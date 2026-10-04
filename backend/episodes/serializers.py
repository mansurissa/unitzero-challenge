from rest_framework import serializers

from .models import Episode, ImportRun


class EpisodeSerializer(serializers.ModelSerializer):
    class Meta:
        model = Episode
        fields = ["id", "episode_id", "robot_id", "task_name", "recorded_at", "duration_seconds", "operator_name", "quality"]
        read_only_fields = fields


class ImportRunSerializer(serializers.ModelSerializer):
    started_by = serializers.SlugRelatedField(slug_field="email", read_only=True)

    class Meta:
        model = ImportRun
        fields = ["id", "started_at", "started_by", "source", "total_rows", "inserted", "skipped", "report"]
        read_only_fields = fields
