from django.urls import path
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter(trailing_slash=False)
router.register("users", views.UserViewSet, basename="user")

urlpatterns = [
    path("auth/csrf", views.csrf, name="auth-csrf"),
    path("auth/login", views.login, name="auth-login"),
    path("auth/logout", views.logout, name="auth-logout"),
    path("auth/me", views.me, name="auth-me"),
    *router.urls,
]
