import uuid
from hashlib import scrypt

from django import forms
from django.core.exceptions import ValidationError

from internal_integrations.management_api.client import ManagementAPIClient
from internal_integrations.management_api.exceptions import ManagementAPIClientError
from .models import CareProviderLocation, CareRecipient, RegisteredManager


from os import getenv

class CareProviderLocationForm(forms.ModelForm):
    class Meta:
        model = CareProviderLocation
        exclude = ["id", "created_at", "updated_at"]


class RegisteredManagerForm(forms.ModelForm):
    class Meta:
        model = RegisteredManager
        exclude = ["id", "created_at", "updated_at"]
        labels = {
            "cqc_registered_manager_id": "CQC Registered Manager ID",
        }


class HighSecurityHash:
    # This version is intentionally slow, derives its security from
    # being slow, and must be used as the default.
    def encode(self, salt="", data="") -> str:
        return scrypt(
            data.encode(),
            salt=str(salt).encode(),
            n=32768,
            r=12,
            p=6,
            maxmem=2**26,
        ).hex()

class NoSecurityHash:
    # This version is fast and offers no security whatsoever, and must
    # be actively selected only for testing purposes.
    def encode(self, salt="", data="") -> str:
        return scrypt(
            data.encode(),
            salt=str(salt).encode(),
            n=16,
            r=12,
            p=1,
        ).hex()


class CareRecipientForm(forms.ModelForm):
    given_name = forms.CharField(
        max_length=64,
        required=True,
        label="Given Names",
        help_text="enter all given (first and middle) names, separated by spaces, e.g. Lavina Maxine",
    )
    family_name = forms.CharField(max_length=64, required=True, label="Family Name")
    nhs_number = forms.CharField(
        max_length=12, required=True, label="NHS Number", help_text="e.g. 999 999 9999"
    )
    birth_date = forms.DateField(
        required=True, label="Birth Date", help_text="e.g. 1998-01-23"
    )

    class Meta:
        model = CareRecipient
        exclude = ["id", "created_at", "updated_at"]

    def clean(self):
        if self.errors:
            return

        self.cleaned_data["nhs_number"] = "".join(
            self.cleaned_data["nhs_number"].split()
        )
        self.cleaned_data["nhs_number_hash"] = self._generate_nhs_number_hash()
        already_existing_care_recipient = CareRecipient.objects.filter(
            nhs_number_hash=self.cleaned_data["nhs_number_hash"]
        )
        if already_existing_care_recipient:
            raise ValidationError(
                f"Care recipient with this NHS number already exists in the database (with provider reference ID "
                f"{already_existing_care_recipient[0].provider_reference_id})"
            )

        self.cleaned_data["given_name"] = [
            name.strip() for name in self.cleaned_data["given_name"].split()
        ]
        self.cleaned_data["subscription_id"] = self._create_subscription()
        return super().clean()

    def save(self, commit: bool = True):
        self.instance.subscription_id = self.cleaned_data["subscription_id"]
        self.instance.nhs_number_hash = self.cleaned_data["nhs_number_hash"]
        return super().save(commit=commit)

    def _create_subscription(self) -> uuid.UUID:
        try:
            return ManagementAPIClient().create_subscription(
                patient_given_name=self.cleaned_data["given_name"],
                patient_family_name=self.cleaned_data["family_name"],
                nhs_number=self.cleaned_data["nhs_number"],
                birth_date=self.cleaned_data["birth_date"],
            )
        except ManagementAPIClientError as ex:
            raise ValidationError(str(ex))

    def _generate_nhs_number_hash(self) -> str:
        # https://nhsx.github.io/il-hans-infrastructure/adrs/003-Do-not-use-NEMS-or-MESH
        if getenv("STUPIDLY_HOBBLE_SECURITY") == "I_AM_AN_IDIOT_YES_I_REALLY_MEAN_IT":
            hasher = NoSecurityHash()
        else:
            hasher = HighSecurityHash()
        return hasher.encode(data=self.cleaned_data["nhs_number"],
                             salt=self.cleaned_data["birth_date"])
