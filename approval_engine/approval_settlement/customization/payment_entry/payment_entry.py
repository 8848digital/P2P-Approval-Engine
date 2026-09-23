# Copyright (c) 2026 8848 Digital LLP. All rights reserved.
# Proprietary and confidential. Unauthorized copying, distribution, or use
# of this file, via any medium, is strictly prohibited without prior
# written permission from 8848 Digital LLP.

"""doc_events hook wiring for Payment Entry. Delegates to msa_check.py."""

from approval_engine.approval_settlement.customization.payment_entry.msa_check import (
	block_payment_without_msa_attachment,
)


def before_submit(doc, method=None):
	"""
	Payment Entry before_submit hook: block payment against a BRN vendor
	marked "Has MSA" whose MSA attachment is missing.

	Parameters:
	        doc (Document, required): The Payment Entry being submitted.
	        method (str, optional): The hook event name passed by Frappe.

	Returns:
	        None
	"""
	block_payment_without_msa_attachment(doc, method)
