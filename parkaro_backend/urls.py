from django.contrib import admin
from django.urls import include, path
from django.conf import settings
from django.conf.urls.static import static

from core import views as core_views

urlpatterns = [
    path("admin/dashboard/", core_views.admin_dashboard, name="admin_dashboard"),
    path("admin/reports/bookings/csv/", core_views.bookings_report_csv, name="bookings_report_csv"),
    path("admin/", admin.site.urls),
    path("", include("core.urls", namespace="core")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)

