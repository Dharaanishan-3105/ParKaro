<p align="center">
  <img src="static/logo.jpeg" alt="ParKaro logo" width="130" />
</p>

<p align="center">
  <b>ParKaro – Smart Parking for Busy Cities</b><br />
  Real‑time slot discovery, QR‑based entry, and business analytics for parking operators.
</p>

---

## 1. What is ParKaro?

ParKaro is a full‑stack smart parking system built with **Django + MySQL**.

- For **drivers**: search nearby parking, see live slot availability, reserve a space, pay online, and enter using a **QR ticket**.
- For **parking owners / admins**: configure locations and slots, define pricing rules and refund policies, and view **revenue & utilization analytics** from a central dashboard.

The project is structured as a production‑style web app: clear domain models, layered views, admin automation, and management commands.


## 2. High‑level architecture

### 2.1 Logical modules

- **User Module**
  - Registration & login (email / mobile / username)
  - Profile (address, Aadhaar‑masked, photo, driving license)
  - Vehicle management (number + type: 2W / 3W / 4W)
  - Location search & slot booking
  - Booking dashboard (active, history, tickets, payments)
  - Booking extension, cancellation & refunds

- **Admin / Parking Owner Module**
  - Manage locations, slots, owners, employees
  - Configure dynamic pricing rules (per time, day, location)
  - Configure cancellation policies (time windows + refund %)
  - View analytics dashboard (KPIs, bookings per day, revenue by location, peak hours)
  - Export bookings to CSV

- **Parking Automation Module**
  - Reservation cleanup (expired pending bookings)
  - Overtime detection & fine generation
  - Expiry reminders
  - Entry / exit logging via QR code scanning


### 2.2 Data model overview (simplified)

- `UserProfile` – extends Django user with mobile, address, Aadhaar‑masked, photo, driving license, owner/employee flags.
- `Vehicle` – vehicle number, type (2W/3W/4W), belongs to a user.
- `ParkingOwner` – business owner linked to a user; has revenue share settings.
- `ParkingLocation` – name, address, coordinates, total slots, base hourly/daily rates, owner.
- `ParkingSlot` – physical slot in a location (code, level, status, allowed vehicle type).
- `Booking` – user + vehicle + location + slot, expected & actual times, amounts, QR code, reservation expiry.
- `Payment` – booking payment with status (initiated / success / failed / refunded).
- `BookingExtension` – extra booked hours + amount for an existing booking.
- `Fine` – overtime or other penalties, with status (unpaid / paid).
- `DynamicPricingRule` – time‑based multiplier applied on top of base rates.
- `CancellationPolicy` – refund % based on how long before start the user cancels.
- `MaintenanceSlotLog` – maintenance windows for slots (start/end, reason).
- `NotificationLog` – record of emails/notifications sent (confirmation, reminders, fines).
- `EntryExitLog` – entry/exit events tied to bookings (for QR validation and audits).


### 2.3 Request flow examples

- **Booking a slot**
  1. User selects location & slot (`location_detail` view).
  2. User submits entry/exit times (`create_booking` view + `BookingForm`).
  3. Backend checks:
     - maintenance windows (no booking during maintenance)
     - overlapping confirmed bookings (no double‑booking)
  4. Fee is calculated using base rate, dynamic pricing rules, and daily threshold.
  5. `Booking` created as `PENDING_PAYMENT`, dummy `Payment` created and marked `SUCCESS`.
  6. Booking updated to `CONFIRMED` and QR code image generated.
  7. Email confirmation sent + `NotificationLog` entry created.

- **Extending a booking**
  1. User selects “Extend” from dashboard.
  2. New exit time is validated (after current exit, no overlaps).
  3. Extra fee is calculated using the same pricing logic.
  4. Extra `Payment` + `BookingExtension` created and booking’s totals updated.

- **Cancelling a booking**
  1. User opens “Cancel booking” before start time.
  2. System finds applicable `CancellationPolicy` (per‑location or global).
  3. Refund amount is calculated; a refund `Payment` is recorded.
  4. Booking marked as `CANCELLED` and user notified.


## 3. Tech stack

- **Backend**: Django 5, Python 3, MySQL (`mysqlclient`)
- **Frontend**: Django templates + custom CSS (`static/css/styles.css`)
- **Media / QR**: `Pillow`, `qrcode`
- **Maps**: Google Maps JavaScript API (optional, via `GOOGLE_MAPS_API_KEY`)


## 4. Project layout

- `manage.py` – standard Django management entry point  
- `run.py` – helper script to start the dev server and auto‑open the browser

- `parkaro_backend/`
  - `settings.py` – Django + MySQL configuration, static/media settings
  - `urls.py` – project‑level routing (`admin/`, `admin/dashboard/`, `core/`)

- `core/` (main app)
  - `models.py` – all domain models for users, parking, bookings, payments, pricing, maintenance, logs
  - `views.py` – user flows (home, auth, booking, dashboards), admin analytics, staff scan, CSV export
  - `forms.py` – registration, login, booking
  - `admin.py` – Django admin registrations + batch actions (generate slots, maintenance toggles)
  - `urls.py` – routes for user and staff endpoints
  - `management/commands/`
    - `cleanup_reservations.py` – cancel expired pending bookings
    - `process_parking_automation.py` – reminders & fines
    - `export_bookings_csv.py` – CLI export helper

- `templates/`
  - `base.html` – base layout (header with logo + nav, footer)
  - `core/home.html` – landing page with value proposition and “How it works”
  - `core/login.html`, `core/register.html` – split‑screen auth with product copy
  - `core/dashboard.html` – user bookings & payments overview
  - `core/admin_dashboard.html` – admin KPIs & reports
  - `core/locations_list.html`, `core/location_detail.html` – search, map, and slot layout
  - `core/create_booking.html`, `core/booking_detail.html`, `core/extend_booking.html`, `core/cancel_booking.html`
  - `core/staff_scan_qr.html` – staff entry/exit page

- `static/`
  - `css/styles.css` – layout, typography, buttons, and card styling
  - `logo.jpeg` – ParKaro logo used in the header and README


## 5. Quick start

```bash
git clone <your-repo-url> ParKaro
cd ParKaro

python -m pip install -r requirements.txt

# Configure MySQL credentials in parkaro_backend/settings.py
python manage.py makemigrations
python manage.py migrate
python manage.py createsuperuser

python run.py   # or: python manage.py runserver
```

Open `http://127.0.0.1:8000/` in your browser to see the app.

Optional: set `GOOGLE_MAPS_API_KEY` to enable embedded maps on the location pages.


## 6. Useful URLs during development

- User home: `http://127.0.0.1:8000/`
- User dashboard: `http://127.0.0.1:8000/dashboard/`
- Admin panel: `http://127.0.0.1:8000/admin/`
- Admin analytics: `http://127.0.0.1:8000/admin/dashboard/`
- Staff scan (entry/exit): `http://127.0.0.1:8000/staff/scan/`

With this setup, you can demo ParKaro end‑to‑end: from a user booking a slot and scanning a QR at entry/exit, to an admin viewing live revenue charts and exporting reports. 

