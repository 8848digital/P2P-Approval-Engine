# Copyright (c) 2026 8848 Digital LLP. All rights reserved.
# Proprietary and confidential. Unauthorized copying, distribution, or use
# of this file, via any medium, is strictly prohibited without prior
# written permission from 8848 Digital LLP.
from frappe.model.document import Document


class KYCSettingsBlockType(Document):
	"""JFS Settings child table row: a KYC check type that must be Success
	or the Supplier gets put on hold (see
	kyc_validation/utils.py's evaluate_supplier_hold)."""
