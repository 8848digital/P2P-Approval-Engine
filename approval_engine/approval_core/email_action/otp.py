# Copyright (c) 2026 8848 Digital LLP. All rights reserved.
# Proprietary and confidential. Unauthorized copying, distribution, or use
# of this file, via any medium, is strictly prohibited without prior
# written permission from 8848 Digital LLP.
"""One-time codes that confirm an emailed-link action really comes from the approver.

The code is emailed separately and only on demand (the visitor clicks "Send OTP"),
so a forwarded or leaked link alone is useless: the code always goes to the
approver's own mailbox. Each code is 6 digits, valid for 10 minutes, bound to one
link *and* one action, single use, and burned after 5 wrong tries. Only its hash
is stored on the `Approval Action Token` record.
"""

import hmac
import secrets

import frappe
from frappe import _
from frappe.utils import add_to_date, get_datetime, now_datetime

from approval_engine.approval_core.email_action.action_link import hash_secret
from approval_engine.approval_core.email_action.errors import ApprovalLinkError

OTP_DIGITS = 6
OTP_VALIDITY_MINUTES = 10
MAX_ATTEMPTS = 5
RESEND_COOLDOWN_SECONDS = 60
OTP_EMAIL_TEMPLATE = "approval_action_otp"


class LinkOtp:
    """Issue and check the one-time code for one emailed approval link."""

    def __init__(self, link):
        """
        Bind the OTP helper to one link; all state lives on the link's token record.

        Parameters:
            link (ApprovalLink, required): The validated link the code belongs to.

        Returns:
            None
        """
        self.link = link
        self.record = link.record

    def send(self, action):
        """
        Generate a new code for `action`, replacing any previous one, and email it now.

        Sent synchronously so an SMTP failure surfaces to the visitor and rolls back
        the stored hash, instead of leaving them waiting for a code that never comes.

        Parameters:
            action (str, required): Workflow action the code will authorise.

        Returns:
            None
        """
        self.__ensure_cooldown_elapsed()
        code = f"{secrets.randbelow(10 ** OTP_DIGITS):0{OTP_DIGITS}d}"
        self.record.db_set({
            "otp_hash": self.__hash(action, code),
            "otp_action": action,
            "otp_sent_on": now_datetime(),
            "otp_expires_on": add_to_date(now_datetime(), minutes=OTP_VALIDITY_MINUTES),
            "otp_attempts": 0,
        })
        self.__email_code(action, code)

    def verify(self, action, code):
        """
        Check `code` for `action`, consuming it on success.

        A wrong code is recorded and reported by return value, not by raising, so the
        failed-attempt count is committed with the request instead of rolled back.

        Parameters:
            action (str, required): Workflow action being confirmed.
            code (str, required): Code the visitor typed.

        Returns:
            bool: True if the code is correct (it is then cleared); False if wrong.

        Raises:
            ApprovalLinkError: When no usable code exists (none sent, expired, other
                action, or attempts exhausted).
        """
        self.__ensure_code_pending(action)

        if hmac.compare_digest(self.__hash(action, (code or "").strip()), self.record.otp_hash):
            self.__clear()
            return True

        attempts = (self.record.otp_attempts or 0) + 1
        self.record.db_set("otp_attempts", attempts)
        if attempts >= MAX_ATTEMPTS:
            self.__clear()
        return False

    def attempts_left(self):
        """
        Wrong tries still allowed for the current code.

        Returns:
            int: Remaining attempts (0 once the code is burned).
        """
        if not self.record.otp_hash:
            return 0
        return max(MAX_ATTEMPTS - (self.record.otp_attempts or 0), 0)

    def __ensure_cooldown_elapsed(self):
        """
        Raise if a code was sent too recently (stops mailbox flooding).

        Returns:
            None
        """
        sent_on = self.record.otp_sent_on
        if not sent_on:
            return
        elapsed = (now_datetime() - get_datetime(sent_on)).total_seconds()
        if elapsed < RESEND_COOLDOWN_SECONDS:
            raise ApprovalLinkError(
                _("A code was just sent. Please wait {0} seconds before requesting another.")
                .format(int(RESEND_COOLDOWN_SECONDS - elapsed) + 1))

    def __ensure_code_pending(self, action):
        """
        Raise unless an unexpired code exists for exactly this action.

        Parameters:
            action (str, required): Workflow action being confirmed.

        Returns:
            None
        """
        record = self.record
        if not record.otp_hash:
            raise ApprovalLinkError(_("Please request a new verification code."))
        if record.otp_action != action:
            raise ApprovalLinkError(
                _("The verification code was issued for {0}. Please request a new code for {1}.")
                .format(_(record.otp_action), _(action)))
        if get_datetime(record.otp_expires_on) < now_datetime():
            self.__clear()
            raise ApprovalLinkError(_("The verification code has expired. Please request a new one."))

    def __clear(self):
        """
        Invalidate the current code (after use, expiry or too many wrong tries).

        Returns:
            None
        """
        self.record.db_set({"otp_hash": None, "otp_action": None, "otp_expires_on": None})

    def __hash(self, action, code):
        """
        Hash a code bound to this link and action, so it can't be replayed elsewhere.

        Parameters:
            action (str, required): Workflow action the code authorises.
            code (str, required): The plain code.

        Returns:
            str: Hex digest to store/compare.
        """
        return hash_secret(f"{self.record.token_hash}:{action}:{code}")

    def __email_code(self, action, code):
        """
        Email the plain code to the approver's own address.

        Parameters:
            action (str, required): Workflow action the code authorises.
            code (str, required): The plain code.

        Returns:
            None
        """
        doc = self.link.reference_doc
        frappe.sendmail(
            recipients=[self.link.approver_email],
            subject=_("Your verification code for {0} {1}").format(doc.doctype, doc.name),
            template=OTP_EMAIL_TEMPLATE,
            args={
                "code": code,
                "action": _(action),
                "doctype": _(doc.doctype),
                "docname": doc.name,
                "validity_minutes": OTP_VALIDITY_MINUTES,
            },
            reference_doctype=doc.doctype,
            reference_name=doc.name,
            now=True,
        )
