from __future__ import annotations

from django import forms
from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth.password_validation import validate_password

from .models import Booking, ParkingLocation, ParkingSlot, UserProfile, Vehicle

User = get_user_model()


class UserRegistrationForm(forms.ModelForm):
    """Registration form capturing user + profile + primary vehicle."""

    password1 = forms.CharField(label="Password", widget=forms.PasswordInput)
    password2 = forms.CharField(label="Confirm password", widget=forms.PasswordInput)

    mobile = forms.CharField(label="Mobile number")
    address = forms.CharField(label="Address", widget=forms.Textarea, required=False)
    aadhaar = forms.CharField(label="Aadhaar number (optional)", required=False)
    photo = forms.ImageField(required=False)
    driving_license = forms.FileField(required=False)

    vehicle_number = forms.CharField(label="Vehicle number")
    vehicle_type = forms.ChoiceField(choices=Vehicle.VEHICLE_TYPE_CHOICES, label="Vehicle type")

    class Meta:
        model = User
        fields = ["username", "email", "first_name", "last_name"]

    def clean_password2(self):
        password1 = self.cleaned_data.get("password1")
        password2 = self.cleaned_data.get("password2")
        if password1 and password2 and password1 != password2:
            raise forms.ValidationError("Passwords do not match.")
        validate_password(password2)
        return password2

    def clean_aadhaar(self):
        aadhaar = self.cleaned_data.get("aadhaar", "").strip()
        if not aadhaar:
            return ""
        # Simple masking: keep last 4 digits
        last4 = aadhaar[-4:]
        return f"XXXX-XXXX-{last4}"

    def save(self, commit: bool = True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data["password1"])
        if commit:
            user.save()

            # Create profile
            profile = UserProfile.objects.create(
                user=user,
                mobile=self.cleaned_data["mobile"],
                address=self.cleaned_data.get("address", ""),
                aadhaar_masked=self.cleaned_data.get("aadhaar") or None,
                photo=self.cleaned_data.get("photo"),
                driving_license=self.cleaned_data.get("driving_license"),
            )

            # Primary vehicle
            Vehicle.objects.create(
                owner=user,
                number=self.cleaned_data["vehicle_number"],
                vehicle_type=self.cleaned_data["vehicle_type"],
                is_default=True,
            )
        return user


class LoginForm(forms.Form):
    """Login with email, mobile or username."""

    identifier = forms.CharField(label="Email / Mobile / Username")
    password = forms.CharField(widget=forms.PasswordInput)

    def __init__(self, *args, **kwargs):
        self.user_cache = None
        super().__init__(*args, **kwargs)

    def clean(self):
        cleaned_data = super().clean()
        identifier = cleaned_data.get("identifier")
        password = cleaned_data.get("password")

        if identifier and password:
            user = (
                User.objects.filter(username=identifier).first()
                or User.objects.filter(email=identifier).first()
                or User.objects.filter(userprofile__mobile=identifier).first()
            )
            if not user:
                raise forms.ValidationError("Invalid credentials.")

            self.user_cache = authenticate(username=user.username, password=password)
            if self.user_cache is None:
                raise forms.ValidationError("Invalid credentials.")
        return cleaned_data

    def get_user(self):
        return self.user_cache


class BookingForm(forms.ModelForm):
    """Basic booking form for selecting time window and slot."""

    class Meta:
        model = Booking
        fields = ["entry_datetime_expected", "exit_datetime_expected"]
        widgets = {
            "entry_datetime_expected": forms.DateTimeInput(attrs={"type": "datetime-local"}),
            "exit_datetime_expected": forms.DateTimeInput(attrs={"type": "datetime-local"}),
        }

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop("user", None)
        self.location = kwargs.pop("location", None)
        self.slot = kwargs.pop("slot", None)
        super().__init__(*args, **kwargs)

    def clean(self):
        cleaned_data = super().clean()
        entry = cleaned_data.get("entry_datetime_expected")
        exit_ = cleaned_data.get("exit_datetime_expected")
        if entry and exit_ and exit_ <= entry:
            raise forms.ValidationError("Exit time must be after entry time.")
        return cleaned_data

