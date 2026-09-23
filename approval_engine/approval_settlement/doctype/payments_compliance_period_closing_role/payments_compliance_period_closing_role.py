# Copyright (c) 2026 8848 Digital LLP. All rights reserved.
# Proprietary and confidential. Unauthorized copying, distribution, or use
# of this file, via any medium, is strictly prohibited without prior
# written permission from 8848 Digital LLP.

# import frappe
from frappe.model.document import Document


class PaymentsCompliancePeriodClosingRole(Document):
	"""Payments Compliance Settings child table row: a Role permitted to run
	period-closing account updates (see procure_to_pay_management.py's
	can_view_period_closing)."""
