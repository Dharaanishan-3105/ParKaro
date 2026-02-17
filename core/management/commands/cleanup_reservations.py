from django.core.management.base import BaseCommand
from django.utils import timezone

from core.models import Booking, ParkingSlot


class Command(BaseCommand):
    help = "Cancel expired pending bookings and release slots."

    def handle(self, *args, **options):
        now = timezone.now()
        expired_bookings = Booking.objects.filter(
            status=Booking.STATUS_PENDING_PAYMENT,
            reservation_expires_at__lt=now,
        )
        count = expired_bookings.count()
        for booking in expired_bookings:
            slot: ParkingSlot = booking.slot
            booking.status = Booking.STATUS_CANCELLED
            booking.save(update_fields=["status"])
        self.stdout.write(self.style.SUCCESS(f"Cancelled {count} expired bookings."))

