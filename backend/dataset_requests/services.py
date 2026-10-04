"""All business rules for requests live here. Views stay thin; nothing else writes `status`.

Every function takes the acting user and enforces the role rules itself, so the rules hold no matter
which entry point (API view, management command, shell) calls them.
"""

from django.db import transaction
from django.utils import timezone

from accounts.models import User
from core.exceptions import DomainError, NotAllowed

from .models import DatasetRequest, StatusEvent

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


def assigned_count(request):
    """Episodes currently attached to the request. Assignments arrive in the next step; until then it is 0."""
    return 0


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
        # Lock the row so two concurrent transitions serialise instead of both passing the checks.
        request = DatasetRequest.objects.select_for_update().get(pk=request_id)

        if actor.role == User.Role.CLIENT and request.client_id != actor.id:
            raise NotAllowed("This request belongs to another client.")

        roles = TRANSITIONS.get((request.status, to_status))
        if roles is None:
            raise DomainError(f"A request cannot move from '{request.status}' to '{to_status}'.", code="invalid_transition")
        if actor.role not in roles:
            raise NotAllowed(f"Role '{actor.role}' may not move a request to '{to_status}'.")

        if to_status == Status.DELIVERED:
            assigned = assigned_count(request)
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
