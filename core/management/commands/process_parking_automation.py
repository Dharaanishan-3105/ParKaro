from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone
from django.conf import settings
from django.core.mail import send_mail

from core.models import Booking, Fine, NotificationLog


class Command(BaseCommand):
    help = "Process overtime detection, fines, and reminders."

    def handle(self, *args, **options):
        now = timezone.now()

        # Reminders for bookings ending in next 30 minutes
        reminder_window_start = now
        reminder_window_end = now + timedelta(minutes=30)

        reminder_bookings = Booking.objects.filter(
            status=Booking.STATUS_CONFIRMED,
            exit_datetime_expected__gte=reminder_window_start,
            exit_datetime_expected__lte=reminder_window_end,
        )

        for booking in reminder_bookings:
            if booking.user.email:
                subject = f"ParKaro Parking Reminder #{booking.id}"
                message = (
                    f"Your parking at {booking.location.name} (slot {booking.slot.slot_code}) "
                    f"is ending at {booking.exit_datetime_expected}.\n"
                    "Please extend your booking if needed to avoid fines."
                )
                send_mail(
                    subject,
                    message,
                    settings.DEFAULT_FROM_EMAIL,
                    [booking.user.email],
                    fail_silently=True,
                )
            NotificationLog.objects.create(
                user=booking.user,
                notification_type=NotificationLog.TYPE_EXPIRY_REMINDER,
                message="Parking end reminder sent.",
                channel=NotificationLog.CHANNEL_EMAIL,
            )

        # Overtime detection and fines
        overtime_bookings = Booking.objects.filter(
            status=Booking.STATUS_CONFIRMED,
            exit_datetime_expected__lt=now,
        )

        for booking in overtime_bookings:
            has_unpaid_fine = booking.fines.filter(status=Fine.STATUS_UNPAID).exists()
            if has_unpaid_fine:
                continue

            # Flat overtime fine for simplicity
            fine_amount = booking.location.base_rate_per_hour
            fine = Fine.objects.create(
                booking=booking,
                reason="Overstay beyond booked time",
                amount=fine_amount,
                status=Fine.STATUS_UNPAID,
            )

            if booking.user.email:
                subject = f"ParKaro Overtime Fine #{fine.id}"
                message = (
                    f"You have overstayed your parking at {booking.location.name} "
                    f"(slot {booking.slot.slot_code}). A fine of ₹{fine.amount} has been generated."
                )
                send_mail(
                    subject,
                    message,
                    settings.DEFAULT_FROM_EMAIL,
                    [booking.user.email],
                    fail_silently=True,
                )

            NotificationLog.objects.create(
                user=booking.user,
                notification_type=NotificationLog.TYPE_FINE_ALERT,
                message=f"Overtime fine of ₹{fine.amount} created.",
                channel=NotificationLog.CHANNEL_EMAIL,
            )

        self.stdout.write(self.style.SUCCESS("Processed reminders and overtime fines."))

