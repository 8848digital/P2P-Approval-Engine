# Copyright (c) 2026, Satya and contributors
# For license information, please see license.txt

# import frappe
from frappe.model.document import Document


class KYCSettingsDefaultVendor(Document):
	"""JFS Settings child table row: a KYC Vendor pre-checked by default in
	the Supplier KYC dialog (see kyc_validation/api.py's get_kyc_vendor_options)."""
