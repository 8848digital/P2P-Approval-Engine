# Copyright (c) 2026 8848 Digital LLP. All rights reserved.
# Proprietary and confidential. Unauthorized copying, distribution, or use
# of this file, via any medium, is strictly prohibited without prior
# written permission from 8848 Digital LLP.

# Copyright (c) 2026, Satya and contributors
# For license information, please see license.txt

# import frappe
from frappe.model.document import Document


class PaymentsComplianceAllowedRole(Document):
	"""Payments Compliance Settings child table row: a Role permitted to
	view the Procure to Pay Management dashboard (see
	dashboard_data.py's _check_permission)."""
