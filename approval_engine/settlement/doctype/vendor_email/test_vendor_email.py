# Copyright (c) 2026 8848 Digital LLP. All rights reserved.
# Proprietary and confidential. Unauthorized copying, distribution, or use
# of this file, via any medium, is strictly prohibited without prior
# written permission from 8848 Digital LLP.

import base64
import urllib.parse
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase, UnitTestCase

from approval_engine.settlement.doctype.vendor_email.utils import (
	build_vendor_webform_link,
	create_vendor,
	encode_email,
	ensure_vendor_portal_role,
)


class IntegrationTestVendorEmail(IntegrationTestCase):
	"""
	Integration tests for VendorEmail and the vendor onboarding logic in
	vendor_email/utils.py.
	"""

	def _get_any_company(self) -> str:
		"""
		Return the name of any existing Company record on the test site,
		skipping the test when none exists so it doesn't depend on
		ERPNext's demo fixtures being present.

		Parameters:
		        None

		Returns:
		        str: A Company document name.
		"""
		company = frappe.db.get_value("Company", {}, "name")
		if not company:
			self.skipTest("No Company record available on this site")
		return company

	def test_create_vendor_creates_document_and_triggers_mail_logic(self) -> None:
		"""
		create_vendor creates a new Vendor Email record for a not-yet-seen
		address and forwards it to send_vendor_mail_logic to kick off
		onboarding, without sending real email.
		"""
		company = self._get_any_company()
		email = "new.vendor@example.com"

		with patch(
			"approval_engine.settlement.doctype.vendor_email.utils.send_vendor_mail_logic",
			return_value={"status": "success", "message": "mocked"},
		) as mock_mail_logic:
			result = create_vendor(email, "Supplier", None, vendor_name="New Vendor", company=company)

		self.assertTrue(frappe.db.exists("Vendor Email", email))
		mock_mail_logic.assert_called_once()
		self.assertEqual(result["status"], "success")

	def test_create_vendor_raises_for_existing_email(self) -> None:
		"""
		create_vendor refuses to create a duplicate Vendor Email record
		and raises a validation error naming the existing address.
		"""
		company = self._get_any_company()
		email = "existing.vendor@example.com"
		frappe.get_doc(
			doctype="Vendor Email",
			email=email,
			company=company,
		).insert(ignore_permissions=True)

		self.assertRaises(frappe.ValidationError, create_vendor, email, "Supplier", None)

	def test_ensure_vendor_portal_role_is_idempotent(self) -> None:
		"""
		ensure_vendor_portal_role creates the Vendor Portal role and its
		Address permission once, and leaves a single permission row in
		place on repeat calls.
		"""
		ensure_vendor_portal_role()
		ensure_vendor_portal_role()

		self.assertTrue(frappe.db.exists("Role", "Vendor Portal"))
		self.assertEqual(
			frappe.db.count(
				"Custom DocPerm",
				{"parent": "Address", "role": "Vendor Portal", "permlevel": 0},
			),
			1,
		)


class UnitTestVendorEmailUtils(UnitTestCase):
	"""
	Unit tests for the pure logic helpers in vendor_email/utils.py.
	"""

	def test_encode_email_roundtrips_local_and_domain_parts(self) -> None:
		"""
		encode_email base64url-encodes the local and domain parts of an
		address independently, so each half can be decoded back.
		"""
		encoded = encode_email("vendor@example.com")
		local, domain = encoded.split("@")

		self.assertEqual(_decode_padded_base64url(local), "vendor")
		self.assertEqual(_decode_padded_base64url(domain), "example.com")

	def test_build_vendor_webform_link_encodes_company_param(self) -> None:
		"""
		build_vendor_webform_link folds a company name into the redirect
		URL as a `custom_company` query parameter when one is supplied.
		"""
		link = build_vendor_webform_link("vendor@example.com", "REF-001", "AcmeCo")
		decoded_redirect = urllib.parse.unquote(link.split("redirect-to=")[1])

		self.assertIn("custom_company=AcmeCo", decoded_redirect)
		self.assertIn("email_id=", decoded_redirect)

	def test_build_vendor_webform_link_omits_company_param_when_not_given(self) -> None:
		"""
		build_vendor_webform_link leaves out `custom_company` entirely
		when no company is supplied.
		"""
		link = build_vendor_webform_link("vendor@example.com", "REF-001")
		decoded_redirect = urllib.parse.unquote(link.split("redirect-to=")[1])

		self.assertNotIn("custom_company", decoded_redirect)


def _decode_padded_base64url(value: str) -> str:
	"""
	Decode a base64url string that had its `=` padding stripped (as
	encode_string_part produces), for use in tests only.

	Note: kept single-underscore (not the usual `__` file-local prefix)
	because it's referenced from inside a test class method, where a
	`__`-prefixed name would be Python name-mangled and fail to resolve.

	Parameters:
	        value (str, required): Padding-stripped base64url string.

	Returns:
	        str: The decoded UTF-8 string.
	"""
	padded = value + "=" * (-len(value) % 4)
	return base64.urlsafe_b64decode(padded).decode()
