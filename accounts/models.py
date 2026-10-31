"""
Users and roles.

The login identifier is the email address (unique, stored lower-case so
``Ekansh@Example.com`` and ``ekansh@example.com`` are the same account).

Roles decide what a user can see:

* ``admin``    - full control, the only role that can add staff
* ``staff``    - internal team with day-to-day access
* ``customer`` - self-signup accounts; portal access to their own data only

Django's ``is_staff`` flag (access to the built-in admin site) is kept in sync
with the ``admin`` role; our application permissions are driven by ``role``.
"""

from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models

from core.navigation import ADMIN, CUSTOMER, STAFF


class Role(models.TextChoices):
    ADMIN = ADMIN, "Administrator"
    STAFF = STAFF, "Staff"
    CUSTOMER = CUSTOMER, "Customer"


class UserManager(BaseUserManager):
    use_in_migrations = True

    def _create_user(self, email, password, **extra_fields):
        if not email:
            raise ValueError("An email address is required.")
        email = self.normalize_email(email).lower()
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, **extra_fields):
        extra_fields.setdefault("role", Role.CUSTOMER)
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra_fields)

    def create_staff(self, email, password=None, **extra_fields):
        extra_fields["role"] = Role.STAFF
        extra_fields["is_staff"] = False
        extra_fields["is_superuser"] = False
        return self._create_user(email, password, **extra_fields)

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields["role"] = Role.ADMIN
        extra_fields["is_staff"] = True
        extra_fields["is_superuser"] = True
        return self._create_user(email, password, **extra_fields)


class User(AbstractUser):
    username = None
    email = models.EmailField(
        "email address",
        unique=True,
        error_messages={"unique": "An account with this email already exists."},
    )
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.CUSTOMER, db_index=True)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["first_name", "last_name"]

    objects = UserManager()

    class Meta:
        ordering = ["first_name", "last_name", "email"]
        verbose_name = "user"
        verbose_name_plural = "users"

    def __str__(self) -> str:
        return self.display_name

    def save(self, *args, **kwargs):
        self.email = self.email.lower()
        # Administrators can use Django's admin site; nobody else needs it.
        self.is_staff = self.role == Role.ADMIN or self.is_superuser
        super().save(*args, **kwargs)

    @property
    def display_name(self) -> str:
        return self.get_full_name() or self.email

    @property
    def is_admin(self) -> bool:
        return self.role == Role.ADMIN

    @property
    def is_staff_member(self) -> bool:
        """Internal team member (staff or admin)."""
        return self.role in (Role.ADMIN, Role.STAFF)

    @property
    def is_customer(self) -> bool:
        return self.role == Role.CUSTOMER
