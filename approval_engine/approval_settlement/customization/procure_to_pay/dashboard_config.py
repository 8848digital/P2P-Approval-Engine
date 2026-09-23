# Copyright (c) 2026 8848 Digital LLP. All rights reserved.
# Proprietary and confidential. Unauthorized copying, distribution, or use
# of this file, via any medium, is strictly prohibited without prior
# written permission from 8848 Digital LLP.

"""Constants and debug logging shared by the Procure to Pay dashboard modules.
"""

import frappe

ENABLE_VERBOSE_DEBUG_LOG = False


def _log(title, message):
	if not ENABLE_VERBOSE_DEBUG_LOG:
		return
	try:
		frappe.log_error(title=str(title)[:140], message=message)
	except Exception:
		pass


# target_keys convention used everywhere below: [FINAL_OK, FINAL_BAD, PENDING]
APPROVAL_TARGET_KEYS = ["Approved", "Rejected", "Pending"]


PAYMENT_TARGET_KEYS = ["Processed", "Failed", "Pending"]


DEBUGGABLE_DOCTYPES = ["BRN", "Payment Order", "Purchase Order", "Purchase Invoice"]


DOCTYPE_TARGET_KEYS = {
	"BRN": APPROVAL_TARGET_KEYS,
	"Purchase Order": APPROVAL_TARGET_KEYS,
	"Purchase Invoice": APPROVAL_TARGET_KEYS,
	"Payment Order": PAYMENT_TARGET_KEYS,
}


# Each doctype's real business/transaction date -- NOT `creation` (when the
# DB row was inserted), which can differ substantially from the transaction
# date for backdated entries or bulk imports. Filtering by `creation` made
# the dashboard's From/To Date disagree with what a user sees when they
# filter the doctype's own list view by the same range.
DOCTYPE_DATE_FIELD = {
	"BRN": "transaction_date",
	"Payment Order": "posting_date",
	"Purchase Order": "transaction_date",
	"Purchase Invoice": "posting_date",
}


# Payment Order has its own real `status` field (Pending / Pending Approval /
# Partially Approved / Approved / Partially Initiated / Initiated / Rejected
# / Failed / Partially Failed). Submission (docstatus=1) only means the
# record was saved -- it does NOT mean a bank has actually processed the
# payment, so "Payment Release Status" buckets by this field instead of
# docstatus. Values not present here fall back to plain docstatus bucketing
# (see _resolve_bucket) so nothing silently vanishes.
PAYMENT_ORDER_STATUS_BUCKET = {
	"approved": "Processed",
	"initiated": "Processed",
	"rejected": "Failed",
	"failed": "Failed",
	"partially failed": "Failed",
	"pending": "Pending",
	"pending approval": "Pending",
	"partially approved": "Pending",
	"partially initiated": "Pending",
}
