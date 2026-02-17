import csv
from datetime import datetime

from django.core.management.base import BaseCommand

from core.models import Booking


class Command(BaseCommand):
    help = "Export all bookings to CSV (stdout)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--start",
            type=str,
            help="Start date (YYYY-MM-DD)",
        )
        parser.add_argument(
            "--end",
            type=str,
            help="End date (YYYY-MM-DD)",
        )

    def handle(self, *args, **options):
        qs = Booking.objects.all().select_related("location", "slot", "user")

        if options.get("start"):
            start = datetime.strptime(options["start"], "%Y-%m-%d")
            qs = qs.filter(entry_datetime_expected__date__gte=start.date())
        if options.get("end"):
            end = datetime.strptime(options["end"], "%Y-%m-%d")
            qs = qs.filter(entry_datetime_expected__date__lte=end.date())

        writer = csv.writer(self.stdout)
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

