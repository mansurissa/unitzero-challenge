from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from accounts.models import User
from accounts.permissions import IsClient, IsOperatorOrAdmin

from . import services
from .models import DatasetRequest
from .serializers import (
    AssignmentSerializer,
    AssignSerializer,
    DatasetRequestCreateSerializer,
    DatasetRequestSerializer,
    StatusEventSerializer,
    TransitionSerializer,
)


class DatasetRequestViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    serializer_class = DatasetRequestSerializer

    def get_permissions(self):
        if self.action == "create":
            return [IsClient()]
        if self.action == "unassign" or (self.action == "assignments" and self.request.method == "POST"):
            return [IsOperatorOrAdmin()]
        return [IsAuthenticated()]

    def get_queryset(self):
        """Clients only ever see their own requests; a foreign id therefore 404s rather than 403s."""
        qs = services.with_assigned_count(DatasetRequest.objects.select_related("client"))
        user = self.request.user
        if user.role == User.Role.CLIENT:
            qs = qs.filter(client=user)

        params = self.request.query_params
        if status_filter := params.get("status"):
            qs = qs.filter(status=status_filter)
        if (client_id := params.get("client")) and user.role != User.Role.CLIENT:
            qs = qs.filter(client_id=client_id)
        return qs.order_by("-created_at")

    def _respond_with(self, request_id, http_status=status.HTTP_200_OK):
        obj = self.get_queryset().get(pk=request_id)
        return Response(self.get_serializer(obj).data, status=http_status)

    def create(self, request):
        data = DatasetRequestCreateSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        created = services.create_request(request.user, **data.validated_data)
        return self._respond_with(created.id, status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def transition(self, request, pk=None):
        obj = self.get_object()  # 404 for clients on other clients' requests
        data = TransitionSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        services.transition(obj.id, data.validated_data["status"], request.user, note=data.validated_data["note"])
        return self._respond_with(obj.id)

    @action(detail=True, methods=["get"])
    def history(self, request, pk=None):
        obj = self.get_object()
        return Response(StatusEventSerializer(obj.events.select_related("actor"), many=True).data)

    @action(detail=True, methods=["get", "post"])
    def assignments(self, request, pk=None):
        """GET: active assignments (owner client or ops). POST {episode_id}: assign an episode (ops only)."""
        obj = self.get_object()
        if request.method == "GET":
            qs = services.active_assignments(obj).select_related("episode", "assigned_by")
            return Response(AssignmentSerializer(qs, many=True).data)
        data = AssignSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        assignment = services.assign_episode(obj.id, data.validated_data["episode_id"], request.user)
        return Response(AssignmentSerializer(assignment).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["delete"], url_path=r"assignments/(?P<episode_id>[^/]+)")
    def unassign(self, request, pk=None, episode_id=None):
        obj = self.get_object()
        services.unassign_episode(obj.id, episode_id, request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)
