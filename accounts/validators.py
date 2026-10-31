import re

from django.core.exceptions import ValidationError


class PasswordComplexityValidator:
    """
    Problem statement rule: the password must contain an uppercase letter,
    a lowercase letter and a special character. (Length is enforced by
    Django's ``MinimumLengthValidator`` with ``min_length=9``, i.e. more than 8.)
    """

    RULES = (
        (re.compile(r"[A-Z]"), "an uppercase letter"),
        (re.compile(r"[a-z]"), "a lowercase letter"),
        (re.compile(r"[^A-Za-z0-9]"), "a special character (for example ! @ # $ %)"),
    )

    def validate(self, password, user=None):
        missing = [label for pattern, label in self.RULES if not pattern.search(password)]
        if missing:
            raise ValidationError(
                "Your password must contain %(missing)s.",
                code="password_complexity",
                params={"missing": ", ".join(missing)},
            )

    def get_help_text(self):
        return "Your password must contain an uppercase letter, a lowercase letter and a special character."
