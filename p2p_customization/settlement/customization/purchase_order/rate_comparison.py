import json
from datetime import timedelta

import frappe
from erpnext.accounts.utils import get_fiscal_year
from frappe import _
from frappe.utils import add_months, getdate


def get_rate_comparison_rows(
	supplier, nature_of_services, company, transaction_date, brn=None, exclude_po=None
):
	"""Cross-company vendor rate comparison for Purchase Order.

	For each (company, nature_of_service) pair with at least one matching
	Purchase Order in the current or previous review period, returns the
	most recent rate charged by `supplier` in each period, plus the
	variance between them. Companies with no matching PO in either window
	are simply omitted, rather than padding the table with empty rows.
	"""
	_check_rate_comparison_permission()

	if isinstance(nature_of_services, str):
		nature_of_services = json.loads(nature_of_services)
	nature_of_services = [nos for nos in (nature_of_services or []) if nos]
	empty_meta = {
		"period_type": None,
		"period_months": None,
		"brn_based": False,
		"current_period_label": None,
		"previous_period_label": None,
	}
	if not supplier or not nature_of_services or not transaction_date:
		return {"rows": [], "meta": empty_meta}

	period_months, brn_based = _resolve_period_months(brn)
	windows = _get_period_windows(transaction_date, period_months)
	cur_start, cur_end, cur_label = windows["current"]
	prev_start, prev_end, prev_label = windows["previous"]

	rows = []
	for nos in nature_of_services:
		current_by_company = {
			r.company: r for r in _fetch_period_rates(supplier, nos, cur_start, cur_end, exclude_po)
		}
		previous_by_company = {
			r.company: r for r in _fetch_period_rates(supplier, nos, prev_start, prev_end, exclude_po)
		}
		companies = sorted(set(current_by_company) | set(previous_by_company))
		for comp in companies:
			cur = current_by_company.get(comp)
			prev = previous_by_company.get(comp)

			variance = None
			if cur and prev and prev.rate:
				variance = round(((cur.rate - prev.rate) / prev.rate) * 100, 2)

			rows.append(
				{
					"company": comp,
					"nature_of_service": nos,
					"current_period_label": cur_label,
					"current_period_rate": cur.rate if cur else None,
					"current_period_po": cur.po_name if cur else None,
					"previous_period_label": prev_label,
					"previous_period_rate": prev.rate if prev else None,
					"previous_period_po": prev.po_name if prev else None,
					"variance_percent": variance,
				}
			)

	period_type = {3: "Quarterly", 6: "Half-Yearly", 12: "Yearly"}[period_months]
	meta = {
		"period_type": period_type,
		"period_months": period_months,
		"brn_based": brn_based,
		"current_period_label": cur_label,
		"previous_period_label": prev_label,
	}
	return {"rows": rows, "meta": meta}


def get_rate_comparison_config():
	"""Non-throwing settings lookup for the client to decide popup behavior.

	Unlike _check_rate_comparison_permission(), this never raises -- the
	client calls it on every Purchase Order form load to decide whether to
	show the button / auto-fetch, and a PermissionError here would just be
	noise on every form for users who simply aren't permitted to see rates.
	"""
	settings = frappe.get_single("Vendor Rate Comparison Settings")
	permitted = bool(settings.allowed_role) and settings.allowed_role in frappe.get_roles()
	return {
		"permitted": permitted,
		"trigger_mode": settings.popup_trigger_mode or "Both",
	}


def _check_rate_comparison_permission():
	# Fail-closed by design: an unconfigured allowed_role blocks everyone,
	# not just users whose roles don't match. This gate is what actually
	# secures the cross-company rate data returned below -- the popup on
	# the client is UX only.
	if not get_rate_comparison_config()["permitted"]:
		frappe.throw(_("You are not permitted to view Vendor Rate Comparison."), frappe.PermissionError)


def _resolve_period_months(brn):
	"""Maps BRN.duration_of_service_months to a comparison bucket size.

	Falls back to Quarterly (3 months) when no BRN is linked, or the BRN
	has no duration set. This fallback is not an edge case -- as of this
	writing zero live Purchase Orders have `brn` populated, so it is the
	dominant, common-case path. Returns (period_months, brn_based) so
	callers can tell a genuine BRN-derived 3-month bucket apart from the
	no-BRN fallback, both of which resolve to the same period_months.
	"""
	if not brn:
		return 3, False
	months = frappe.db.get_value("BRN", brn, "duration_of_service_months")
	if not months:
		return 3, False
	if months <= 3:
		return 3, True
	if months <= 6:
		return 6, True
	return 12, True


def _build_buckets(fy_start, fy_end, period_months):
	buckets = []
	cursor = fy_start
	while cursor <= fy_end:
		bucket_end = min(add_months(cursor, period_months) - timedelta(days=1), fy_end)
		buckets.append((cursor, bucket_end))
		cursor = add_months(cursor, period_months)
	return buckets


def _period_label(start, end, fiscal_year, period_months, idx):
	if period_months == 3:
		prefix = f"Q{idx + 1} "
	elif period_months == 6:
		prefix = f"H{idx + 1} "
	else:
		prefix = ""

	date_range = (
		start.strftime("%b %Y")
		if start.month == end.month and start.year == end.year
		else f"{start.strftime('%b')}-{end.strftime('%b %Y')}"
	)
	return f"{prefix}FY{fiscal_year} ({date_range})"


def _get_period_windows(transaction_date, period_months):
	"""Fiscal-year-aligned (Apr-Mar) current/previous period windows.

	Reuses erpnext's own get_fiscal_year(), the same helper this app's
	_get_fiscal_year_and_validity() already relies on for PO validity
	dates, so period boundaries stay consistent with that existing
	convention rather than a rolling N-months-back window.
	"""
	transaction_date = getdate(transaction_date)
	fiscal_year, fy_start, fy_end = get_fiscal_year(transaction_date)
	fy_start, fy_end = getdate(fy_start), getdate(fy_end)

	buckets = _build_buckets(fy_start, fy_end, period_months)
	current_idx = next(i for i, (s, e) in enumerate(buckets) if s <= transaction_date <= e)
	current_start, current_end = buckets[current_idx]
	current_label = _period_label(current_start, current_end, fiscal_year, period_months, current_idx)

	if current_idx > 0:
		previous_start, previous_end = buckets[current_idx - 1]
		previous_label = _period_label(
			previous_start, previous_end, fiscal_year, period_months, current_idx - 1
		)
	else:
		# Current period is the first bucket of this fiscal year -- the
		# previous period is the last bucket of the prior fiscal year.
		day_before_fy_start = fy_start - timedelta(days=1)
		previous_fiscal_year, prev_fy_start, prev_fy_end = get_fiscal_year(day_before_fy_start)
		prev_fy_start, prev_fy_end = getdate(prev_fy_start), getdate(prev_fy_end)
		prev_buckets = _build_buckets(prev_fy_start, prev_fy_end, period_months)
		previous_start, previous_end = prev_buckets[-1]
		previous_label = _period_label(
			previous_start, previous_end, previous_fiscal_year, period_months, len(prev_buckets) - 1
		)

	return {
		"current": (current_start, current_end, current_label),
		"previous": (previous_start, previous_end, previous_label),
	}


def _fetch_period_rates(supplier, nature_of_service, window_start, window_end, exclude_po):
	"""Most recent PO rate per company within a period window.

	Raw SQL, deliberately not going through frappe.get_list/has_permission:
	this returns only aggregate company/rate/PO-name values (not full
	documents), and the whole endpoint is already gated by
	_check_rate_comparison_permission() above. Do not "fix" this into a
	permission-filtered query -- doing so would silently defeat the
	feature's entire purpose, which is cross-entity rate visibility for
	users who may not have read access to every company's Purchase Orders.
	"""
	# exclude_clause is one of exactly two hardcoded literal strings (never
	# derived from exclude_po's value); the actual value is bound through the
	# %(exclude_po)s param below. Plain "+" concatenation (not an f-string or
	# .format()) so the query text itself never carries interpolated data.
	exclude_clause = "AND po.name != %(exclude_po)s" if exclude_po else ""
	query = (
		"""
		SELECT company, name AS po_name, rate FROM (
			SELECT
				po.company, po.name, po.transaction_date, poi.rate,
				ROW_NUMBER() OVER (
					PARTITION BY po.company
					ORDER BY po.transaction_date DESC, po.creation DESC
				) AS rn
			FROM `tabPurchase Order Item` poi
			INNER JOIN `tabPurchase Order` po ON po.name = poi.parent
			WHERE po.supplier = %(supplier)s
			  AND poi.nature_of_service = %(nature_of_service)s
			  AND po.docstatus != 2
			  AND po.transaction_date BETWEEN %(start)s AND %(end)s
			  """
		+ exclude_clause
		+ """
		) ranked
		WHERE rn = 1
		"""
	)
	return frappe.db.sql(
		query,
		{
			"supplier": supplier,
			"nature_of_service": nature_of_service,
			"start": window_start,
			"end": window_end,
			"exclude_po": exclude_po,
		},
		as_dict=True,
	)
