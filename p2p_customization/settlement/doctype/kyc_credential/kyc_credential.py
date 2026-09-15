# Copyright (c) 2026, p2p_customization
import frappe
from frappe.model.document import Document


class KYCCredential(Document):
	def validate(self):
		self.base_url = (self.base_url or "").strip().rstrip("/")

		if not self.base_url.startswith("http"):
			frappe.throw(
				frappe._("Row #{0}: Base URL must start with http:// or https://").format(self.idx)
			)

		if self.auth_type != "None" and not self.token:
			frappe.throw(
				frappe._("Row #{0}: Token is required when Auth Type is {1}").format(
					self.idx, self.auth_type
				)
			)

		if not self.header_key:
			self.header_key = "Authorization"
