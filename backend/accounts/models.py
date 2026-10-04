from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.db import models
from django.utils import timezone


class UserManager(BaseUserManager):
    use_in_migrations = True

    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError("Users must have an email address")
        # Emails are stored lowercased so lookups and the unique constraint are case-insensitive.
        user = self.model(email=email.strip().lower(), **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user


class User(AbstractBaseUser):
    """Login is by email. Authorization is by `role` only; Django's groups/permissions are not used."""

    class Role(models.TextChoices):
        CLIENT = "client"
        OPERATOR = "operator"
        ADMIN = "admin"

    email = models.EmailField(unique=True)
    name = models.CharField(max_length=150)
    role = models.CharField(max_length=16, choices=Role.choices, default=Role.CLIENT)
    organisation = models.CharField(max_length=150, blank=True)
    is_active = models.BooleanField(default=True)
    date_joined = models.DateTimeField(default=timezone.now)

    objects = UserManager()

    USERNAME_FIELD = "email"
    EMAIL_FIELD = "email"
    REQUIRED_FIELDS = ["name"]

    def __str__(self):
        return f"{self.email} ({self.role})"
