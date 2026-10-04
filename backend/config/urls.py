from django.urls import include, path

from analytics.views import analytics
from core.views import health

urlpatterns = [
    path("health", health, name="health"),
    path("api/", include("accounts.urls")),
    path("api/", include("episodes.urls")),
    path("api/", include("dataset_requests.urls")),
    path("api/analytics", analytics, name="analytics"),
]
