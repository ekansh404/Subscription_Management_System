from django.core import mail
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from .models import Role, User
from .validators import PasswordComplexityValidator

VALID_PASSWORD = "Bright#Loop2026"


def make_user(email, role=Role.CUSTOMER, password=VALID_PASSWORD, **extra):
    extra.setdefault("first_name", "Test")
    extra.setdefault("last_name", role.title())
    if role == Role.ADMIN:
        return User.objects.create_superuser(email, password, **extra)
    return User.objects.create_user(email, password, role=role, **extra)


class PasswordPolicyTests(TestCase):
    def test_complexity_rules(self):
        validator = PasswordComplexityValidator()
        for bad in ("alllowercase!", "ALLUPPERCASE!", "NoSpecial123"):
            with self.assertRaises(ValidationError, msg=bad):
                validator.validate(bad)
        validator.validate("Good#Pass1")  # no exception

    def test_signup_rejects_short_or_weak_passwords(self):
        url = reverse("accounts:signup")
        base = {"first_name": "Asha", "last_name": "Rao", "email": "asha@example.com"}
        for bad in ("Short#1a", "longenoughbutweak", "LONGENOUGH#BUT"):
            response = self.client.post(url, {**base, "password1": bad, "password2": bad})
            self.assertEqual(response.status_code, 200, bad)
            self.assertFalse(User.objects.filter(email="asha@example.com").exists(), bad)


class SignupTests(TestCase):
    def test_signup_creates_customer_and_logs_in(self):
        response = self.client.post(
            reverse("accounts:signup"),
            {
                "first_name": "Asha",
                "last_name": "Rao",
                "email": "Asha@Example.com",
                "password1": VALID_PASSWORD,
                "password2": VALID_PASSWORD,
            },
        )
        self.assertRedirects(response, reverse("core:home"), fetch_redirect_response=False)
        user = User.objects.get(email="asha@example.com")  # stored lower-case
        self.assertEqual(user.role, Role.CUSTOMER)
        self.assertFalse(user.is_staff)
        self.assertEqual(int(self.client.session["_auth_user_id"]), user.pk)

    def test_email_must_be_unique_case_insensitively(self):
        make_user("asha@example.com")
        response = self.client.post(
            reverse("accounts:signup"),
            {
                "first_name": "Other",
                "last_name": "Person",
                "email": "ASHA@example.com",
                "password1": VALID_PASSWORD,
                "password2": VALID_PASSWORD,
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "already exists")
        self.assertEqual(User.objects.count(), 1)


class LoginAndResetTests(TestCase):
    def test_login_is_case_insensitive_on_email(self):
        make_user("staff@example.com", role=Role.STAFF)
        response = self.client.post(reverse("accounts:login"), {"username": "STAFF@example.com", "password": VALID_PASSWORD})
        self.assertRedirects(response, reverse("core:home"), fetch_redirect_response=False)

    def test_password_reset_sends_link_to_registered_email(self):
        make_user("asha@example.com")
        response = self.client.post(reverse("accounts:password_reset"), {"email": "asha@example.com"})
        self.assertRedirects(response, reverse("accounts:password_reset_done"))
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("asha@example.com", mail.outbox[0].to)
        self.assertIn("/accounts/password/reset/", mail.outbox[0].body)


class StaffManagementTests(TestCase):
    def setUp(self):
        self.admin = make_user("admin@example.com", role=Role.ADMIN)
        self.staff = make_user("staff@example.com", role=Role.STAFF)
        self.customer = make_user("customer@example.com")

    def test_only_admin_can_open_staff_pages(self):
        url = reverse("accounts:staff_list")
        self.assertEqual(self.client.get(url).status_code, 302)  # anonymous -> login
        self.client.force_login(self.customer)
        self.assertEqual(self.client.get(url).status_code, 403)
        self.client.force_login(self.staff)
        self.assertEqual(self.client.get(url).status_code, 403)
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(url).status_code, 200)

    def test_admin_creates_staff_member(self):
        self.client.force_login(self.admin)
        response = self.client.post(
            reverse("accounts:staff_create"),
            {
                "first_name": "Neha",
                "last_name": "Verma",
                "email": "neha@example.com",
                "role": Role.STAFF,
                "password1": VALID_PASSWORD,
                "password2": VALID_PASSWORD,
            },
        )
        self.assertRedirects(response, reverse("accounts:staff_list"))
        neha = User.objects.get(email="neha@example.com")
        self.assertEqual(neha.role, Role.STAFF)
        self.assertTrue(neha.check_password(VALID_PASSWORD))
        self.assertFalse(neha.is_staff)  # no Django-admin access for staff

    def test_admin_cannot_demote_self(self):
        self.client.force_login(self.admin)
        response = self.client.post(
            reverse("accounts:staff_update", args=[self.admin.pk]),
            {"first_name": "A", "last_name": "D", "email": self.admin.email, "role": Role.STAFF, "is_active": "on"},
        )
        self.assertEqual(response.status_code, 200)
        self.admin.refresh_from_db()
        self.assertEqual(self.admin.role, Role.ADMIN)

    def test_superuser_has_admin_role(self):
        self.assertEqual(self.admin.role, Role.ADMIN)
        self.assertTrue(self.admin.is_staff)


class ResetEmailBrandingTests(TestCase):
    def test_reset_email_uses_app_name_not_host(self):
        make_user("asha@example.com")
        self.client.post(reverse("accounts:password_reset"), {"email": "asha@example.com"})
        self.assertIn("Brightloop", mail.outbox[0].subject)
        self.assertNotIn("testserver", mail.outbox[0].subject)
