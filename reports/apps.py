from django.apps import AppConfig

from core.navigation import MenuItem


class ReportsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "reports"
    verbose_name = "Reports"

    menu = (
        MenuItem("Dashboard", "reports:dashboard", icon="dashboard", order=10, match="reports:dashboard"),
        MenuItem("Revenue report", "reports:revenue", icon="chart", order=60, match="reports:revenue"),
    )
