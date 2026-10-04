from django.urls import include, path

from core.views import health

urlpatterns = [
    path("health", health, name="health"),
    path("api/", include("accounts.urls")),
    path("api/", include("episodes.urls")),
]
