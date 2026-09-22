# Copyright (c) 2026, Satya and contributors
# For license information, please see license.txt

# import frappe
from frappe.model.document import Document


class PaymentsComplianceWorkflowStateMapping(Document):
	"""Payments Compliance Settings child table row: maps one doctype's
	workflow_state value to a dashboard status bucket (Approved/Rejected/
	Pending) -- see customization/procure_to_pay/dashboard_data.py's
	_get_state_mapping and _resolve_bucket."""
