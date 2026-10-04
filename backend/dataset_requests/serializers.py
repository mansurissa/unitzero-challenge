from django.utils import timezone
from rest_framework import serializers

from episodes.serializers import EpisodeSerializer

from . import services
from .models import Assignment, DatasetRequest, StatusEvent


class ClientSummarySerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()
    email = serializers.EmailField()
    organisation = serializers.CharField()


class DatasetRequestSerializer(serializers.ModelSerializer):
    client = ClientSummarySerializer(read_only=True)
    assigned_count = serializers.SerializerMethodField()
    allowed_transitions = serializers.SerializerMethodField()

    class Meta:
        model = DatasetRequest
        fields = [
            "id", "client", "task_name", "episodes_requested", "deadline", "notes", "status",
            "assigned_count", "allowed_transitions", "submitted_at", "delivered_at", "created_at", "updated_at",
        ]
        read_only_fields = fields

    def get_assigned_count(self, obj):
        return services.assigned_count(obj)

    def get_allowed_transitions(self, obj):
        return services.allowed_transitions(obj, self.context["request"].user)


class DatasetRequestCreateSerializer(serializers.Serializer):
    task_name = serializers.CharField(max_length=100)
    episodes_requested = serializers.IntegerField(min_value=1, max_value=100_000)
    deadline = serializers.DateField()
    notes = serializers.CharField(required=False, allow_blank=True, default="")

    def validate_task_name(self, value):
        value = " ".join(value.split()).lower()
        if not value:
            raise serializers.ValidationError("task_name cannot be blank.")
        return value

    def validate_deadline(self, value):
        if value < timezone.localdate():
            raise serializers.ValidationError("deadline cannot be in the past.")
        return value


class TransitionSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=DatasetRequest.Status.choices)
    note = serializers.CharField(required=False, allow_blank=True, default="")


class AssignSerializer(serializers.Serializer):
    episode_id = serializers.CharField(max_length=32)


class AssignmentSerializer(serializers.ModelSerializer):
    episode = EpisodeSerializer(read_only=True)
    assigned_by = serializers.SlugRelatedField(slug_field="email", read_only=True)

    class Meta:
        model = Assignment
        fields = ["id", "episode", "assigned_by", "assigned_at"]
        read_only_fields = fields


class StatusEventSerializer(serializers.ModelSerializer):
    actor = serializers.SlugRelatedField(slug_field="email", read_only=True)

    class Meta:
        model = StatusEvent
        fields = ["id", "from_status", "to_status", "actor", "note", "created_at"]
        read_only_fields = fields
