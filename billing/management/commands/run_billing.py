from datetime import date

from django.core.management.base import BaseCommand, CommandError

from billing.services import run_billing


class Command(BaseCommand):
    help = "Billing day: activate subscriptions that start, invoice every due period, close expired ones. Safe to run repeatedly."

    def add_arguments(self, parser):
        parser.add_argument("--date", help="Run as of this date (YYYY-MM-DD); default today.")
        parser.add_argument("--confirm", action="store_true", help="Confirm the generated invoices immediately.")

    def handle(self, *args, **options):
        try:
            run_date = date.fromisoformat(options["date"]) if options["date"] else None
        except ValueError as error:
            raise CommandError("--date must look like 2026-10-31") from error
        result = run_billing(run_date, auto_confirm=options["confirm"])
        self.stdout.write(
            self.style.SUCCESS(
                f"Billing run {result.run_date}: {len(result.invoices)} invoice(s) for {result.invoiced_amount:,.2f}, "
                f"{result.activated} activated, {result.closed} closed."
            )
        )
        for error in result.errors:
            self.stderr.write(error)
