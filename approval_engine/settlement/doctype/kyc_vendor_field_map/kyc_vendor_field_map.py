# Copyright (c) 2026 8848 Digital LLP. All rights reserved.
# Proprietary and confidential. Unauthorized copying, distribution, or use
# of this file, via any medium, is strictly prohibited without prior
# written permission from 8848 Digital LLP.
import frappe
from frappe.model.document import Document


class KYCVendorFieldMap(Document):
	"""KYC Vendor child table row: maps one Supplier field to one request
	template placeholder key."""

	def validate(self) -> None:
		"""Require supplier_fieldname/placeholder_key, and that
		supplier_fieldname is a real field on Supplier."""
		if not self.supplier_fieldname:
			frappe.throw(frappe._("Row #{0}: Supplier Fieldname is required").format(self.idx))
		if not self.placeholder_key:
			frappe.throw(frappe._("Row #{0}: Placeholder Key is required").format(self.idx))

		# Supplier fieldname must actually exist on the Supplier doctype
		meta = frappe.get_meta("Supplier")
		if not meta.has_field(self.supplier_fieldname) and self.supplier_fieldname not in (
			"name",
			"supplier_name",
		):
			frappe.throw(
				frappe._(
					"Row #{0}: '{1}' is not a valid fieldname on Supplier. Check spelling / custom field name."
				).format(self.idx, self.supplier_fieldname)
			)
