import os
from http import HTTPStatus
from unittest import mock
from unittest.mock import MagicMock
from uuid import uuid4

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase
from django.urls import reverse

from .enums import CSVImportMessages
from .forms import CareRecipientForm
from .models import CareRecipient, RegisteredManager


class CareProviderLocationTests(TestCase):
    def setUp(self) -> None:
        self.manager = RegisteredManager.objects.create(
            given_name="Jehosephat",
            family_name="McGibbons",
            cqc_registered_manager_id="My CQC RegsiteredManagerID",
        )
        self.location = self.manager.careproviderlocation_set.create(
            name="My Location Name",
            email="nosuchaddress@nhs.net",
            ods_code="My Ods Code",
            cqc_location_id="My CQC Location ID",
        )
        self.care_recipient = self.location.carerecipient_set.create(
            subscription_id=uuid4(), provider_reference_id="foobar"
        )
        self.care_recipient.nhs_number = "password"
        self.care_recipient.save()

    def assertFailure(self, response, expected_status_code, expected_code):
        self.assertEqual(response.status_code, expected_status_code)
        self.assertEqual(response.json()["issue"][0]["code"], expected_code)

    def test_search_get_method_not_allowed(self):
        url = reverse("care_provider_search")
        response = self.client.get(
            url, {"_careRecipientPseudoId": self.care_recipient.nhs_number_hash}
        )
        self.assertFailure(response, HTTPStatus.METHOD_NOT_ALLOWED, "not-allowed")

    def test_successful_search(self):
        url = reverse("care_provider_search")
        response = self.client.post(
            url, {"_careRecipientPseudoId": self.care_recipient.nhs_number_hash}
        )
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertEqual(response.json()["name"], self.location.name)

    def test_search_not_found(self):
        url = reverse("care_provider_search")
        response = self.client.post(url, {"_careRecipientPseudoId": "not_existing_id"})
        self.assertFailure(response, HTTPStatus.NOT_FOUND, "not-found")

    def test_search_missing_param_returns_bad_request(self):
        url = reverse("care_provider_search")
        response = self.client.post(url, {})
        self.assertFailure(response, HTTPStatus.BAD_REQUEST, "required")


class AdminCareProviderLocationTests(TestCase):
    def _convert_messages_to_str(self, response):
        return "".join([str(message) for message in list(response.context["messages"])])

    def _get_upload_file_response(self, csv_file):
        response = self.client.post(
            reverse("admin:import_care_recipients", args=(self.location.id,)),
            {"csvfile": csv_file},
            follow=True,
        )
        return response

    def _upload_test_data(self, test_filename):
        file_path = os.path.join(
            os.path.dirname(__file__), f"test_files/{test_filename}"
        )
        with open(file_path, "rb") as file:
            csv_file = SimpleUploadedFile(
                "patients_test_data.csv", file.read(), content_type="text/csv"
            )
        return csv_file

    def setUp(self) -> None:
        self.manager = RegisteredManager.objects.create(
            given_name="Jehosephat",
            family_name="McGibbons",
            cqc_registered_manager_id="My CQC RegsiteredManagerID",
        )
        self.location = self.manager.careproviderlocation_set.create(
            name="My Location Name",
            email="nosuchaddress@nhs.net",
            ods_code="My Ods Code",
            cqc_location_id="My CQC Location ID",
        )

        self.client = Client()
        self.user = User.objects.create_user(
            username="admin",
            email="admin@example.com",
            password="password",
            is_staff=True,
            is_superuser=True,
        )
        self.client.force_login(self.user)

    def test_admin_upload_empty_csv_file(self):
        response = self.client.post(
            reverse("admin:import_care_recipients", args=(self.location.id,)),
            follow=True,
        )
        messages = self._convert_messages_to_str(response)
        self.assertIn(CSVImportMessages.INVALID_OR_EMPTY_FILE.value, messages)
        self.assertEqual(CareRecipient.objects.count(), 0)

    def test_admin_upload_binary_file(self):
        csv_file = self._upload_test_data("binary_file.bin")
        response = self._get_upload_file_response(csv_file)
        messages = self._convert_messages_to_str(response)
        self.assertIn(CSVImportMessages.FILE_CORRUPTED_OR_BINARY.value, messages)
        self.assertEqual(CareRecipient.objects.count(), 0)

    def test_admin_upload_csv_file_with_invalid_columns(self):
        csv_file = self._upload_test_data("patients_invalid_column_set_test_data.csv")
        response = self._get_upload_file_response(csv_file)
        messages = self._convert_messages_to_str(response)
        self.assertIn(CSVImportMessages.INVALID_COLUMN_SET.value, messages)
        self.assertEqual(CareRecipient.objects.count(), 0)

    def test_admin_upload_csv_file_successfully(self):
        csv_file = self._upload_test_data("patients_test_data.csv")
        with mock.patch.object(
            CareRecipientForm,
            CareRecipientForm._create_subscription.__name__,
            MagicMock(side_effect=uuid4),
        ) as _create_subscription_mocked:
            response = self._get_upload_file_response(csv_file)
            csv_file.seek(0)
            lines_count = len(csv_file.readlines())
            messages = self._convert_messages_to_str(response)

        self.assertEqual(_create_subscription_mocked.call_count, lines_count - 1)
        self.assertIn(CSVImportMessages.FILE_IMPORTED_SUCCESSFULLY.value, messages)
        self.assertEqual(CareRecipient.objects.count(), lines_count - 1)

    def test_admin_upload_csv_file_with_broken_row(self):
        csv_file = self._upload_test_data("patients_invalid_row_test_data.csv")
        with mock.patch.object(
            CareRecipientForm,
            CareRecipientForm._create_subscription.__name__,
            MagicMock(side_effect=uuid4),
        ) as _create_subscription_mocked:
            response = self._get_upload_file_response(csv_file)
            csv_file.seek(0)
            lines_count = len(csv_file.readlines())
            messages = self._convert_messages_to_str(response)
        self.assertIn(CSVImportMessages.FILE_IMPORTED_SUCCESSFULLY.value, messages)
        self.assertIn("error(s)", messages)
        self.assertEqual(
            _create_subscription_mocked.call_count, lines_count - 3
        )  # header + two invalid rows


class AdminCareRecipientTests(TestCase):
    def setUp(self) -> None:
        self.manager = RegisteredManager.objects.create(
            given_name="Jehosephat",
            family_name="McGibbons",
            cqc_registered_manager_id="My CQC RegsiteredManagerID",
        )
        self.location = self.manager.careproviderlocation_set.create(
            name="My Location Name",
            email="nosuchaddress@nhs.net",
            ods_code="My Ods Code",
            cqc_location_id="My CQC Location ID",
        )

        self.client = Client()
        self.user = User.objects.create_user(
            username="admin",
            email="admin@example.com",
            password="password",
            is_staff=True,
            is_superuser=True,
        )
        self.client.force_login(self.user)

    def test_change_view__does_not_display_fields_not_stored_in_database(
        self,
    ):
        care_recipient = CareRecipient.objects.create(
            care_provider_location=self.location,
            nhs_number_hash="1234567",
            subscription_id=uuid4(),
            provider_reference_id="AX812938",
        )
        response = self.client.get(self._get_admin_change_view_url(care_recipient))
        response_text_lower = response.content.decode("utf-8").lower()
        self.assertEqual(response.status_code, HTTPStatus.OK)
        assert "given name" not in response_text_lower
        assert "family name" not in response_text_lower
        assert "nhs number" not in response_text_lower
        assert "birth date" not in response_text_lower

    @staticmethod
    def _get_admin_change_view_url(obj: object) -> str:
        return reverse(
            "admin:{}_{}_change".format(
                obj._meta.app_label, type(obj).__name__.lower()
            ),
            args=(obj.pk,),
        )
