# Copyright (c) 2026, Satya and contributors
# For license information, please see license.txt

# import frappe
from frappe.model.document import Document


class PaymentsCompliancePeriodClosingRole(Document):
	"""Payments Compliance Settings child table row: a Role permitted to run
	period-closing account updates (see procure_to_pay_management.py's
	can_view_period_closing)."""
