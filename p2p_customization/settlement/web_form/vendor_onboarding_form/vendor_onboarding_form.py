def get_context(context) -> None:
	"""No server-side context needed; the vendor onboarding web form's
	FAQ fields are synced separately by
	settlement/doc_events/faq_master.py's _rebuild_web_form_faq_fields().

	Parameters:
		context (frappe._dict, required): The website render context.

	Returns:
		None
	"""
