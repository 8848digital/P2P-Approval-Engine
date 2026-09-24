# Copyright (c) 2026 8848 Digital LLP. All rights reserved.
# Proprietary and confidential. Unauthorized copying, distribution, or use
# of this file, via any medium, is strictly prohibited without prior
# written permission from 8848 Digital LLP.
"""Controller for `Additional Approver` — a per-document ad-hoc approver insertion.

Thin lifecycle wiring only; the real logic lives in `additional_approver_utils.py`.
"""

from frappe.model.document import Document

from approval_engine.approval_core.doctype.additional_approver import (
    additional_approver_utils as utils,
)


class AdditionalApprover(Document):
    """One extra approver injected into a single document's live approval chain."""

    def validate(self):
        """
        Enforce the record invariants (governed target, valid state, one at a time).

        Returns:
            None
        """
        utils.validate_reviewer(self)

    def after_insert(self):
        """
        Grant the reviewer the coarse additional-approver role and, if configured,
        email them an action link.

        Returns:
            None
        """
        utils.grant_additional_role(self.reference_doctype, self.approver)
        if self.action_via_email:
            utils.notify_reviewer(self.name)
