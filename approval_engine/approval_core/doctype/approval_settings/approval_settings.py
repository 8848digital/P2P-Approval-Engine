# Copyright (c) 2026 8848 Digital LLP. All rights reserved.
# Proprietary and confidential. Unauthorized copying, distribution, or use
# of this file, via any medium, is strictly prohibited without prior
# written permission from 8848 Digital LLP.
"""Controller for Approval Settings (hooks only; logic lives in approval_settings_utils)."""

from frappe.model.document import Document

from approval_engine.approval_core.doctype.approval_settings.approval_settings_utils import (
	validate_link_validity,
)


class ApprovalSettings(Document):
	"""App-wide approval configuration: amount-field mapping and email-link settings."""

	def validate(self):
		"""
		Validate settings before save.

		Returns:
			None
		"""
		validate_link_validity(self)
