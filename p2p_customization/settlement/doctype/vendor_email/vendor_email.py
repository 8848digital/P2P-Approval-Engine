# Copyright (c) 2025, Satya and contributors
# For license information, please see license.txt

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
