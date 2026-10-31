import csv

from django.http import HttpResponse
from django.views import View
from django.views.generic import TemplateView

from core.mixins import StaffRequiredMixin

from . import services
from .forms import ReportFilterForm


class FilteredReportMixin:
    def get_filters(self) -> services.ReportFilters:
        filters = services.ReportFilters.default()
        self.filter_form = ReportFilterForm(
            self.request.GET or None, initial={"date_from": filters.date_from, "date_to": filters.date_to}
        )
        if self.filter_form.is_valid():
            data = self.filter_form.cleaned_data
            filters.date_from = data["date_from"] or filters.date_from
            filters.date_to = data["date_to"] or filters.date_to
            filters.plan_id = data["plan"].pk if data["plan"] else None
            filters.customer_id = data["customer"].pk if data["customer"] else None
        return filters


class DashboardView(StaffRequiredMixin, FilteredReportMixin, TemplateView):
    """The finance lead's one place: KPIs, trends and what needs chasing."""

    template_name = "reports/dashboard.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        filters = self.get_filters()
        series = services.monthly_series(filters)
        statuses = services.status_breakdown(filters)
        plans = list(services.mrr_by_plan(filters))
        context.update(
            filters=filters,
            filter_form=self.filter_form,
            kpi=services.kpis(filters),
            top_overdue=services.top_overdue(filters),
            mrr_plans=plans,
            chart_data={
                "months": [row["month"].strftime("%b %Y") for row in series],
                "invoiced": [float(row["invoiced"]) for row in series],
                "collected": [float(row["collected"]) for row in series],
                "statusLabels": [label for label, _ in statuses],
                "statusCounts": [count for _, count in statuses],
                "planLabels": [row["plan__name"] for row in plans],
                "planMrr": [float(row["mrr"]) for row in plans],
            },
        )
        return context


class RevenueReportView(StaffRequiredMixin, FilteredReportMixin, TemplateView):
    template_name = "reports/revenue.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        filters = self.get_filters()
        rows = services.monthly_series(filters)
        context.update(
            filters=filters,
            filter_form=self.filter_form,
            rows=rows,
            totals={key: sum(row[key] for row in rows) for key in ("invoiced", "untaxed", "tax", "discount", "collected", "count")},
            by_plan=services.revenue_by(filters, "plan")[:10],
            by_customer=services.revenue_by(filters, "customer")[:10],
        )
        return context


class RevenueCsvView(StaffRequiredMixin, FilteredReportMixin, View):
    def get(self, request):
        filters = self.get_filters()
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = f'attachment; filename="revenue_{filters.date_from}_{filters.date_to}.csv"'
        writer = csv.writer(response)
        writer.writerow(["Month", "Invoices", "Untaxed", "Discounts", "Taxes", "Invoiced total", "Collected"])
        for row in services.monthly_series(filters):
            amounts = [f"{row[key]:.2f}" for key in ("untaxed", "discount", "tax", "invoiced", "collected")]
            writer.writerow([row["month"].strftime("%Y-%m"), row["count"], *amounts])
        return response
