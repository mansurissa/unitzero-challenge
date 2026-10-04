from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone


class DatasetRequest(models.Model):
    """A client's request for N episodes of a task. Status changes go through services.transition() only."""

    class Status(models.TextChoices):
        SUBMITTED = "submitted"
        IN_PROGRESS = "in_progress"
        DELIVERED = "delivered"
        ACCEPTED = "accepted"
        REJECTED = "rejected"

    client = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="dataset_requests")
    task_name = models.CharField(max_length=100)
    episodes_requested = models.PositiveIntegerField()
    deadline = models.DateField()
    notes = models.TextField(blank=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.SUBMITTED)

    # Denormalised timestamps for the fulfilment analytics (the full trail is in StatusEvent).
    submitted_at = models.DateTimeField(default=timezone.now)
    delivered_at = models.DateTimeField(null=True, blank=True)  # first delivery; rework does not reset it

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(condition=Q(episodes_requested__gte=1), name="request_episodes_requested_positive"),
        ]
        indexes = [
            models.Index(fields=["client", "status"], name="request_client_status_idx"),
            models.Index(fields=["submitted_at"], name="request_submitted_idx"),
        ]

    def __str__(self):
        return f"#{self.pk} {self.task_name} x{self.episodes_requested} ({self.status})"


class StatusEvent(models.Model):
    """Append-only audit trail: who moved which request to which status, and when."""

    request = models.ForeignKey(DatasetRequest, on_delete=models.CASCADE, related_name="events")
    from_status = models.CharField(max_length=16, choices=DatasetRequest.Status.choices, blank=True)  # blank on creation
    to_status = models.CharField(max_length=16, choices=DatasetRequest.Status.choices)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")
    note = models.TextField(blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["created_at", "id"]

    def __str__(self):
        return f"#{self.request_id}: {self.from_status or '∅'} → {self.to_status}"


class Assignment(models.Model):
    """An episode attached to a request. Unassigning keeps the row (history) and sets unassigned_at."""

    request = models.ForeignKey(DatasetRequest, on_delete=models.CASCADE, related_name="assignments")
    episode = models.ForeignKey("episodes.Episode", on_delete=models.PROTECT, related_name="assignments")
    assigned_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")
    assigned_at = models.DateTimeField(default=timezone.now)
    unassigned_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    unassigned_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["assigned_at", "id"]
        constraints = [
            # The database, not Python, guarantees "an episode is assigned to at most one request at a time".
            models.UniqueConstraint(
                fields=["episode"], condition=Q(unassigned_at__isnull=True), name="one_active_assignment_per_episode"
            ),
        ]
        indexes = [
            models.Index(fields=["request"], condition=Q(unassigned_at__isnull=True), name="assignment_active_request_idx"),
        ]

    def __str__(self):
        return f"{self.episode_id} → request #{self.request_id}"
