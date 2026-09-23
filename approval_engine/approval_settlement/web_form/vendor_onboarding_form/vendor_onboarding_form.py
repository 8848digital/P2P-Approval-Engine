# Copyright (c) 2026 8848 Digital LLP. All rights reserved.
# Proprietary and confidential. Unauthorized copying, distribution, or use
# of this file, via any medium, is strictly prohibited without prior
# written permission from 8848 Digital LLP.


def get_context(context) -> None:
	"""No server-side context needed; the vendor onboarding web form's
	FAQ fields are synced separately by
	approval_settlement/doctype/faq_master/faq_master_utils.py's _rebuild_web_form_faq_fields().

	Parameters:
	        context (frappe._dict, required): The website render context.

	Returns:
	        None
	"""
