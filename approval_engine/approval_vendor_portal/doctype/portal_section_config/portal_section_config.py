# Copyright (c) 2026 8848 Digital LLP. All rights reserved.
# Proprietary and confidential. Unauthorized copying, distribution, or use
# of this file, via any medium, is strictly prohibited without prior
# written permission from 8848 Digital LLP.

from frappe.model.document import Document


class PortalSectionConfig(Document):
	"""
	Child-table row of Vendor Portal Settings, describing one portal
	section: which DocType it lists, its route/label/icon, the Role
	required to see it, which fields drive its title/status/amount
	display, and whether it belongs to a shared tab group. Configures a
	whole portal section without any code changes -- see
	`vendor_portal.utils.get_portal_doctypes` and friends for how rows
	here are read.

	Carries no custom validation of its own.
	"""

	pass
