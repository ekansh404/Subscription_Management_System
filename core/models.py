from django.db import models


class TimeStampedModel(models.Model):
    """Abstract base that records when a row was created and last changed."""

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class Sequence(models.Model):
    """
    Named counter behind human-readable document numbers such as
    ``SUB-00001`` or ``INV/2026/00001``. See :func:`core.sequences.next_number`.
    """

    key = models.CharField(max_length=50, unique=True)
    last_value = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["key"]

    def __str__(self) -> str:
        return f"{self.key} = {self.last_value}"


class OutboxEmail(models.Model):
    """
    Copy of an email sent while ``EMAIL_BACKEND=outbox`` (the default). Lets
    you demo password resets, invoices and reminders without a mail server;
    administrators read them under Email outbox.
    """

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    from_email = models.CharField(max_length=254)
    to = models.TextField(help_text="Comma-separated recipients.")
    subject = models.CharField(max_length=255)
    body = models.TextField()

    class Meta:
        ordering = ["-created_at", "-pk"]

    def __str__(self) -> str:
        return self.subject
