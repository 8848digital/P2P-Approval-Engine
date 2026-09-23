# Copyright (c) 2026 8848 Digital LLP. All rights reserved.
# Proprietary and confidential. Unauthorized copying, distribution, or use
# of this file, via any medium, is strictly prohibited without prior
# written permission from 8848 Digital LLP.
"""
Patch: set the tds_reference link on Tax Withholding Category records that
were auto-created by doctype/tds_reference/tds_reference_utils.py's create_tax_withholding_categories
before the tds_reference custom field existed. Needed so
doctype/tds_reference/tds_reference_utils.py's get_tax_withholding_category (used by the Purchase
Order/Invoice Item nature_of_service handler) can look categories up reliably.

Idempotent - only fills in tds_reference where it's currently empty, using the
same name-construction logic as the category creation itself.

Runs in [post_model_sync], which executes before the after_migrate hook that
creates this app's custom fields - tds_reference (the whole point of this
patch) is one of them, so on a fresh site the column wouldn't exist yet
without calling create_custom_fields() here first.

Registered in patches.txt as:
    approval_engine.patches.v1_0.backfill_tds_reference_on_tax_withholding_category
"""

import frappe

from approval_engine.settlement.doctype.tds_reference.tds_reference_utils import (
	RATE_RE,
	STANDARD_DUAL_RATE_REMARK,
	_build_name,
	_category_base_name,
)
from approval_engine.settlement.setup import create_custom_fields


def execute():
	create_custom_fields()

	for name in frappe.get_all("TDS Reference", pluck="name"):
		doc = frappe.get_doc("TDS Reference", name)
		rates = RATE_RE.findall(doc.tds_rate or "")
		if not rates:
			continue

		base_name = _category_base_name(doc)

		if len(rates) == 1:
			candidate_names = [_build_name(base_name)]
		else:
			if (doc.remarks or "").strip() != STANDARD_DUAL_RATE_REMARK:
				continue
			candidate_names = [
				_build_name(base_name, " - Individual"),
				_build_name(base_name, " - HUF"),
				_build_name(base_name, " - Others"),
			]

		for category_name in candidate_names:
			if not frappe.db.exists("Tax Withholding Category", category_name):
				continue
			if not frappe.db.get_value("Tax Withholding Category", category_name, "tds_reference"):
				frappe.db.set_value("Tax Withholding Category", category_name, "tds_reference", doc.name)

	frappe.db.commit()
