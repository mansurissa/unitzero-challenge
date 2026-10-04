from django.db.models import OuterRef, Subquery
from rest_framework import mixins, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from accounts.permissions import IsOperatorOrAdmin

from .models import Episode, ImportRun
from .serializers import EpisodeSerializer, ImportRunSerializer


class EpisodeViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """Operator/admin view of the episode catalogue.

    Filters: task_name, quality, robot_id (all exact, case-insensitive) and available=1
    (good/usable and not currently assigned to any request).
    """

    permission_classes = [IsOperatorOrAdmin]
    serializer_class = EpisodeSerializer

    def get_queryset(self):
        # Imported lazily: dataset_requests depends on episodes, not the other way round.
        from dataset_requests.models import Assignment

        active = Assignment.objects.filter(episode=OuterRef("pk"), unassigned_at__isnull=True)
        qs = Episode.objects.annotate(assigned_request_id=Subquery(active.values("request_id")[:1]))

        params = self.request.query_params
        # Values are stored normalised (lower case, single spaces) by the importer, so normalise the filters the same way.
        if task_name := params.get("task_name"):
            qs = qs.filter(task_name=" ".join(task_name.split()).lower())
        if quality := params.get("quality"):
            qs = qs.filter(quality=quality.strip().lower())
        if robot_id := params.get("robot_id"):
            qs = qs.filter(robot_id=robot_id.strip().lower())
        if params.get("available") in ("1", "true"):
            qs = qs.filter(assigned_request_id__isnull=True, quality__in=Episode.ASSIGNABLE_QUALITIES)
        return qs

    @action(detail=False, methods=["get"], url_path="task-names")
    def task_names(self, request):
        """Distinct task names, for filter dropdowns."""
        names = Episode.objects.order_by("task_name").values_list("task_name", flat=True).distinct()
        return Response(list(names))


class ImportRunViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """Past CSV imports with their full reports, newest first."""

    permission_classes = [IsOperatorOrAdmin]
    serializer_class = ImportRunSerializer
    queryset = ImportRun.objects.select_related("started_by")
