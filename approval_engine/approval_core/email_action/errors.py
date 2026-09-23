# Copyright (c) 2026 8848 Digital LLP. All rights reserved.
# Proprietary and confidential. Unauthorized copying, distribution, or use
# of this file, via any medium, is strictly prohibited without prior
# written permission from 8848 Digital LLP.
"""Exceptions raised by the email-link approval flow."""

import frappe


class ApprovalLinkError(frappe.ValidationError):
    """An emailed approval link (or its OTP) can't be used: invalid, expired, used or superseded.

    Messages are shown to an unauthenticated visitor, so they never reveal internal details.
    """

    http_status_code = 400
