# Copyright (c) 2026 8848 Digital LLP. All rights reserved.
# Proprietary and confidential. Unauthorized copying, distribution, or use
# of this file, via any medium, is strictly prohibited without prior
# written permission from 8848 Digital LLP.
"""Whitelisted endpoints for the Finance Overview dashboard.

Thin wrappers over the per-DocType aggregation logic in
``approval_core.dashboard.finance_dashboard``. Each returns the standard
response envelope; the heavy query logic lives in the dashboard data provider,
not here.
"""

import frappe

from approval_engine.approval_core.dashboard import finance_dashboard as fd
from approval_engine.utils.api_handlers.response_formatter import api_response


def _resolve_user(user):
    """Resolve the effective user for a summary request.

    A caller may only request another user's summary if they are a System
    Manager; otherwise the request is scoped to the session user.

    Parameters:
        user (str, optional): Requested user. Defaults to the session user.

    Returns:
        str: The user the summary should be built for.
    """
    if user and user != frappe.session.user:
        frappe.only_for("System Manager")
    return user or frappe.session.user


@frappe.whitelist()
def get_pending_summary(company, user=None):
    """Per-DocType count + amount of documents pending on a user in a company.

    Path: approval_engine.approval_core.api.v1.dashboard.get_pending_summary
    Method: GET

    Parameters:
        company (str, required): Company to scope the summary to.
        user (str, optional): User to build the summary for; defaults to the
            session user. Only a System Manager may request another user.

    Returns:
        dict: Envelope whose ``data`` maps each target DocType to
        ``{records, amount, names}``.
    """
    return api_response(fd.pending_summary(company, _resolve_user(user)))


@frappe.whitelist()
def get_on_hold_summary(company, user=None):
    """Per-DocType count + amount of documents on hold by a user in a company.

    Path: approval_engine.approval_core.api.v1.dashboard.get_on_hold_summary
    Method: GET

    Parameters:
        company (str, required): Company to scope the summary to.
        user (str, optional): User to build the summary for; defaults to the
            session user. Only a System Manager may request another user.

    Returns:
        dict: Envelope whose ``data`` maps each target DocType to
        ``{records, amount, names}``.
    """
    return api_response(fd.on_hold_summary(company, _resolve_user(user)))


@frappe.whitelist()
def get_approved_summary(company, from_date=None, to_date=None, user=None):
    """Per-DocType count + amount of documents a user approved in a date range.

    Path: approval_engine.approval_core.api.v1.dashboard.get_approved_summary
    Method: GET

    Parameters:
        company (str, required): Company to scope the summary to.
        from_date (str, optional): Inclusive start date (YYYY-MM-DD).
        to_date (str, optional): Inclusive end date (YYYY-MM-DD).
        user (str, optional): User to build the summary for; defaults to the
            session user. Only a System Manager may request another user.

    Returns:
        dict: Envelope whose ``data`` maps each target DocType to
        ``{records, amount, names}``.
    """
    return api_response(
        fd.approved_summary(company, _resolve_user(user), from_date, to_date)
    )


@frappe.whitelist()
def get_dashboard_summary(company, user=None):
    """Per-DocType {pending, on_hold} summary for a user in a company.

    The single call the dashboard needs — both rows per DocType column in one
    round trip.

    Path: approval_engine.approval_core.api.v1.dashboard.get_dashboard_summary
    Method: GET

    Parameters:
        company (str, required): Company to scope the summary to.
        user (str, optional): User to build the summary for; defaults to the
            session user. Only a System Manager may request another user.

    Returns:
        dict: Envelope whose ``data`` maps each target DocType to
        ``{pending, on_hold}``.
    """
    return api_response(fd.dashboard_summary(company, _resolve_user(user)))
