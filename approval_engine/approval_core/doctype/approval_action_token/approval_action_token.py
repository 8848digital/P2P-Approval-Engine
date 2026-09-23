# Copyright (c) 2026 8848 Digital LLP. All rights reserved.
# Proprietary and confidential. Unauthorized copying, distribution, or use
# of this file, via any medium, is strictly prohibited without prior
# written permission from 8848 Digital LLP.
"""Approval Action Token: one emailed, single-use approval link for one approver on one document.

Only a SHA-256 hash of the link token (and of any OTP) is stored; the raw values exist
only in the emails. Records are created and updated by the engine
(`approval_core/email_action/`), never by hand.
"""

from frappe.model.document import Document


class ApprovalActionToken(Document):
	"""Audit + state record for one emailed approval link (see module docstring)."""

	pass
