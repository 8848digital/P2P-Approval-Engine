# Copyright (c) 2026 8848 Digital LLP. All rights reserved.
# Proprietary and confidential. Unauthorized copying, distribution, or use
# of this file, via any medium, is strictly prohibited without prior
# written permission from 8848 Digital LLP.

from frappe.model.document import Document

from .faq_master_utils import delete_supplier_custom_field, sync_supplier_custom_field
from .faq_master_utils import validate as validate_faq_master


class FAQMaster(Document):
	"""A single onboarding FAQ question, synced onto the Supplier form as a
	Custom Field and onto the vendor onboarding web form (see
	settlement/doctype/faq_master/faq_master_utils.py)."""

	def validate(self):
		"""Check the question code, options and dependency are consistent."""
		validate_faq_master(self)

	def after_insert(self):
		"""Add the new question to the Supplier form and onboarding web form."""
		sync_supplier_custom_field(self)

	def on_update(self):
		"""Re-sync the question onto the Supplier form and onboarding web form."""
		sync_supplier_custom_field(self)

	def on_trash(self):
		"""Remove the question from the Supplier form and onboarding web form."""
		delete_supplier_custom_field(self)
