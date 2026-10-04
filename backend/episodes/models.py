from django.db import models


class Episode(models.Model):
    """Metadata for one recorded clip, as exported by the recording system."""

    class Quality(models.TextChoices):
        GOOD = "good"
        USABLE = "usable"
        BAD = "bad"

    # Only these qualities may be assigned to a request.
    ASSIGNABLE_QUALITIES = (Quality.GOOD, Quality.USABLE)

    # The recording system's identifier (e.g. EP-00042), normalised to upper case on import.
    episode_id = models.CharField(max_length=32, unique=True)
    robot_id = models.CharField(max_length=32)
    task_name = models.CharField(max_length=100)
    recorded_at = models.DateTimeField()
    duration_seconds = models.PositiveIntegerField()
    operator_name = models.CharField(max_length=100, blank=True)
    quality = models.CharField(max_length=8, choices=Quality.choices)
    imported_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-recorded_at", "episode_id"]
        indexes = [
            # analytics: episodes per day per robot over a date range
            models.Index(fields=["recorded_at", "robot_id"], name="episode_recorded_robot_idx"),
            # analytics: top task names by good episodes; operator list filtered by quality + task
            models.Index(fields=["quality", "task_name", "recorded_at"], name="episode_quality_task_idx"),
            # operator list filtered by task only
            models.Index(fields=["task_name"], name="episode_task_idx"),
        ]

    def __str__(self):
        return self.episode_id
