# Copyright (c) 2026 8848 Digital LLP. All rights reserved.
# Proprietary and confidential. Unauthorized copying, distribution, or use
# of this file, via any medium, is strictly prohibited without prior
# written permission from 8848 Digital LLP.

"""MSME ageing buckets for the Procure to Pay dashboard.
"""

import frappe
from frappe.utils import add_days, date_diff, nowdate

from approval_engine.settlement.customization.procure_to_pay.dashboard_config import _log
from approval_engine.settlement.customization.procure_to_pay.dashboard_filters import _base_filters


def _msme_ageing(company, settings, from_date=None, to_date=None, extra_filters=None):
	base = _base_filters(
		"Purchase Invoice",
		company,
		from_date,
		to_date,
		extra={**(extra_filters or {}), "docstatus": 1, "status": ["not in", ["Paid", "Cancelled"]]},
	)

	_log("PCD: _msme_ageing filters", f"company={company!r} filters={base}")

	invoices = frappe.db.get_list(
		"Purchase Invoice", filters=base, fields=["name", "due_date"], ignore_permissions=True
	)
	_log("PCD: _msme_ageing invoices fetched", f"count={len(invoices)}\nsample={invoices[:5]}")
	if not invoices:
		_log("PCD: _msme_ageing ZERO INVOICES", f"No Purchase Invoice matched filters={base}.")

	b1 = settings.immediate_due_days or 5
	b2 = settings.bucket_2_end_days or 14
	b3 = settings.bucket_3_end_days or 30
	b4 = settings.bucket_4_end_days or 45

	# "Overdue" is last, not first: it's the worst case on the ageing
	# gradient (worse than merely being due in 31-45 days), matching the
	# existing green->red bucket color scheme (see BUCKET_COLORS in both
	# dashboards' JS) where later buckets are more severe.
	bucket_labels = [
		"Immediate Due",
		f"6-{b2} Days",
		f"{b2 + 1}-{b3} Days",
		f"{b3 + 1}-{b4} Days",
		"Overdue",
	]
	counts = {b: 0 for b in bucket_labels}
	today = nowdate()

	skipped_no_due_date = 0
	skipped_beyond_bucket4 = 0

	for inv in invoices:
		if not inv.due_date:
			skipped_no_due_date += 1
			continue
		# date_diff(due_date, today) is NEGATIVE once due_date is in the
		# past. That used to satisfy `days <= b1` same as a bill due days
		# from now, so an invoice overdue by months counted as "Immediate
		# Due" -- same bucket as one due tomorrow. Overdue (due_date
		# already passed) is now its own bucket, checked first.
		days = date_diff(inv.due_date, today)
		if days < 0:
			counts[bucket_labels[4]] += 1
		elif days <= b1:
			counts[bucket_labels[0]] += 1
		elif days <= b2:
			counts[bucket_labels[1]] += 1
		elif days <= b3:
			counts[bucket_labels[2]] += 1
		elif days <= b4:
			counts[bucket_labels[3]] += 1
		else:
			skipped_beyond_bucket4 += 1

	_log(
		"PCD: _msme_ageing RESULT",
		f"today={today}\nbucket_days=({b1},{b2},{b3},{b4})\ncounts={counts}\n"
		f"skipped_no_due_date={skipped_no_due_date}\nskipped_beyond_bucket4={skipped_beyond_bucket4}",
	)

	# Concrete due_date ranges per bucket, for click-through navigation.
	bucket_filters = {
		bucket_labels[4]: {**base, "due_date": ["<", today]},
		bucket_labels[0]: {**base, "due_date": ["between", [today, add_days(today, b1)]]},
		bucket_labels[1]: {
			**base,
			"due_date": ["between", [add_days(today, b1 + 1), add_days(today, b2)]],
		},
		bucket_labels[2]: {
			**base,
			"due_date": ["between", [add_days(today, b2 + 1), add_days(today, b3)]],
		},
		bucket_labels[3]: {
			**base,
			"due_date": ["between", [add_days(today, b3 + 1), add_days(today, b4)]],
		},
	}

	return counts, bucket_filters
