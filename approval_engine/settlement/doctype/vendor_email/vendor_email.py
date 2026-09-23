# Copyright (c) 2026 8848 Digital LLP. All rights reserved.
# Proprietary and confidential. Unauthorized copying, distribution, or use
# of this file, via any medium, is strictly prohibited without prior
# written permission from 8848 Digital LLP.

from frappe.model.document import Document


class VendorEmail(Document):
	"""
	Tracks a vendor's onboarding email address(es) and their linked
	Supplier-creation reference, driving the Vendor Portal onboarding
	flow implemented in utils.py.

	Carries no custom validation of its own; uniqueness of `email` is
	enforced by the DocType schema.
	"""

	pass
