# Copyright (c) 2026 8848 Digital LLP. All rights reserved.
# Proprietary and confidential. Unauthorized copying, distribution, or use
# of this file, via any medium, is strictly prohibited without prior
# written permission from 8848 Digital LLP.
import frappe
from frappe.model.document import Document


class KYCCredential(Document):
	"""One vendor's base URL + auth config, shared by every KYC Vendor row
	that points at it (JFS Settings' Credentials child table)."""

	def validate(self) -> None:
		"""Normalize base_url and enforce it's an http(s) URL; require a
		Token when Auth Type isn't None; default Header Key to Authorization."""
		self.base_url = (self.base_url or "").strip().rstrip("/")

		if not self.base_url.startswith("http"):
			frappe.throw(frappe._("Row #{0}: Base URL must start with http:// or https://").format(self.idx))

		if self.auth_type != "None" and not self.token:
			frappe.throw(
				frappe._("Row #{0}: Token is required when Auth Type is {1}").format(self.idx, self.auth_type)
			)

		if not self.header_key:
			self.header_key = "Authorization"
