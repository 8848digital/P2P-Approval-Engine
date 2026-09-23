# Copyright (c) 2026 8848 Digital LLP. All rights reserved.
# Proprietary and confidential. Unauthorized copying, distribution, or use
# of this file, via any medium, is strictly prohibited without prior
# written permission from 8848 Digital LLP.

"""doc_events hook wiring for Payment Request. Delegates to msa_check.py."""

from approval_engine.approval_settlement.customization.payment_request.msa_check import (
	msa_agreement_validation,
)


def before_validate(doc, method=None):
	"""
	Payment Request before_validate hook: block the request when the
	Supplier's MSA Agreement is "No" or not set.

	Parameters:
	        doc (Document, required): The Payment Request being validated.
	        method (str, optional): The hook event name passed by Frappe.

	Returns:
	        None
	"""
	msa_agreement_validation(doc, method)
