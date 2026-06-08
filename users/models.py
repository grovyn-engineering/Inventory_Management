from django.contrib.auth.models import AbstractUser, UserManager as DjangoUserManager
from django.db import models
from common.models import TimeStampedModel

ROLE_ADMIN = "admin"
ROLE_MANAGER = "manager"
ROLE_WORKER = "worker"
LEGACY_ADMIN_ROLE = "super_admin"


class UserManager(DjangoUserManager):
    def create_superuser(self, username, email=None, password=None, **extra_fields):
        extra_fields.setdefault("role", ROLE_ADMIN)
        return super().create_superuser(username, email, password, **extra_fields)


class User(TimeStampedModel, AbstractUser):
    ROLE_CHOICES = (
        (ROLE_ADMIN, "Admin"),
        (ROLE_MANAGER, "Manager"),
        (ROLE_WORKER, "Worker"),
    )

    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default=ROLE_WORKER, db_index=True)
    phone_number = models.CharField(max_length=15, unique=True, null=True, blank=True)
    location = models.ForeignKey(
        'inventory.Location',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='users',
    )

    objects = UserManager()

    @property
    def normalized_role(self):
        role = (self.role or "").lower()
        if role == LEGACY_ADMIN_ROLE:
            return ROLE_ADMIN
        return role

    def has_role(self, *roles):
        if self.is_superuser and ROLE_ADMIN in roles:
            return True
        return self.normalized_role in roles

    def __str__(self):
        return f"{self.username} - {self.normalized_role}"
