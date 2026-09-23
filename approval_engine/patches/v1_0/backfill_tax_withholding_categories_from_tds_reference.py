# Copyright (c) 2026 8848 Digital LLP. All rights reserved.
# Proprietary and confidential. Unauthorized copying, distribution, or use
# of this file, via any medium, is strictly prohibited without prior
# written permission from 8848 Digital LLP.
"""
Patch: create Tax Withholding Category records for TDS Reference rows that
were already imported before the TDS Reference -> Tax Withholding Category
after_insert hook (doctype/tds_reference/tds_reference_utils.py's create_tax_withholding_categories)
was added.

Idempotent - category creation is guarded by frappe.db.exists(), so re-running
this patch is safe and skips categories that already exist.

Runs in [post_model_sync], which executes before the after_migrate hook that
creates this app's custom fields (create_tax_withholding_categories sets
category.tds_reference, a custom field on Tax Withholding Category) - calling
create_custom_fields() here first guarantees the column exists regardless of
whether this is a fresh site or a re-run, instead of silently creating
categories with an empty tds_reference link.

Registered in patches.txt as:
    approval_engine.patches.v1_0.backfill_tax_withholding_categories_from_tds_reference
"""

import frappe

from approval_engine.approval_settlement.doctype.tds_reference.tds_reference_utils import (
	create_tax_withholding_categories,
)
from approval_engine.approval_settlement.setup import create_custom_fields


def execute():
	create_custom_fields()

	for name in frappe.get_all("TDS Reference", pluck="name"):
		doc = frappe.get_doc("TDS Reference", name)
		create_tax_withholding_categories(doc)

	frappe.db.commit()
