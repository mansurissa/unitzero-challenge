"""All business rules for requests live here. Views stay thin; nothing else writes status or assignments.

Every function takes the acting user and enforces the role rules itself, so the rules hold no matter
which entry point (API view, management command, shell) calls them.
"""

from django.db import IntegrityError, transaction
from django.db.models import Count, Q
from django.utils import timezone

from accounts.models import User
from core.exceptions import Conflict, DomainError, NotAllowed
from episodes.models import Episode

from .models import Assignment, DatasetRequest, StatusEvent

Status = DatasetRequest.Status
OPS = frozenset({User.Role.OPERATOR, User.Role.ADMIN})
CLIENT_ONLY = frozenset({User.Role.CLIENT})

# (from, to) -> roles allowed to make that move. Anything not listed is an invalid transition.
TRANSITIONS = {
    (Status.SUBMITTED, Status.IN_PROGRESS): OPS,
    (Status.IN_PROGRESS, Status.DELIVERED): OPS,
    (Status.DELIVERED, Status.ACCEPTED): CLIENT_ONLY,
    (Status.DELIVERED, Status.REJECTED): CLIENT_ONLY,
    (Status.REJECTED, Status.IN_PROGRESS): OPS,  # rework
}

# Assignments may only change while operators are actively working on the request.
ASSIGNABLE_STATUSES = frozenset({Status.IN_PROGRESS})


def active_assignments(request):
    return request.assignments.filter(unassigned_at__isnull=True)


def assigned_count(request):
    # Prefer the annotation from with_assigned_count() when present (one query for a whole list).
    annotated = getattr(request, "assigned_count", None)
    return annotated if annotated is not None else active_assignments(request).count()


def with_assigned_count(queryset):
    return queryset.annotate(assigned_count=Count("assignments", filter=Q(assignments__unassigned_at__isnull=True)))


def allowed_transitions(request, actor):
    """Statuses `actor` may move `request` to right now (used by the UI to show buttons; not a security check)."""
    if actor.role == User.Role.CLIENT and request.client_id != actor.id:
        return []
    return [to for (frm, to), roles in TRANSITIONS.items() if frm == request.status and actor.role in roles]


def create_request(client, *, task_name, episodes_requested, deadline, notes=""):
    if client.role != User.Role.CLIENT:
        raise NotAllowed("Only clients can create requests.")
    with transaction.atomic():
        request = DatasetRequest.objects.create(
            client=client,
            task_name=" ".join(task_name.split()).lower(),
            episodes_requested=episodes_requested,
            deadline=deadline,
            notes=notes,
        )
        StatusEvent.objects.create(request=request, from_status="", to_status=request.status, actor=client)
    return request


def transition(request_id, to_status, actor, note=""):
    with transaction.atomic():
        # Lock the row so two concurrent transitions (or a transition racing an assignment) serialise.
        request = DatasetRequest.objects.select_for_update().get(pk=request_id)

        if actor.role == User.Role.CLIENT and request.client_id != actor.id:
            raise NotAllowed("This request belongs to another client.")

        roles = TRANSITIONS.get((request.status, to_status))
        if roles is None:
            raise DomainError(f"A request cannot move from '{request.status}' to '{to_status}'.", code="invalid_transition")
        if actor.role not in roles:
            raise NotAllowed(f"Role '{actor.role}' may not move a request to '{to_status}'.")

        if to_status == Status.DELIVERED:
            assigned = active_assignments(request).count()
            if assigned < request.episodes_requested:
                raise DomainError(
                    f"Only {assigned} of {request.episodes_requested} episodes are assigned.",
                    code="not_enough_episodes",
                )

        from_status = request.status
        request.status = to_status
        update_fields = ["status", "updated_at"]
        if to_status == Status.DELIVERED and request.delivered_at is None:
            request.delivered_at = timezone.now()
            update_fields.append("delivered_at")
        request.save(update_fields=update_fields)

        StatusEvent.objects.create(request=request, from_status=from_status, to_status=to_status, actor=actor, note=note)
    return request


def _lock_for_assignment(request_id, actor):
    if actor.role not in OPS:
        raise NotAllowed("Only operators can change assignments.")
    request = DatasetRequest.objects.select_for_update().get(pk=request_id)
    if request.status not in ASSIGNABLE_STATUSES:
        raise DomainError(
            f"Episodes can only be assigned or removed while the request is in progress (it is '{request.status}').",
            code="request_not_in_progress",
        )
    return request


def assign_episode(request_id, episode_code, actor):
    with transaction.atomic():
        request = _lock_for_assignment(request_id, actor)

        try:
            episode = Episode.objects.get(episode_id=episode_code.strip().upper())
        except Episode.DoesNotExist:
            raise DomainError(f"Unknown episode '{episode_code}'.", code="unknown_episode") from None
        if episode.quality not in Episode.ASSIGNABLE_QUALITIES:
            raise DomainError(
                f"Episode {episode.episode_id} has quality '{episode.quality}' and cannot be assigned.", code="episode_quality"
            )

        try:
            # Savepoint so the IntegrityError from the partial unique index does not poison the outer transaction.
            with transaction.atomic():
                assignment = Assignment.objects.create(request=request, episode=episode, assigned_by=actor)
        except IntegrityError:
            holder = Assignment.objects.filter(episode=episode, unassigned_at__isnull=True).values_list("request_id", flat=True).first()
            where = "this request" if holder == request.id else f"request #{holder}"
            raise Conflict(f"Episode {episode.episode_id} is already assigned to {where}.", code="episode_already_assigned") from None
    return assignment


def unassign_episode(request_id, episode_code, actor):
    with transaction.atomic():
        request = _lock_for_assignment(request_id, actor)
        assignment = (
            active_assignments(request).select_related("episode").filter(episode__episode_id=episode_code.strip().upper()).first()
        )
        if assignment is None:
            raise DomainError(f"Episode '{episode_code}' is not assigned to this request.", code="not_assigned")
        assignment.unassigned_at = timezone.now()
        assignment.unassigned_by = actor
        assignment.save(update_fields=["unassigned_at", "unassigned_by"])
    return assignment
