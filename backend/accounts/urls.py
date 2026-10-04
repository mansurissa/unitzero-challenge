from django.urls import path

from . import views

urlpatterns = [
    path("auth/csrf", views.csrf, name="auth-csrf"),
    path("auth/login", views.login, name="auth-login"),
    path("auth/logout", views.logout, name="auth-logout"),
    path("auth/me", views.me, name="auth-me"),
]
