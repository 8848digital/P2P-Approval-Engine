# Copyright (c) 2026 8848 Digital LLP. All rights reserved.
# Proprietary and confidential. Unauthorized copying, distribution, or use
# of this file, via any medium, is strictly prohibited without prior
# written permission from 8848 Digital LLP.

# import frappe
from frappe.model.document import Document


class FAQMaster(Document):
	"""A single onboarding FAQ question, synced onto the Supplier form as a
	Custom Field and onto the vendor onboarding web form (see
	settlement/doc_events/faq_master.py)."""
