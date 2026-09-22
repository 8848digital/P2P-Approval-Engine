# Copyright (c) 2026, p2p_customization
from frappe.model.document import Document


class KYCSettingsBlockType(Document):
	"""JFS Settings child table row: a KYC check type that must be Success
	or the Supplier gets put on hold (see
	kyc_validation/utils.py's evaluate_supplier_hold)."""
