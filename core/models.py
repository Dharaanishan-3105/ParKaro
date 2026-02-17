from __future__ import annotations

from django.conf import settings
from django.contrib.auth.models import User
from django.db import models


class TimeStampedModel(models.Model):
    """Abstract base model with created/updated timestamps."""

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class UserProfile(TimeStampedModel):
    """Extended information for Django auth users."""

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    mobile = models.CharField(max_length=15, unique=True)
    address = models.TextField(blank=True)
    aadhaar_masked = models.CharField(max_length=20, blank=True, null=True)
    photo = models.ImageField(upload_to="user_photos/", blank=True, null=True)
    driving_license = models.FileField(upload_to="driving_licenses/", blank=True, null=True)
    is_parking_owner = models.BooleanField(default=False)
    is_employee = models.BooleanField(default=False)

    def __str__(self) -> str:
        return f"{self.user.get_full_name() or self.user.username}"


class Vehicle(TimeStampedModel):
    TWO_WHEELER = "2W"
    THREE_WHEELER = "3W"
    FOUR_WHEELER = "4W"

    VEHICLE_TYPE_CHOICES = [
        (TWO_WHEELER, "2-Wheeler"),
        (THREE_WHEELER, "3-Wheeler"),
        (FOUR_WHEELER, "4-Wheeler"),
    ]

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="vehicles")
    number = models.CharField(max_length=20)
    vehicle_type = models.CharField(max_length=3, choices=VEHICLE_TYPE_CHOICES)
    is_default = models.BooleanField(default=True)

    class Meta:
        unique_together = ("owner", "number")

    def __str__(self) -> str:
        return f"{self.number} ({self.get_vehicle_type_display()})"


class ParkingOwner(TimeStampedModel):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="parking_owner_profile")
    company_name = models.CharField(max_length=255)
    revenue_share_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=0)  # 0–100

    def __str__(self) -> str:
        return self.company_name


class ParkingLocation(TimeStampedModel):
    owner = models.ForeignKey(
        ParkingOwner, on_delete=models.SET_NULL, null=True, blank=True, related_name="locations"
    )
    name = models.CharField(max_length=255)
    address = models.TextField()
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    total_slots = models.PositiveIntegerField()
    base_rate_per_hour = models.DecimalField(max_digits=8, decimal_places=2)
    base_rate_per_day = models.DecimalField(max_digits=8, decimal_places=2)
    is_active = models.BooleanField(default=True)

    def __str__(self) -> str:
        return self.name


class ParkingSlot(TimeStampedModel):
    STATUS_AVAILABLE = "AVAILABLE"
    STATUS_BOOKED = "BOOKED"
    STATUS_MAINTENANCE = "MAINTENANCE"
    STATUS_TEMP_BLOCKED = "TEMP_BLOCKED"

    STATUS_CHOICES = [
        (STATUS_AVAILABLE, "Available"),
        (STATUS_BOOKED, "Booked"),
        (STATUS_MAINTENANCE, "Maintenance"),
        (STATUS_TEMP_BLOCKED, "Temporarily Blocked"),
    ]

    VEHICLE_TYPE_ALLOWED_CHOICES = Vehicle.VEHICLE_TYPE_CHOICES + [("ALL", "All Types")]

    location = models.ForeignKey(ParkingLocation, on_delete=models.CASCADE, related_name="slots")
    slot_code = models.CharField(max_length=20)
    level = models.CharField(max_length=20, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_AVAILABLE)
    vehicle_type_allowed = models.CharField(max_length=3, choices=Vehicle.VEHICLE_TYPE_CHOICES, default=Vehicle.FOUR_WHEELER)

    class Meta:
        unique_together = ("location", "slot_code")

    def __str__(self) -> str:
        return f"{self.location.name} - {self.slot_code}"


class Employee(TimeStampedModel):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="employee_profile")
    location = models.ForeignKey(ParkingLocation, on_delete=models.CASCADE, related_name="employees")
    role = models.CharField(max_length=100, default="Attendant")

    def __str__(self) -> str:
        return f"{self.user.get_full_name() or self.user.username} @ {self.location.name}"


class DynamicPricingRule(TimeStampedModel):
    location = models.ForeignKey(
        ParkingLocation, on_delete=models.CASCADE, related_name="pricing_rules", null=True, blank=True
    )
    day_of_week = models.IntegerField(null=True, blank=True)  # 0=Monday ... 6=Sunday
    start_time = models.TimeField()
    end_time = models.TimeField()
    multiplier = models.DecimalField(max_digits=5, decimal_places=2, help_text="e.g., 1.5 for 50% extra")
    notes = models.CharField(max_length=255, blank=True)

    def __str__(self) -> str:
        scope = self.location.name if self.location else "Global"
        return f"{scope} x{self.multiplier} ({self.start_time}-{self.end_time})"


class CancellationPolicy(TimeStampedModel):
    """Configurable refund rules for cancellations."""

    location = models.ForeignKey(
        ParkingLocation,
        on_delete=models.CASCADE,
        related_name="cancellation_policies",
        null=True,
        blank=True,
        help_text="Leave empty to apply globally.",
    )
    min_minutes_before_start = models.IntegerField(
        help_text="Minimum minutes before booking start time for this rule to apply."
    )
    refund_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        help_text="Refund percentage of paid amount (0–100).",
    )
    description = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["-min_minutes_before_start"]

    def __str__(self) -> str:
        scope = self.location.name if self.location else "Global"
        return f"{scope}: {self.refund_percentage}% if ≥ {self.min_minutes_before_start} min"


class Booking(TimeStampedModel):
    STATUS_PENDING_PAYMENT = "PENDING_PAYMENT"
    STATUS_CONFIRMED = "CONFIRMED"
    STATUS_CANCELLED = "CANCELLED"
    STATUS_COMPLETED = "COMPLETED"
    STATUS_NO_SHOW = "NO_SHOW"

    STATUS_CHOICES = [
        (STATUS_PENDING_PAYMENT, "Pending Payment"),
        (STATUS_CONFIRMED, "Confirmed"),
        (STATUS_CANCELLED, "Cancelled"),
        (STATUS_COMPLETED, "Completed"),
        (STATUS_NO_SHOW, "No Show"),
    ]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="bookings")
    vehicle = models.ForeignKey(Vehicle, on_delete=models.PROTECT, related_name="bookings")
    location = models.ForeignKey(ParkingLocation, on_delete=models.PROTECT, related_name="bookings")
    slot = models.ForeignKey(ParkingSlot, on_delete=models.PROTECT, related_name="bookings")

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING_PAYMENT)
    entry_datetime_expected = models.DateTimeField()
    exit_datetime_expected = models.DateTimeField()
    actual_entry_datetime = models.DateTimeField(null=True, blank=True)
    actual_exit_datetime = models.DateTimeField(null=True, blank=True)
    duration_hours_booked = models.DecimalField(max_digits=6, decimal_places=2)
    amount_expected = models.DecimalField(max_digits=10, decimal_places=2)
    amount_paid = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    reservation_expires_at = models.DateTimeField(null=True, blank=True)
    qr_code_image = models.ImageField(upload_to="booking_qr_codes/", blank=True, null=True)

    def __str__(self) -> str:
        return f"Booking #{self.id} - {self.user} - {self.slot}"


class Payment(TimeStampedModel):
    STATUS_INITIATED = "INITIATED"
    STATUS_SUCCESS = "SUCCESS"
    STATUS_FAILED = "FAILED"
    STATUS_REFUNDED = "REFUNDED"
    STATUS_PARTIAL_REFUND = "PARTIAL_REFUND"

    STATUS_CHOICES = [
        (STATUS_INITIATED, "Initiated"),
        (STATUS_SUCCESS, "Success"),
        (STATUS_FAILED, "Failed"),
        (STATUS_REFUNDED, "Refunded"),
        (STATUS_PARTIAL_REFUND, "Partial Refund"),
    ]

    booking = models.ForeignKey(Booking, on_delete=models.CASCADE, related_name="payments")
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=10, default="INR")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_INITIATED)
    gateway_txn_id = models.CharField(max_length=100, blank=True)
    payment_method = models.CharField(max_length=50, blank=True)

    def __str__(self) -> str:
        return f"Payment #{self.id} - {self.amount} {self.currency} ({self.status})"


class BookingExtension(TimeStampedModel):
    booking = models.ForeignKey(Booking, on_delete=models.CASCADE, related_name="extensions")
    extra_hours = models.DecimalField(max_digits=6, decimal_places=2)
    extra_amount = models.DecimalField(max_digits=10, decimal_places=2)
    payment = models.OneToOneField(
        Payment, on_delete=models.SET_NULL, null=True, blank=True, related_name="extension"
    )

    def __str__(self) -> str:
        return f"Extension for booking #{self.booking_id} (+{self.extra_hours}h)"


class Fine(TimeStampedModel):
    STATUS_UNPAID = "UNPAID"
    STATUS_PAID = "PAID"

    STATUS_CHOICES = [
        (STATUS_UNPAID, "Unpaid"),
        (STATUS_PAID, "Paid"),
    ]

    booking = models.ForeignKey(Booking, on_delete=models.CASCADE, related_name="fines")
    reason = models.CharField(max_length=255)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=STATUS_UNPAID)
    paid_at = models.DateTimeField(null=True, blank=True)

    def __str__(self) -> str:
        return f"Fine #{self.id} - {self.amount} ({self.status})"


class MaintenanceSlotLog(TimeStampedModel):
    slot = models.ForeignKey(ParkingSlot, on_delete=models.CASCADE, related_name="maintenance_logs")
    start_datetime = models.DateTimeField()
    end_datetime = models.DateTimeField(null=True, blank=True)
    reason = models.CharField(max_length=255, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="created_maintenance_logs"
    )

    def __str__(self) -> str:
        return f"Maintenance {self.slot} from {self.start_datetime}"


class NotificationLog(TimeStampedModel):
    TYPE_BOOKING_CONFIRMATION = "BOOKING_CONFIRMATION"
    TYPE_EXPIRY_REMINDER = "EXPIRY_REMINDER"
    TYPE_FINE_ALERT = "FINE_ALERT"

    NOTIFICATION_TYPE_CHOICES = [
        (TYPE_BOOKING_CONFIRMATION, "Booking Confirmation"),
        (TYPE_EXPIRY_REMINDER, "Expiry Reminder"),
        (TYPE_FINE_ALERT, "Fine Alert"),
    ]

    CHANNEL_EMAIL = "EMAIL"
    CHANNEL_SMS = "SMS"
    CHANNEL_IN_APP = "IN_APP"

    CHANNEL_CHOICES = [
        (CHANNEL_EMAIL, "Email"),
        (CHANNEL_SMS, "SMS"),
        (CHANNEL_IN_APP, "In-App"),
    ]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications")
    notification_type = models.CharField(max_length=50, choices=NOTIFICATION_TYPE_CHOICES)
    message = models.TextField()
    channel = models.CharField(max_length=20, choices=CHANNEL_CHOICES, default=CHANNEL_EMAIL)
    sent_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return f"{self.notification_type} to {self.user} via {self.channel}"


class EntryExitLog(TimeStampedModel):
    EVENT_ENTRY = "ENTRY"
    EVENT_EXIT = "EXIT"

    EVENT_TYPE_CHOICES = [
        (EVENT_ENTRY, "Entry"),
        (EVENT_EXIT, "Exit"),
    ]

    booking = models.ForeignKey(Booking, on_delete=models.CASCADE, related_name="entry_exit_logs")
    employee = models.ForeignKey(
        Employee, on_delete=models.SET_NULL, null=True, blank=True, related_name="entry_exit_logs"
    )
    event_type = models.CharField(max_length=10, choices=EVENT_TYPE_CHOICES)
    timestamp = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return f"{self.event_type} for booking #{self.booking_id} at {self.timestamp}"

