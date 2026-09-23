# Copyright (c) 2026 8848 Digital LLP. All rights reserved.
# Proprietary and confidential. Unauthorized copying, distribution, or use
# of this file, via any medium, is strictly prohibited without prior
# written permission from 8848 Digital LLP.

"""Builds the full chart payload for both Procure to Pay dashboards.
"""

import frappe
from frappe import _
from frappe.utils import cint

from approval_engine.settlement.customization.procure_to_pay.dashboard_buckets import (
	_status_counts,
)
from approval_engine.settlement.customization.procure_to_pay.dashboard_config import (
	APPROVAL_TARGET_KEYS,
	PAYMENT_TARGET_KEYS,
	_log,
)
from approval_engine.settlement.customization.procure_to_pay.dashboard_msme import (
	_msme_ageing,
)
from approval_engine.settlement.customization.procure_to_pay.dashboard_scope import (
	_my_scope_context,
	_scope_context_filter,
)


def build_dashboard_payload(settings, company, from_date=None, to_date=None, scope_user=False):
	"""Single call: returns chart data + bucket click-through filters + UI settings.

	`scope_user` controls personal vs. aggregate scoping:
	  - Truthy (a user ID): every section is scoped to that user -- documents
	    they created, UNIONed with documents currently pending on them as an
	    approval-workflow approver, UNIONed with documents they already
	    approved or rejected at their own step (see _my_scope_context). This is the
	    open dashboard's only mode (always frappe.session.user), and the
	    management dashboard's mode when a specific "User" filter is set.
	  - `None` (explicitly, not just falsy): no personal scoping at all --
	    plain company-wide totals, every document's real current/final
	    bucket shown as-is. Only the management dashboard's default (no
	    User filter selected) uses this.
	  - The default value `False` is deliberately not a valid mode (neither
	    a user nor `None`) so a caller must pick one explicitly rather than
	    silently getting aggregate-by-omission.

	Access control is NOT this function's job -- see module docstring.
	"""
	_log(
		"PCD: build_dashboard_payload CALLED",
		f"company={company!r} from_date={from_date!r} to_date={to_date!r} "
		f"scope_user={scope_user!r} session_user={frappe.session.user}",
	)

	if scope_user is False:
		frappe.throw(
			_("build_dashboard_payload requires an explicit scope_user (a user ID, or None for aggregate).")
		)

	try:
		if not company:
			_log("PCD: build_dashboard_payload NO COMPANY", "company arg was empty/None -> throwing")
			frappe.throw(_("Please select a Company to view the dashboard."))

		def section(doctype, counts, bucket_filters):
			return {"doctype": doctype, "counts": counts, "bucket_filters": bucket_filters}

		scope_context = {}
		scope_filter = {}
		for dt in ("BRN", "Payment Order", "Purchase Order", "Purchase Invoice"):
			if scope_user:
				scope_context[dt] = _my_scope_context(dt, scope_user)
				scope_filter[dt] = _scope_context_filter(scope_context[dt])
			else:
				scope_context[dt] = None
				scope_filter[dt] = None

		brn_counts, brn_bf = _status_counts(
			"BRN",
			company,
			APPROVAL_TARGET_KEYS,
			settings,
			from_date,
			to_date,
			extra_filters=scope_filter.get("BRN"),
			scope_context=scope_context.get("BRN"),
		)
		po_counts, po_bf = _status_counts(
			"Payment Order",
			company,
			PAYMENT_TARGET_KEYS,
			settings,
			from_date,
			to_date,
			extra_filters=scope_filter.get("Payment Order"),
			scope_context=scope_context.get("Payment Order"),
		)
		puo_counts, puo_bf = _status_counts(
			"Purchase Order",
			company,
			APPROVAL_TARGET_KEYS,
			settings,
			from_date,
			to_date,
			extra_filters=scope_filter.get("Purchase Order"),
			scope_context=scope_context.get("Purchase Order"),
		)
		pi_counts, pi_bf = _status_counts(
			"Purchase Invoice",
			company,
			APPROVAL_TARGET_KEYS,
			settings,
			from_date,
			to_date,
			extra_filters=scope_filter.get("Purchase Invoice"),
			scope_context=scope_context.get("Purchase Invoice"),
		)
		msme_counts, msme_bf = _msme_ageing(
			company, settings, from_date, to_date, extra_filters=scope_filter.get("Purchase Invoice")
		)

		enable_related_party = cint(settings.get("enable_related_party_chart", 1))
		rp_counts, rp_bf = {}, {}
		if enable_related_party:
			rp_extra = {**(scope_filter.get("Purchase Invoice") or {}), "is_related_party_transaction": 1}
			rp_counts, rp_bf = _status_counts(
				"Purchase Invoice",
				company,
				APPROVAL_TARGET_KEYS,
				settings,
				from_date,
				to_date,
				extra_filters=rp_extra,
				scope_context=scope_context.get("Purchase Invoice"),
			)

		payload = {
			"brn": section("BRN", brn_counts, brn_bf),
			"payment_order": section("Payment Order", po_counts, po_bf),
			"purchase_order": section("Purchase Order", puo_counts, puo_bf),
			"purchase_invoice": section("Purchase Invoice", pi_counts, pi_bf),
			"msme": section("Purchase Invoice", msme_counts, msme_bf),
			"related_party": section("Purchase Invoice", rp_counts, rp_bf),
			"enable_related_party_chart": bool(enable_related_party),
			"chart_types": {
				"brn": settings.brn_chart_type or "Pie",
				"payment_order": settings.payment_order_chart_type or "Bar",
				"purchase_order": settings.purchase_order_chart_type or "Pie",
				"purchase_invoice": settings.purchase_invoice_chart_type or "Bar",
				"msme": settings.msme_chart_type or "Bar",
				"related_party": settings.related_party_chart_type or "Donut",
			},
			"auto_refresh_seconds": settings.auto_refresh_seconds or 0,
			"can_configure": "System Manager" in frappe.get_roles(),
			"is_aggregate_view": not bool(scope_user),
			"current_user": {
				"name": scope_user or None,
				"fullname": frappe.utils.get_fullname(scope_user) if scope_user else None,
			},
		}

		all_zero = all(
			all(v == 0 for v in section_data["counts"].values())
			for section_data in (
				payload["brn"],
				payload["payment_order"],
				payload["purchase_order"],
				payload["purchase_invoice"],
				payload["msme"],
			)
		)
		if all_zero:
			_log(
				"PCD: build_dashboard_payload ALL SECTIONS ZERO",
				f"company={company!r} from_date={from_date!r} to_date={to_date!r}\n"
				f"Every chart section came back all-zero -- check the per-doctype log entries just "
				f"above this one, and confirm with the 'Debug Raw Counts' dialog using the same "
				f"Company + date range.",
			)

		_log("PCD: build_dashboard_payload RETURNING", f"company={company!r}\npayload={payload}")
		return payload

	except frappe.PermissionError:
		raise
	except Exception:
		_log(
			"PCD: build_dashboard_payload EXCEPTION",
			f"company={company!r} user={frappe.session.user}\n\n{frappe.get_traceback()}",
		)
		raise
