# Copyright (c) 2026 8848 Digital LLP. All rights reserved.
# Proprietary and confidential. Unauthorized copying, distribution, or use
# of this file, via any medium, is strictly prohibited without prior
# written permission from 8848 Digital LLP.
"""Email the approvers who must act next a personal action link + the document PDF.

Runs in a background job after a governed document changes workflow state
(`tasks.send_action_emails`). Only the tier that acts FROM the new state is
emailed, and only when that tier has "Action via Email" ticked on the matched
Approval Matrix row. A hold re-emails the holding tier so they can resume or
reject from email as well.
"""

import frappe
from frappe import _
from frappe.utils import flt, fmt_money

from approval_engine.approval_core.email_action.action_link import (
    issue_link,
    link_validity_hours,
)
from approval_engine.approval_core.generator import (
    acting_tier,
    amount_field_for,
    find_band_row,
    pool,
)

REQUEST_EMAIL_TEMPLATE = "approval_action_request"


class ActionRequestNotifier:
    """Send the action-request emails for one document in its current state."""

    def __init__(self, doc):
        """
        Bind the notifier to the document whose next approvers should be emailed.

        Parameters:
            doc (Document, required): The governed document, freshly loaded.

        Returns:
            None
        """
        self.doc = doc
        self.tier = acting_tier(doc.get("workflow_state"))
        self.amount = flt(doc.get(amount_field_for(doc.doctype)))

    def run(self):
        """
        Issue one link per eligible approver of the acting tier and email it.

        Returns:
            int: Number of emails queued (0 when the tier isn't configured for email).
        """
        recipients = self.__recipients()
        if not recipients:
            return 0

        attachments = self.__pdf_attachments()
        for user, email in recipients:
            self.__send(user, email, issue_link(self.doc, user, self.tier), attachments)
        return len(recipients)

    def __recipients(self):
        """
        Enabled approvers (with an email address) of the acting tier, if it emails.

        Returns:
            list[tuple[str, str]]: `(user, email)` pairs; empty when nothing to send.
        """
        if not self.tier:
            return []
        row = find_band_row(
            self.doc.doctype, self.doc.get("company"), self.doc.get("department"), self.amount)
        if not row or not row.get(f"approver_{self.tier}_action_via_email"):
            return []

        users = frappe.get_all(
            "User",
            filters={"name": ["in", pool(row, self.tier)], "enabled": 1},
            fields=["name", "email"],
        )
        return [(user.name, user.email) for user in users if user.email]

    def __pdf_attachments(self):
        """
        Deferred PDF attachment in the DocType's Default Print Format (Customize Form),
        falling back to Standard.

        Rendered by the email worker at send time, not here: a slow or hung PDF renderer
        then can't time this job out before every link is issued and every email queued,
        and a render failure shows up (and can be retried) on the Email Queue record.

        Returns:
            list[dict]: One `print_format_attachment` spec for `frappe.sendmail`.
        """
        return [{
            "print_format_attachment": 1,
            "doctype": self.doc.doctype,
            "name": self.doc.name,
        }]

    def __send(self, user, email, link_url, attachments):
        """
        Queue the action-request email for one approver.

        Parameters:
            user (str, required): Approver user ID.
            email (str, required): Approver email address.
            link_url (str, required): Their personal approval-page URL.
            attachments (list, required): PDF attachment(s) to include.

        Returns:
            None
        """
        doc = self.doc
        frappe.sendmail(
            recipients=[email],
            subject=_("Approval required: {0} {1}").format(_(doc.doctype), doc.name),
            template=REQUEST_EMAIL_TEMPLATE,
            args={
                "approver_name": frappe.utils.get_fullname(user),
                "doctype": _(doc.doctype),
                "docname": doc.name,
                "company": doc.get("company"),
                "department": doc.get("department"),
                "amount": fmt_money(self.amount, currency=doc.get("currency")),
                "workflow_state": _(doc.get("workflow_state")),
                "tier": self.tier,
                "link_url": link_url,
                "validity_hours": link_validity_hours(),
            },
            attachments=attachments,
            print_letterhead=True,
            reference_doctype=doc.doctype,
            reference_name=doc.name,
        )
