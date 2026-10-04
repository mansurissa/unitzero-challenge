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
