# Copyright (c) 2026 8848 Digital LLP. All rights reserved.
# Proprietary and confidential. Unauthorized copying, distribution, or use
# of this file, via any medium, is strictly prohibited without prior
# written permission from 8848 Digital LLP.

# Copyright (c) 2026, Satya and contributors
# For license information, please see license.txt

# import frappe
from frappe.model.document import Document


class KYCType(Document):
	"""A single KYC check category (e.g. GSTIN, PAN, MSME) -- the master
	list KYC Vendor.kyc_type and JFS Settings' vendor/block-type child
	tables link against."""
