from django.contrib import admin
from django.utils import timezone

from . import models


@admin.register(models.UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "mobile", "is_parking_owner", "is_employee")
    search_fields = ("user__username", "user__first_name", "user__last_name", "mobile")


@admin.register(models.Vehicle)
class VehicleAdmin(admin.ModelAdmin):
    list_display = ("number", "owner", "vehicle_type", "is_default")
    search_fields = ("number", "owner__username")
    list_filter = ("vehicle_type",)


@admin.register(models.ParkingOwner)
class ParkingOwnerAdmin(admin.ModelAdmin):
    list_display = ("company_name", "user", "revenue_share_percentage")
    search_fields = ("company_name", "user__username")


@admin.register(models.ParkingLocation)
class ParkingLocationAdmin(admin.ModelAdmin):
    list_display = ("name", "owner", "total_slots", "base_rate_per_hour", "is_active")
    search_fields = ("name", "address")
    list_filter = ("is_active",)
    actions = ["generate_basic_slots"]

    def generate_basic_slots(self, request, queryset):
        """
        Bulk-generate slots for selected locations.

        For each location, create slots S1..S{total_slots} if they do not already exist.
        """
        created = 0
        for location in queryset:
            for index in range(1, location.total_slots + 1):
                code = f"S{index}"
                obj, was_created = models.ParkingSlot.objects.get_or_create(
                    location=location,
                    slot_code=code,
                    defaults={"status": models.ParkingSlot.STATUS_AVAILABLE},
                )
                if was_created:
                    created += 1
        self.message_user(request, f"Generated {created} slots across selected locations.")

    generate_basic_slots.short_description = "Generate S1..S{total_slots} slots for selected locations"


@admin.register(models.ParkingSlot)
class ParkingSlotAdmin(admin.ModelAdmin):
    list_display = ("slot_code", "location", "status", "vehicle_type_allowed")
    list_filter = ("location", "status", "vehicle_type_allowed")
    search_fields = ("slot_code", "location__name")
    actions = ["mark_as_maintenance", "mark_as_available"]

    def mark_as_maintenance(self, request, queryset):
        now = timezone.now()
        count = 0
        for slot in queryset:
            models.MaintenanceSlotLog.objects.create(
                slot=slot,
                start_datetime=now,
                end_datetime=None,
                reason="Marked via admin action",
                created_by=request.user if request.user.is_authenticated else None,
            )
            slot.status = models.ParkingSlot.STATUS_MAINTENANCE
            slot.save(update_fields=["status"])
            count += 1
        self.message_user(request, f"{count} slots marked as under maintenance.")

    mark_as_maintenance.short_description = "Mark selected slots as under maintenance"

    def mark_as_available(self, request, queryset):
        updated = queryset.update(status=models.ParkingSlot.STATUS_AVAILABLE)
        self.message_user(request, f"{updated} slots marked as available.")

    mark_as_available.short_description = "Mark selected slots as available"


@admin.register(models.Employee)
class EmployeeAdmin(admin.ModelAdmin):
    list_display = ("user", "location", "role")
    list_filter = ("location",)


@admin.register(models.DynamicPricingRule)
class DynamicPricingRuleAdmin(admin.ModelAdmin):
    list_display = ("location", "day_of_week", "start_time", "end_time", "multiplier")
    list_filter = ("location", "day_of_week")


@admin.register(models.CancellationPolicy)
class CancellationPolicyAdmin(admin.ModelAdmin):
    list_display = ("location", "min_minutes_before_start", "refund_percentage", "description")
    list_filter = ("location",)


@admin.register(models.Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user",
        "slot",
        "status",
        "entry_datetime_expected",
        "exit_datetime_expected",
        "amount_expected",
        "amount_paid",
    )
    list_filter = ("status", "location")
    search_fields = ("id", "user__username", "slot__slot_code")


@admin.register(models.Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ("id", "booking", "amount", "currency", "status", "created_at")
    list_filter = ("status", "currency")
    search_fields = ("gateway_txn_id",)


@admin.register(models.BookingExtension)
class BookingExtensionAdmin(admin.ModelAdmin):
    list_display = ("booking", "extra_hours", "extra_amount", "created_at")


@admin.register(models.Fine)
class FineAdmin(admin.ModelAdmin):
    list_display = ("booking", "amount", "status", "created_at", "paid_at")
    list_filter = ("status",)


@admin.register(models.MaintenanceSlotLog)
class MaintenanceSlotLogAdmin(admin.ModelAdmin):
    list_display = ("slot", "start_datetime", "end_datetime", "reason")
    list_filter = ("slot__location",)


@admin.register(models.NotificationLog)
class NotificationLogAdmin(admin.ModelAdmin):
    list_display = ("user", "notification_type", "channel", "sent_at")
    list_filter = ("notification_type", "channel")


@admin.register(models.EntryExitLog)
class EntryExitLogAdmin(admin.ModelAdmin):
    list_display = ("booking", "event_type", "timestamp", "employee")
    list_filter = ("event_type",)

