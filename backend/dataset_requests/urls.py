from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter(trailing_slash=False)
router.register("requests", views.DatasetRequestViewSet, basename="request")

urlpatterns = router.urls
