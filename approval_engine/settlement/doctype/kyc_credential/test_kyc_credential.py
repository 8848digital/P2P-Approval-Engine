# Copyright (c) 2026 8848 Digital LLP. All rights reserved.
# Proprietary and confidential. Unauthorized copying, distribution, or use
# of this file, via any medium, is strictly prohibited without prior
# written permission from 8848 Digital LLP.

"""Coverage for KYCCredential.validate() -- part of issue #10's "credential
lifecycle" test-coverage ask.

KYC Credential is a child table (istable=1, lives on JFS Settings), so
these call KYCCredential.validate() directly against a lightweight
frappe._dict standing in for `self`, rather than inserting a real child
row -- avoids needing a JFS Settings parent context this environment has
no live site to verify against.
"""

import frappe
from frappe.tests import UnitTestCase

from approval_engine.settlement.doctype.kyc_credential.kyc_credential import KYCCredential


def _credential(**overrides):
	row = frappe._dict(
		base_url="https://api.example.com", auth_type="None", token=None, header_key=None, idx=1
	)
	row.update(overrides)
	return row


class TestKYCCredentialValidate(UnitTestCase):
	def test_strips_trailing_slash_from_base_url(self):
		row = _credential(base_url="https://api.example.com/")
		KYCCredential.validate(row)
		self.assertEqual(row.base_url, "https://api.example.com")

	def test_rejects_non_http_base_url(self):
		row = _credential(base_url="ftp://api.example.com")
		self.assertRaises(frappe.ValidationError, KYCCredential.validate, row)

	def test_accepts_https(self):
		row = _credential(base_url="https://api.example.com")
		KYCCredential.validate(row)  # must not raise

	def test_requires_token_when_auth_type_not_none(self):
		row = _credential(auth_type="Bearer", token=None)
		self.assertRaises(frappe.ValidationError, KYCCredential.validate, row)

	def test_allows_no_token_when_auth_type_none(self):
		row = _credential(auth_type="None", token=None)
		KYCCredential.validate(row)  # must not raise

	def test_defaults_header_key_to_authorization(self):
		row = _credential(header_key=None)
		KYCCredential.validate(row)
		self.assertEqual(row.header_key, "Authorization")

	def test_keeps_explicit_header_key(self):
		row = _credential(header_key="X-Api-Key")
		KYCCredential.validate(row)
		self.assertEqual(row.header_key, "X-Api-Key")
