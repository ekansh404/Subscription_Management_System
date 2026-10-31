"""
Email backend for local use and demos: every message is stored in the
database (Email outbox page, admin only) and also printed to the terminal.
No mail server or internet connection is needed. Set ``EMAIL_BACKEND=smtp``
in ``.env`` to deliver for real instead.
"""

from django.core.mail.backends.base import BaseEmailBackend
from django.core.mail.backends.console import EmailBackend as ConsoleBackend


class OutboxEmailBackend(BaseEmailBackend):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.console = ConsoleBackend(*args, **kwargs)

    def send_messages(self, email_messages):
        from .models import OutboxEmail

        for message in email_messages:
            OutboxEmail.objects.create(
                from_email=message.from_email,
                to=", ".join(message.recipients()),
                subject=message.subject[:255],
                body=message.body,
            )
        self.console.send_messages(email_messages)
        return len(email_messages)
