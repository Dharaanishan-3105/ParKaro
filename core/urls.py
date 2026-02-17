from django.urls import path

from . import views

app_name = "core"

urlpatterns = [
    path("", views.home, name="home"),
    path("register/", views.register, name="register"),
    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),
    path("locations/", views.locations_list, name="locations_list"),
    path("locations/<int:location_id>/", views.location_detail, name="location_detail"),
    path(
        "locations/<int:location_id>/slots/<int:slot_id>/book/",
        views.create_booking,
        name="create_booking",
    ),
    path("bookings/<int:booking_id>/", views.booking_detail, name="booking_detail"),
    path("bookings/<int:booking_id>/cancel/", views.cancel_booking, name="cancel_booking"),
    path("bookings/<int:booking_id>/extend/", views.extend_booking, name="extend_booking"),
    path("dashboard/", views.dashboard, name="dashboard"),
    path("staff/scan/", views.staff_scan_qr, name="staff_scan_qr"),
]

