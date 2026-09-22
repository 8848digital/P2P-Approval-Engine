# Copyright (c) 2026 8848 Digital LLP. All rights reserved.
# Proprietary and confidential. Unauthorized copying, distribution, or use
# of this file, via any medium, is strictly prohibited without prior
# written permission from 8848 Digital LLP.

"""
Patch: create the Settlement custom fields (Supplier, Purchase Order,
Purchase Invoice, etc. -- everything under settlement/custom_fields/)
before any other post_model_sync patch runs.

hooks.py also wires approval_engine.settlement.setup.create_custom_fields
as an after_migrate hook, which is idempotent and safe to run again -- but
after_migrate fires only after every patch in this file has already run.
create_faq_master's FAQ Master.after_insert doc_event
(doc_events.faq_master.sync_supplier_custom_field -> faq_master_sync.
rebuild_web_form_faq_fields) saves the "vendor-onboarding-form" Web Form,
which validates that every field it references (gstin, pan, brn,
workflow_state, ...) already exists as a Custom Field on Supplier -- on a
fresh site those fields don't exist yet at that point unless this patch
runs first. Existing sites that installed these fields via an earlier,
separate migration never hit this ordering gap; a from-scratch install
does.

Registered in patches.txt as:
    approval_engine.patches.v1_0.create_settlement_custom_fields_early
"""

from approval_engine.settlement.setup import create_custom_fields


def execute():
	create_custom_fields()
