import frappe
from frappe.model.document import Document


class ITCReversalLog(Document):
	def validate(self):
		if self.purchase_invoice:
			is_reversed = 1 if self.reversal_status == "Reversed" else 0
			frappe.db.set_value(
				"Purchase Invoice", self.purchase_invoice,
				"is_itc_reversed", is_reversed,
				update_modified=False
			)