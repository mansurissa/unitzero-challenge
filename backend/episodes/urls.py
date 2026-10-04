from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter(trailing_slash=False)
router.register("episodes", views.EpisodeViewSet, basename="episode")

urlpatterns = router.urls
