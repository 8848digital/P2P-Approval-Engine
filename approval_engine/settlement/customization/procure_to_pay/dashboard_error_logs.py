# Copyright (c) 2026 8848 Digital LLP. All rights reserved.
# Proprietary and confidential. Unauthorized copying, distribution, or use
# of this file, via any medium, is strictly prohibited without prior
# written permission from 8848 Digital LLP.

"""Error Log viewer for the Procure to Pay dashboards (System Manager only).
"""

import frappe
from frappe.utils import cint, get_datetime

from approval_engine.settlement.customization.procure_to_pay.dashboard_config import _log
from approval_engine.settlement.customization.procure_to_pay.dashboard_filters import (
	_date_range_filter,
)


def build_error_logs(doctype=None, from_date=None, to_date=None, limit=100):
	"""Line-by-line Frappe Error Log viewer, scoped to this dashboard's doctypes and a date range.
	System Manager only: tracebacks can carry data from any module, and the
	query below reads Error Log with ignore_permissions."""
	frappe.only_for("System Manager")

	_log(
		"PCD: build_error_logs CALLED",
		f"doctype={doctype!r} from_date={from_date!r} to_date={to_date!r} limit={limit!r}",
	)

	limit = cint(limit) or 100

	filters = {}
	filters.update(_date_range_filter(from_date, to_date, fieldname="creation"))
	if doctype:
		filters["error"] = ["like", f"%{doctype}%"]

	_log("PCD: build_error_logs filters", f"filters={filters}\nlimit={limit}")

	rows = frappe.db.get_list(
		"Error Log",
		filters=filters,
		fields=["name", "creation", "method", "error"],
		order_by="creation desc",
		limit_page_length=limit,
		ignore_permissions=True,
	)
	_log("PCD: build_error_logs raw row count", f"row_count={len(rows)}")

	out = []
	for r in rows:
		error_text = r.get("error") or ""
		lines = [ln for ln in error_text.splitlines() if ln.strip()]
		summary = lines[-1] if lines else "(empty error log)"
		out.append(
			{
				"name": r["name"],
				"creation": get_datetime(r["creation"]).strftime("%Y-%m-%d %H:%M:%S")
				if r.get("creation")
				else "",
				"method": r.get("method") or "",
				"summary": summary[:300],
				"line_count": len(lines),
				"full_text": error_text,
			}
		)

	return {
		"filters_applied": filters,
		"row_count": len(out),
		"hit_limit": len(out) == limit,
		"rows": out,
	}
