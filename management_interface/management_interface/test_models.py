from django.core.exceptions import ValidationError
from django.test import TestCase

from management_interface.models import (
    CareProviderLocation,
    CareRecipient,
    RegisteredManager,
)


def assert_rejects_email(obj, email):
    obj.email = email
    try:
        obj.full_clean()
    except ValidationError as e:
        assert "email" in e.message_dict
        assert "Enter an nhs.net email address" in e.message_dict["email"]


def assert_accepts_email(obj, email):
    obj.email = email
    try:
        obj.full_clean()
    except ValidationError as e:
        assert "email" not in e.message_dict


class RegisteredManagerTests(TestCase):
    def test_rejects_bad_email_domain(self):
        assert_rejects_email(RegisteredManager(), "bad-man@invalid-domain.evil")

    def test_accepts_safe_email_domain(self):
        assert_accepts_email(RegisteredManager(), "good-dr@nhs.net")

    def test_rejects_invalid_email_address_format(self):
        manager = RegisteredManager(email="notanemail.address")
        try:
            manager.full_clean()
        except ValidationError as e:
            assert "email" in e.message_dict

    def test_accepts_data_fields(self):
        manager = RegisteredManager(
            given_name="Jehosephat", family_name="McGibbons", cqc_registered_manager_id="My CQC Registered Manager ID"
        )

        try:
            manager.full_clean()
        except ValidationError as e:
            assert "given_name" not in e.message_dict
            assert "first_name" not in e.message_dict
            assert "cqc_registered_manager_id" not in e.message_dict


class CareProviderLocationTests(TestCase):
    def test_rejects_bad_email_domain(self):
        assert_rejects_email(CareProviderLocation(), "bad-man@invalid-domain.evil")

    def test_accepts_safe_email_domain(self):
        assert_accepts_email(CareProviderLocation(), "good-dr@nhs.net")

    def test_rejects_invalid_email_address_format(self):
        assert_rejects_email(CareProviderLocation(), "notanemail.address")

    def test_accepts_data_fields(self):
        location = CareProviderLocation(
            name="My Location Name", ods_code="My Ods Code", cqc_location_id="My CQC Location ID"
        )

        try:
            location.full_clean()
        except ValidationError as e:
            assert "name" not in e.message_dict
            assert "ods_code" not in e.message_dict
            assert "cqc_location_id" not in e.message_dict

    def test_wont_save_without_a_manager(self):
        location = CareProviderLocation(
            name="My Location Name",
            email="nosuchaddress@nhs.net",
            ods_code="My Ods Code",
            cqc_location_id="My CQC Location ID",
        )
        with self.assertRaises(Exception):
            location.save()

    def test_saves_with_a_manager(self):
        manager = RegisteredManager(
            given_name="Jehosephat", family_name="McGibbons", cqc_registered_manager_id="My CQC RegsiteredManagerID"
        )
        manager.save()
        location = CareProviderLocation(
            registered_manager_id=manager.id,
            name="My Location Name",
            email="nosuchaddress@nhs.net",
            ods_code="My Ods Code",
            cqc_location_id="My CQC Location ID",
        )
        location.save()


class CareRecipientTests(TestCase):
    def test_stores_nhs_number_as_hash(self):
        jeff = CareRecipient(nhs_number="password")
        jeff.clean()
        self.assertEquals(jeff.nhs_number_hash, "c0067d4af4e87f00dbac63b6156828237059172d1bbeac67427345d6a9fda484")

    def test_nhs_number_is_write_only(self):
        jeff = CareRecipient()
        jeff.nhs_number = "super-sekrit"
        jeff.clean()
        self.assertEquals(jeff.nhs_number, None)

    def test_nhs_number_hash_gets_saved(self):
        manager = RegisteredManager.objects.create(
            given_name="Jehosephat", family_name="McGibbons", cqc_registered_manager_id="My CQC RegsiteredManagerID"
        )
        location = manager.careproviderlocation_set.create(
            name="My Location Name",
            email="nosuchaddress@nhs.net",
            ods_code="My Ods Code",
            cqc_location_id="My CQC Location ID",
        )
        jeff = location.carerecipient_set.create(subscription_id="42", provider_reference_id="foobar")
        jeff.nhs_number = "password"
        jeff.save()

        jeff_comparison = CareRecipient.objects.get(pk=jeff.id)
        self.assertEquals(jeff.nhs_number_hash, jeff_comparison.nhs_number_hash)
