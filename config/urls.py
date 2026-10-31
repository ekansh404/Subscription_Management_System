"""
Root URL configuration.

Each product app is mounted under its own prefix (`/<app>/`), except `core`,
which owns the site root. Adding an app to `settings.PROJECT_APPS` is all that
is needed to expose its URLs and its navigation entries.
"""

from django.conf import settings
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
]

for _app_label in settings.PROJECT_APPS:
    _prefix = "" if _app_label == "core" else f"{_app_label}/"
    urlpatterns.append(path(_prefix, include(f"{_app_label}.urls")))

admin.site.site_header = f"{settings.APP_NAME} administration"
admin.site.site_title = settings.APP_NAME
