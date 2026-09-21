# apps/p2p_customization/p2p_customization/patches/v1_0/create_agreement_attachment_faq_record.py
"""
Patch: create the agreement_attachment FAQ Master row on sites where
agreement_po_engagement_letter was already seeded before dependent
attachments became their own FAQ Master rows (field_type Attach +
depends_on_question, see doc_events.faq_master).

A fresh site's seed (create_faq_master.py) already creates this row
directly, right after its trigger question - this patch only backfills
existing sites.

Inserting a new FAQ Master row always lands it at the end of the sort
order (see _auto_set_sort_order - it unconditionally sets sort_order to
max+1 for new docs), so this shifts every row after the trigger by one to
make room, inserts the row, then re-saves it with the correct sort_order
(the is_new() guard in _auto_set_sort_order no longer applies on a second
save) - which also re-triggers sync_supplier_custom_field so the Supplier
Custom Field and web form field land in the right position immediately.

Registered in patches.txt as:
    p2p_customization.patches.v1_0.create_agreement_attachment_faq_record
"""

import frappe

TRIGGER_QUESTION_CODE = "agreement_po_engagement_letter"
QUESTION_CODE = "agreement_attachment"
QUESTION_LABEL = "Agreement / PO / Engagement Letter Copy"


def execute():
	if frappe.db.exists("FAQ Master", QUESTION_CODE):
		return
	if not frappe.db.exists("FAQ Master", TRIGGER_QUESTION_CODE):
		return

	trigger_sort_order = frappe.db.get_value("FAQ Master", TRIGGER_QUESTION_CODE, "sort_order")

	later_rows = frappe.get_all(
		"FAQ Master",
		filters={"sort_order": [">", trigger_sort_order]},
		fields=["name", "sort_order"],
	)
	for row in later_rows:
		frappe.db.set_value("FAQ Master", row.name, "sort_order", row.sort_order + 1, update_modified=False)

	doc = frappe.get_doc(
		{
			"doctype": "FAQ Master",
			"question_code": QUESTION_CODE,
			"question_label": QUESTION_LABEL,
			"field_type": "Attach",
			"options": "",
			"reqd_on_supplier": 0,
			"is_active": 1,
			"description": "Attachment for Agreement/PO/Engagement Letter, required when the corresponding question is answered Yes.",
			"depends_on_question": TRIGGER_QUESTION_CODE,
		}
	).insert(ignore_permissions=True)

	doc.sort_order = trigger_sort_order + 1
	doc.save(ignore_permissions=True)

	frappe.db.commit()
