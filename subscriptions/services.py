"""
Subscription lifecycle rules: the single place that decides what may happen
to a subscription. Views, the customer portal, the API and the nightly
billing run all call these functions.

    Draft --send--> Quotation --confirm--> Confirmed --activate--> Active --close--> Closed
      \\______________confirm_______________/                     |  ^
                                                       pause/resume |  | renew (reopens)
                                                                    v  |
                                                                   Paused
"""

from datetime import date, timedelta
from decimal import Decimal

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from catalog.models import Plan
from core.sequences import next_number
from core.utils import dates

from .models import RUNNING_STATUSES, Status, Subscription, SubscriptionEvent, SubscriptionLine


class TransitionError(Exception):
    """Raised when an action is not allowed; the message is shown to the user."""


def log(subscription, message, *, user=None, from_status="", to_status=""):
    SubscriptionEvent.objects.create(
        subscription=subscription, user=user, message=message, from_status=from_status, to_status=to_status
    )


def _today() -> date:
    return timezone.localdate()


# --- creation & totals --------------------------------------------------------


def assign_number(subscription: Subscription) -> None:
    if not subscription.number:
        subscription.number = next_number("subscription", prefix="SUB")


def recompute_totals(subscription: Subscription) -> Subscription:
    for line in subscription.lines.prefetch_related("taxes"):
        line.compute_amounts()
        line.save(update_fields=["amount_untaxed", "amount_tax", "amount_total"])
    totals = subscription.lines.aggregate(
        untaxed=Sum("amount_untaxed"), tax=Sum("amount_tax"), total=Sum("amount_total")
    )
    subscription.amount_untaxed = totals["untaxed"] or Decimal("0.00")
    subscription.amount_tax = totals["tax"] or Decimal("0.00")
    subscription.amount_total = totals["total"] or Decimal("0.00")
    subscription.mrr = dates.monthly_amount(subscription.amount_untaxed, subscription.plan.billing_period)
    subscription.save(update_fields=["amount_untaxed", "amount_tax", "amount_total", "mrr", "updated_at"])
    return subscription


def add_line(subscription, variant, quantity, unit_price=None, taxes=None) -> SubscriptionLine:
    line = SubscriptionLine.objects.create(
        subscription=subscription,
        variant=variant,
        quantity=Decimal(quantity),
        unit_price=variant.price if unit_price is None else unit_price,
    )
    line.taxes.set(variant.product.taxes.filter(is_active=True) if taxes is None else taxes)
    return line


def default_expiry(start: date, plan: Plan, periods: int | None) -> date | None:
    if not periods:
        return None
    return dates.add_period(start, plan.billing_period, periods) - timedelta(days=1)


@transaction.atomic
def create_subscription(customer, plan, *, start_date=None, template=None, user=None, with_plan_line=True, **fields):
    """
    New draft subscription. With a quotation template the plan, payment terms,
    notes, contract length and product lines are copied from it; otherwise the
    plan's default product is added at the plan price and minimum quantity.
    """
    start_date = start_date or _today()
    subscription = Subscription(customer=customer, plan=plan, start_date=start_date, salesperson=user, **fields)
    if template is not None:
        subscription.template = template
        subscription.payment_term_days = template.payment_term_days
        subscription.notes = subscription.notes or template.notes
        subscription.expiry_date = subscription.expiry_date or default_expiry(start_date, plan, template.duration_periods)
    assign_number(subscription)
    subscription.save()
    if template is not None:
        for template_line in template.lines.select_related("variant__product"):
            add_line(subscription, template_line.variant, template_line.quantity, template_line.unit_price)
    elif with_plan_line and plan.product_id:
        add_line(subscription, plan.product, plan.min_quantity, plan.price)
    recompute_totals(subscription)
    source = f"from template {template.name}" if template else "manually"
    log(subscription, f"Subscription created {source}.", user=user, to_status=Status.DRAFT)
    return subscription


# --- validation -------------------------------------------------------------


def validate_for_confirmation(subscription: Subscription, today: date | None = None) -> None:
    today = today or _today()
    plan = subscription.plan
    lines = list(subscription.lines.all())
    if not lines:
        raise TransitionError("Add at least one product line before confirming.")
    if not plan.is_available(subscription.start_date):
        raise TransitionError(f"Plan {plan.name} is not available on {subscription.start_date:%d %b %Y}.")
    if subscription.expiry_date and subscription.expiry_date <= subscription.start_date:
        raise TransitionError("The expiry date must be after the start date.")
    if subscription.status == Status.QUOTATION and subscription.quotation_valid_until and subscription.quotation_valid_until < today:
        raise TransitionError(
            f"This quotation expired on {subscription.quotation_valid_until:%d %b %Y}. Send it again to renew its validity."
        )
    seat_lines = [line for line in lines if line.variant_id == plan.product_id] or lines
    quantity = sum(line.quantity for line in seat_lines)
    if quantity < plan.min_quantity:
        raise TransitionError(f"Plan {plan.name} requires a minimum quantity of {plan.min_quantity} (currently {quantity:g}).")


# --- transitions --------------------------------------------------------------


def _move(subscription, to_status, message, user=None, **changes):
    from_status = subscription.status
    subscription.status = to_status
    for field, value in changes.items():
        setattr(subscription, field, value)
    subscription.save()
    log(subscription, message, user=user, from_status=from_status, to_status=to_status)
    return subscription


def _require(subscription, *allowed):
    if subscription.status not in allowed:
        raise TransitionError(f"Not possible while the subscription is {subscription.get_status_display().lower()}.")


@transaction.atomic
def send_quotation(subscription, user=None, today=None):
    """Draft (or expired quotation) -> Quotation, valid for the template's validity days."""
    _require(subscription, Status.DRAFT, Status.QUOTATION)
    if not subscription.lines.exists():
        raise TransitionError("Add at least one product line before sending the quotation.")
    today = today or _today()
    validity = subscription.template.validity_days if subscription.template else 30
    valid_until = today + timedelta(days=validity)
    return _move(subscription, Status.QUOTATION, f"Quotation sent, valid until {valid_until:%d %b %Y}.", user, quotation_valid_until=valid_until)


@transaction.atomic
def confirm(subscription, user=None, today=None):
    """Customer accepted: Draft/Quotation -> Confirmed, then Active straight away if the start date has arrived."""
    _require(subscription, Status.DRAFT, Status.QUOTATION)
    today = today or _today()
    validate_for_confirmation(subscription, today)
    _move(subscription, Status.CONFIRMED, "Subscription confirmed.", user)
    if subscription.start_date <= today:
        activate(subscription, user=user, today=today)
    return subscription


@transaction.atomic
def activate(subscription, user=None, today=None):
    _require(subscription, Status.CONFIRMED)
    today = today or _today()
    if subscription.start_date > today:
        raise TransitionError(f"The subscription starts on {subscription.start_date:%d %b %Y}.")
    return _move(
        subscription,
        Status.ACTIVE,
        "Subscription is active; billing starts.",
        user,
        next_invoice_date=subscription.next_invoice_date or subscription.start_date,
    )


@transaction.atomic
def pause(subscription, user=None):
    _require(subscription, Status.ACTIVE)
    if not subscription.plan.pausable:
        raise TransitionError(f"Plan {subscription.plan.name} does not allow pausing.")
    return _move(subscription, Status.PAUSED, "Subscription paused; no invoices while paused.", user)


@transaction.atomic
def resume(subscription, user=None, today=None):
    """Paused -> Active. Periods missed while paused are not billed: billing restarts today."""
    _require(subscription, Status.PAUSED)
    today = today or _today()
    next_date = max(subscription.next_invoice_date or today, today)
    return _move(subscription, Status.ACTIVE, "Subscription resumed.", user, next_invoice_date=next_date)


@transaction.atomic
def close(subscription, user=None, reason="", today=None, automatic=False):
    today = today or _today()
    _require(subscription, Status.CONFIRMED, Status.ACTIVE, Status.PAUSED, Status.DRAFT, Status.QUOTATION)
    running = subscription.status in RUNNING_STATUSES or subscription.status == Status.CONFIRMED
    if running and not automatic and not subscription.plan.closable:
        raise TransitionError(f"Plan {subscription.plan.name} cannot be closed before it ends.")
    message = "Closed automatically at expiry." if automatic else "Subscription closed."
    if reason:
        message = f"{message} Reason: {reason}"
    return _move(subscription, Status.CLOSED, message, user, closed_on=today, close_reason=reason[:200], next_invoice_date=None)


@transaction.atomic
def renew(subscription, user=None, today=None):
    """
    Extend the contract by its original length (or one billing period when it
    has none). A closed subscription is reopened and billing resumes.
    """
    _require(subscription, Status.ACTIVE, Status.PAUSED, Status.CLOSED)
    if not subscription.plan.renewable:
        raise TransitionError(f"Plan {subscription.plan.name} is not renewable.")
    today = today or _today()
    period = subscription.plan.billing_period
    if subscription.expiry_date:
        term_days = (subscription.expiry_date - subscription.start_date).days + 1
        base = max(subscription.expiry_date, today - timedelta(days=1))
        new_expiry = base + timedelta(days=term_days)
    else:
        new_expiry = dates.add_period(max(today, subscription.start_date), period) - timedelta(days=1)
    changes = {"expiry_date": new_expiry}
    to_status = subscription.status
    if subscription.status == Status.CLOSED:
        to_status = Status.ACTIVE
        changes.update(closed_on=None, close_reason="", next_invoice_date=today)
    return _move(subscription, to_status, f"Renewed until {new_expiry:%d %b %Y}.", user, **changes)


ACTIONS = {
    "send": send_quotation,
    "confirm": confirm,
    "activate": activate,
    "pause": pause,
    "resume": resume,
    "close": close,
    "renew": renew,
}


def available_actions(subscription: Subscription, today: date | None = None) -> list[str]:
    """Buttons to show for the current state (the services still re-check)."""
    today = today or _today()
    plan = subscription.plan
    status = subscription.status
    actions = []
    if status in (Status.DRAFT, Status.QUOTATION):
        actions += ["send", "confirm", "close"]
    if status == Status.CONFIRMED:
        if subscription.start_date <= today:
            actions.append("activate")
        if plan.closable:
            actions.append("close")
    if status == Status.ACTIVE:
        if plan.pausable:
            actions.append("pause")
        if plan.closable:
            actions.append("close")
        if plan.renewable:
            actions.append("renew")
    if status == Status.PAUSED:
        actions.append("resume")
        if plan.closable:
            actions.append("close")
        if plan.renewable:
            actions.append("renew")
    if status == Status.CLOSED and plan.renewable:
        actions.append("renew")
    return actions


# --- scheduled housekeeping (called by the billing run) -----------------------


def activate_due(today: date | None = None) -> int:
    """Confirmed subscriptions whose start date has arrived become active."""
    today = today or _today()
    due = Subscription.objects.filter(status=Status.CONFIRMED, start_date__lte=today).select_related("plan")
    count = 0
    for subscription in due:
        activate(subscription, today=today)
        count += 1
    return count


def close_expired(today: date | None = None) -> int:
    """Running subscriptions past their expiry date close on their own when the plan says so."""
    today = today or _today()
    expired = Subscription.objects.filter(
        status__in=RUNNING_STATUSES, expiry_date__lt=today, plan__auto_close=True
    ).select_related("plan")
    count = 0
    for subscription in expired:
        close(subscription, today=today, automatic=True)
        count += 1
    return count
