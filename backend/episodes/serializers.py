from rest_framework import serializers

from .models import Episode


class EpisodeSerializer(serializers.ModelSerializer):
    class Meta:
        model = Episode
        fields = ["id", "episode_id", "robot_id", "task_name", "recorded_at", "duration_seconds", "operator_name", "quality"]
        read_only_fields = fields
