from datetime import timedelta
import csv

from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.db import models
from django.db.models import Count, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.conf import settings
from django.core.mail import send_mail
from django.http import HttpResponse

from .forms import BookingForm, LoginForm, UserRegistrationForm
from .models import (
    Booking,
    BookingExtension,
    CancellationPolicy,
    DynamicPricingRule,
    Fine,
    MaintenanceSlotLog,
    NotificationLog,
    ParkingLocation,
    ParkingSlot,
    Payment,
    Vehicle,
)


def home(request):
    """Landing page with quick links."""
    locations = ParkingLocation.objects.filter(is_active=True).order_by("name")[:6]
    return render(request, "core/home.html", {"locations": locations})


def register(request):
    if request.method == "POST":
        form = UserRegistrationForm(request.POST, request.FILES)
        if form.is_valid():
            user = form.save()

            # Optional welcome / verification email
            if user.email:
                send_mail(
                    "Welcome to ParKaro",
                    "Thank you for registering with ParKaro. Your account is ready to use.",
                    settings.DEFAULT_FROM_EMAIL,
                    [user.email],
                    fail_silently=True,
                )

            login(request, user)
            messages.success(request, "Registration successful. Welcome to ParKaro!")
            return redirect("core:dashboard")
    else:
        form = UserRegistrationForm()
    return render(request, "core/register.html", {"form": form})


def login_view(request):
    if request.method == "POST":
        form = LoginForm(request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)
            messages.success(request, "Logged in successfully.")
            return redirect("core:dashboard")
    else:
        form = LoginForm()
    return render(request, "core/login.html", {"form": form})


def logout_view(request):
    logout(request)
    messages.info(request, "You have been logged out.")
    return redirect("core:home")


def locations_list(request):
    """List and search active parking locations, with basic stats."""
    query = request.GET.get("q", "")
    qs = ParkingLocation.objects.filter(is_active=True).annotate(
        available_slots=Count(
            "slots",
            filter=models.Q(slots__status=ParkingSlot.STATUS_AVAILABLE),
        )
    )
    if query:
        qs = qs.filter(name__icontains=query)
    locations = qs.order_by("name")

    return render(
        request,
        "core/locations_list.html",
        {
            "locations": locations,
            "query": query,
            "google_maps_api_key": settings.GOOGLE_MAPS_API_KEY,
        },
    )


def location_detail(request, location_id):
    """Show slots for a parking location with real-time availability."""
    location = get_object_or_404(ParkingLocation, pk=location_id, is_active=True)
    slots = list(ParkingSlot.objects.filter(location=location).order_by("slot_code"))

    now = timezone.now()

    for slot in slots:
        # Maintenance status
        has_maintenance = MaintenanceSlotLog.objects.filter(
            slot=slot,
            start_datetime__lte=now,
        ).filter(models.Q(end_datetime__isnull=True) | models.Q(end_datetime__gte=now)).exists()

        if has_maintenance:
            slot.current_status = ParkingSlot.STATUS_MAINTENANCE
            continue

        # Booking overlapping now
        has_active_booking = Booking.objects.filter(
            slot=slot,
            status=Booking.STATUS_CONFIRMED,
            entry_datetime_expected__lte=now,
            exit_datetime_expected__gte=now,
        ).exists()

        slot.current_status = ParkingSlot.STATUS_BOOKED if has_active_booking else ParkingSlot.STATUS_AVAILABLE

    return render(request, "core/location_detail.html", {"location": location, "slots": slots})


@login_required
def create_booking(request, location_id, slot_id):
    """Create a booking for a specific slot."""
    location = get_object_or_404(ParkingLocation, pk=location_id, is_active=True)
    slot = get_object_or_404(ParkingSlot, pk=slot_id, location=location)

    # Use user's default vehicle
    vehicle = Vehicle.objects.filter(owner=request.user, is_default=True).first()

    if request.method == "POST":
        form = BookingForm(request.POST, user=request.user, location=location, slot=slot)
        if form.is_valid():
            booking = form.save(commit=False)
            booking.user = request.user
            booking.location = location
            booking.slot = slot
            booking.vehicle = vehicle

            # Check for overlapping bookings on this slot
            overlapping = Booking.objects.filter(
                slot=slot,
                status=Booking.STATUS_CONFIRMED,
                entry_datetime_expected__lt=booking.exit_datetime_expected,
                exit_datetime_expected__gt=booking.entry_datetime_expected,
            ).exists()
            if overlapping:
                messages.error(request, "This slot is already booked for the selected time window.")
                return redirect("core:location_detail", location_id=location.id)

            # Duration and fee with simple dynamic pricing
            entry = booking.entry_datetime_expected
            exit_ = booking.exit_datetime_expected
            duration_hours = (exit_ - entry).total_seconds() / 3600
            booking.duration_hours_booked = round(duration_hours, 2)

            base_rate = float(location.base_rate_per_hour)
            multiplier = 1.0

            rules = DynamicPricingRule.objects.filter(location=location, day_of_week=entry.weekday())
            for rule in rules:
                if rule.start_time <= entry.time() <= rule.end_time:
                    multiplier = max(multiplier, float(rule.multiplier))

            # Simple daily threshold: if > 8 hours, use daily rate
            effective_rate = base_rate * multiplier
            if booking.duration_hours_booked >= 8:
                days = (booking.duration_hours_booked / 24) or 1
                booking.amount_expected = float(location.base_rate_per_day) * round(days)
            else:
                booking.amount_expected = booking.duration_hours_booked * effective_rate

            # Initial pending booking and dummy payment
            booking.status = Booking.STATUS_PENDING_PAYMENT
            booking.amount_paid = 0
            booking.reservation_expires_at = timezone.now() + timedelta(minutes=10)
            booking.save()

            payment = Payment.objects.create(
                booking=booking,
                amount=booking.amount_expected,
                currency="INR",
                status=Payment.STATUS_SUCCESS,
                payment_method="DUMMY_GATEWAY",
            )

            booking.status = Booking.STATUS_CONFIRMED
            booking.amount_paid = booking.amount_expected
            booking.reservation_expires_at = None
            booking.save()

            # Generate QR code file
            from io import BytesIO

            import qrcode
            from django.core.files.base import ContentFile

            qr_data = f"BOOKING:{booking.id}"
            img = qrcode.make(qr_data)
            buffer = BytesIO()
            img.save(buffer, format="PNG")
            file_name = f"booking_{booking.id}_qr.png"
            booking.qr_code_image.save(file_name, ContentFile(buffer.getvalue()))

            # Email ticket
            if request.user.email:
                subject = f"ParKaro Booking Confirmation #{booking.id}"
                message = (
                    f"Your booking is confirmed.\n\n"
                    f"Location: {booking.location.name}\n"
                    f"Slot: {booking.slot.slot_code}\n"
                    f"Entry: {booking.entry_datetime_expected}\n"
                    f"Exit: {booking.exit_datetime_expected}\n"
                    f"Amount: ₹{booking.amount_expected}\n"
                )
                send_mail(
                    subject,
                    message,
                    settings.DEFAULT_FROM_EMAIL,
                    [request.user.email],
                    fail_silently=True,
                )

            messages.success(request, "Booking created successfully and ticket sent to your email.")
            return redirect("core:booking_detail", booking_id=booking.id)
    else:
        form = BookingForm(user=request.user, location=location, slot=slot)

    return render(
        request,
        "core/create_booking.html",
        {"form": form, "location": location, "slot": slot, "vehicle": vehicle},
    )


@login_required
def booking_detail(request, booking_id):
    booking = get_object_or_404(Booking, pk=booking_id, user=request.user)
    return render(
        request,
        "core/booking_detail.html",
        {
            "booking": booking,
            "now": timezone.now(),
        },
    )


@login_required
def dashboard(request):
    """User dashboard showing active and past bookings."""
    active_bookings = Booking.objects.filter(
        user=request.user, status__in=[Booking.STATUS_CONFIRMED]
    ).order_by("-entry_datetime_expected")
    past_bookings = Booking.objects.filter(
        user=request.user, status__in=[Booking.STATUS_COMPLETED, Booking.STATUS_CANCELLED]
    ).order_by("-entry_datetime_expected")[:10]
    return render(
        request,
        "core/dashboard.html",
        {
            "active_bookings": active_bookings,
            "past_bookings": past_bookings,
            "recent_payments": Payment.objects.filter(
                booking__user=request.user
            ).order_by("-created_at")[:10],
        },
    )


@staff_member_required
def admin_dashboard(request):
    """Analytics dashboard with KPIs and simple aggregates."""
    today = timezone.localdate()
    start_30 = today - timedelta(days=29)
    start_week = today - timedelta(days=6)
    start_month = today.replace(day=1)

    total_bookings = Booking.objects.count()
    total_revenue = Payment.objects.filter(status=Payment.STATUS_SUCCESS).aggregate(
        total=Sum("amount")
    )["total"] or 0
    active_locations = ParkingLocation.objects.filter(is_active=True).count()
    active_slots = ParkingSlot.objects.filter(status=ParkingSlot.STATUS_AVAILABLE).count()
    total_unpaid_fines = Fine.objects.filter(status=Fine.STATUS_UNPAID).aggregate(
        total=Sum("amount")
    )["total"] or 0

    # KPIs by period
    def revenue_for_range(start_date, end_date):
        return (
            Payment.objects.filter(
                status=Payment.STATUS_SUCCESS,
                created_at__date__gte=start_date,
                created_at__date__lte=end_date,
            ).aggregate(total=Sum("amount"))["total"]
            or 0
        )

    kpi_today_revenue = revenue_for_range(today, today)
    kpi_week_revenue = revenue_for_range(start_week, today)
    kpi_month_revenue = revenue_for_range(start_month, today)

    # Bookings per day (last 30 days)
    bookings_per_day = (
        Booking.objects.filter(entry_datetime_expected__date__gte=start_30)
        .extra(select={"day": "date(entry_datetime_expected)"})
        .values("day")
        .annotate(count=Count("id"))
        .order_by("day")
    )

    # Revenue per location
    revenue_per_location = (
        Payment.objects.filter(status=Payment.STATUS_SUCCESS)
        .values("booking__location__name")
        .annotate(total=Sum("amount"))
        .order_by("-total")
    )

    # Peak hours
    peak_hours = (
        Booking.objects.extra(select={"hour": "extract(hour from entry_datetime_expected)"})
        .values("hour")
        .annotate(count=Count("id"))
        .order_by("hour")
    )

    bookings_by_location = (
        Booking.objects.values("location__name")
        .annotate(count=Count("id"), revenue=Sum("amount_paid"))
        .order_by("-count")
    )

    locations_for_filter = ParkingLocation.objects.filter(is_active=True).order_by("name")

    context = {
        "total_bookings": total_bookings,
        "total_revenue": total_revenue,
        "active_locations": active_locations,
        "active_slots": active_slots,
        "total_unpaid_fines": total_unpaid_fines,
        "kpi_today_revenue": kpi_today_revenue,
        "kpi_week_revenue": kpi_week_revenue,
        "kpi_month_revenue": kpi_month_revenue,
        "bookings_per_day": bookings_per_day,
        "revenue_per_location": revenue_per_location,
        "peak_hours": peak_hours,
        "bookings_by_location": bookings_by_location,
        "locations_for_filter": locations_for_filter,
    }
    return render(request, "core/admin_dashboard.html", context)


@staff_member_required
def bookings_report_csv(request):
    """Export bookings to CSV with optional filters."""
    start = request.GET.get("start")
    end = request.GET.get("end")
    location_id = request.GET.get("location")

    qs = Booking.objects.select_related("location", "slot", "user")

    from django.utils.dateparse import parse_date

    if start:
        start_date = parse_date(start)
        if start_date:
            qs = qs.filter(entry_datetime_expected__date__gte=start_date)
    if end:
        end_date = parse_date(end)
        if end_date:
            qs = qs.filter(entry_datetime_expected__date__lte=end_date)
    if location_id:
        qs = qs.filter(location_id=location_id)

    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="bookings_report.csv"'

    writer = csv.writer(response)
    writer.writerow(
        [
            "ID",
            "User",
            "Location",
            "Slot",
            "Status",
            "Entry",
            "Exit",
            "Amount Expected",
            "Amount Paid",
        ]
    )
    for b in qs:
        writer.writerow(
            [
                b.id,
                b.user.username,
                b.location.name,
                b.slot.slot_code,
                b.status,
                b.entry_datetime_expected,
                b.exit_datetime_expected,
                b.amount_expected,
                b.amount_paid,
            ]
        )

    return response


@staff_member_required
def staff_scan_qr(request):
    """Allow staff to register entry/exit using booking code/ID."""
    booking = None
    message = ""
    if request.method == "POST":
        code = request.POST.get("code", "").strip()
        if code.startswith("BOOKING:"):
            code = code.split("BOOKING:", 1)[1]
        try:
            booking_id = int(code)
            booking = Booking.objects.get(id=booking_id)
        except (ValueError, Booking.DoesNotExist):
            messages.error(request, "Invalid booking code.")
            return redirect("core:staff_scan_qr")

        now = timezone.now()
        if booking.actual_entry_datetime is None:
            booking.actual_entry_datetime = now
            booking.save(update_fields=["actual_entry_datetime"])
            from .models import EntryExitLog, Employee

            EntryExitLog.objects.create(
                booking=booking,
                employee=None,
                event_type=EntryExitLog.EVENT_ENTRY,
            )
            message = "Entry recorded."
        elif booking.actual_exit_datetime is None:
            booking.actual_exit_datetime = now
            booking.status = Booking.STATUS_COMPLETED
            booking.save(update_fields=["actual_exit_datetime", "status"])
            from .models import EntryExitLog, Employee

            EntryExitLog.objects.create(
                booking=booking,
                employee=None,
                event_type=EntryExitLog.EVENT_EXIT,
            )
            message = "Exit recorded and booking marked as completed."
        else:
            message = "Booking already has entry and exit recorded."

        messages.info(request, message)
        return redirect("core:staff_scan_qr")

    return render(request, "core/staff_scan_qr.html")


@login_required
def extend_booking(request, booking_id):
    """User-initiated extension of a confirmed booking."""
    booking = get_object_or_404(Booking, pk=booking_id, user=request.user, status=Booking.STATUS_CONFIRMED)

    if request.method == "POST":
        new_exit_str = request.POST.get("new_exit")
        if not new_exit_str:
            messages.error(request, "Please select a new exit time.")
            return redirect("core:extend_booking", booking_id=booking.id)

        from django.utils.dateparse import parse_datetime

        new_exit = parse_datetime(new_exit_str)
        if not new_exit or new_exit <= booking.exit_datetime_expected:
            messages.error(request, "New exit time must be after current exit time.")
            return redirect("core:extend_booking", booking_id=booking.id)

        # Check for overlapping bookings on this slot
        overlapping = Booking.objects.filter(
            slot=booking.slot,
            status=Booking.STATUS_CONFIRMED,
            entry_datetime_expected__lt=new_exit,
            exit_datetime_expected__gt=booking.exit_datetime_expected,
        ).exclude(id=booking.id).exists()
        if overlapping:
            messages.error(request, "Slot is not available for the selected extension window.")
            return redirect("core:extend_booking", booking_id=booking.id)

        extra_hours = (new_exit - booking.exit_datetime_expected).total_seconds() / 3600
        extra_hours = round(extra_hours, 2)

        base_rate = float(booking.location.base_rate_per_hour)
        multiplier = 1.0
        rules = DynamicPricingRule.objects.filter(location=booking.location, day_of_week=new_exit.weekday())
        for rule in rules:
            if rule.start_time <= new_exit.time() <= rule.end_time:
                multiplier = max(multiplier, float(rule.multiplier))

        effective_rate = base_rate * multiplier
        extra_amount = extra_hours * effective_rate

        payment = Payment.objects.create(
            booking=booking,
            amount=extra_amount,
            currency="INR",
            status=Payment.STATUS_SUCCESS,
            payment_method="DUMMY_GATEWAY",
        )

        BookingExtension.objects.create(
            booking=booking,
            extra_hours=extra_hours,
            extra_amount=extra_amount,
            payment=payment,
        )

        booking.exit_datetime_expected = new_exit
        booking.amount_expected += extra_amount
        booking.amount_paid += extra_amount
        booking.save(update_fields=["exit_datetime_expected", "amount_expected", "amount_paid"])

        messages.success(request, "Booking extended successfully.")
        return redirect("core:booking_detail", booking_id=booking.id)

    return render(request, "core/extend_booking.html", {"booking": booking})


@login_required
def cancel_booking(request, booking_id):
    """Allow users to cancel a future booking and receive refund as per policy."""
    booking = get_object_or_404(
        Booking,
        pk=booking_id,
        user=request.user,
        status=Booking.STATUS_CONFIRMED,
    )
    now = timezone.now()
    if booking.entry_datetime_expected <= now:
        messages.error(request, "You can only cancel bookings before the start time.")
        return redirect("core:booking_detail", booking_id=booking.id)

    minutes_before = (booking.entry_datetime_expected - now).total_seconds() / 60

    # Find best matching cancellation policy
    policy = (
        CancellationPolicy.objects.filter(
            models.Q(location=booking.location) | models.Q(location__isnull=True),
            min_minutes_before_start__lte=minutes_before,
        )
        .order_by("-min_minutes_before_start")
        .first()
    )

    refund_percentage = float(policy.refund_percentage) if policy else 0.0
    refundable_amount = booking.amount_paid * (refund_percentage / 100.0)

    if request.method == "POST":
        if refundable_amount > 0:
            Payment.objects.create(
                booking=booking,
                amount=refundable_amount,
                currency="INR",
                status=Payment.STATUS_REFUNDED,
                payment_method="REFUND",
            )
            booking.amount_paid -= refundable_amount
            if booking.amount_paid < 0:
                booking.amount_paid = 0

        booking.status = Booking.STATUS_CANCELLED
        booking.save(update_fields=["status", "amount_paid"])

        if booking.user.email:
            send_mail(
                f"ParKaro Booking #{booking.id} cancelled",
                f"Your booking at {booking.location.name} has been cancelled.\n"
                f"Refund applied: ₹{refundable_amount:.2f}",
                settings.DEFAULT_FROM_EMAIL,
                [booking.user.email],
                fail_silently=True,
            )

        NotificationLog.objects.create(
            user=booking.user,
            notification_type=NotificationLog.TYPE_BOOKING_CONFIRMATION,
            message=f"Booking #{booking.id} cancelled with refund ₹{refundable_amount:.2f}.",
            channel=NotificationLog.CHANNEL_IN_APP,
        )

        messages.success(request, "Booking cancelled as per refund policy.")
        return redirect("core:dashboard")

    return render(
        request,
        "core/cancel_booking.html",
        {
            "booking": booking,
            "minutes_before": int(minutes_before),
            "refund_percentage": refund_percentage,
            "refundable_amount": refundable_amount,
        },
    )

