# Copyright (c) 2026, Satya and contributors
# For license information, please see license.txt

# import frappe
from frappe.model.document import Document


class KYCType(Document):
	"""A single KYC check category (e.g. GSTIN, PAN, MSME) -- the master
	list KYC Vendor.kyc_type and JFS Settings' vendor/block-type child
	tables link against."""
