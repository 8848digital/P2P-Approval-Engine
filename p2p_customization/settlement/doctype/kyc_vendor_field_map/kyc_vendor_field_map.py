# Copyright (c) 2026, p2p_customization
import frappe
from frappe.model.document import Document


class KYCVendorFieldMap(Document):
	def validate(self):
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
