# Copyright (c) 2026 8848 Digital LLP. All rights reserved.
# Proprietary and confidential. Unauthorized copying, distribution, or use
# of this file, via any medium, is strictly prohibited without prior
# written permission from 8848 Digital LLP.

# import frappe
from frappe.model.document import Document


class VendorFAQChangeLog(Document):
	"""Supplier child table row: an audit entry recording one FAQ answer's
	old/new value change (see customization/supplier/supplier_onboarding.py's _log_faq_changes)."""
