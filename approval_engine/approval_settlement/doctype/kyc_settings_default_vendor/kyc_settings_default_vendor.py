# Copyright (c) 2026 8848 Digital LLP. All rights reserved.
# Proprietary and confidential. Unauthorized copying, distribution, or use
# of this file, via any medium, is strictly prohibited without prior
# written permission from 8848 Digital LLP.

# import frappe
from frappe.model.document import Document


class KYCSettingsDefaultVendor(Document):
	"""JFS Settings child table row: a KYC Vendor pre-checked by default in
	the Supplier KYC dialog (see kyc_validation/api.py's get_kyc_vendor_options)."""
