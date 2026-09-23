# Copyright (c) 2026 8848 Digital LLP. All rights reserved.
# Proprietary and confidential. Unauthorized copying, distribution, or use
# of this file, via any medium, is strictly prohibited without prior
# written permission from 8848 Digital LLP.

# apps/approval_engine/approval_engine/patches/v1_0/add_vendor_faq_coc_fields.py
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

from approval_engine.settlement.doctype.faq_master.faq_master_utils import (
	FAQ_SECTION_VISIBILITY_DEPENDS_ON,
)


def execute():
	"""Creates only the STATIC structural fields for the vendor FAQ tab.
	Every actual FAQ question (Yes/No or otherwise, including
	sustainable_goods_percentage and dependent attachments like
	agreement_attachment, which are just FAQ Master rows with field_type
	Attach and depends_on_question set) is now created dynamically from FAQ
	Master rows via doctype/faq_master/faq_master_utils.py — do NOT add question fields here.
	coc_section starts anchored to faq_section here and gets repositioned
	after the real trailing question by _reposition_tail_fields() once FAQ
	Master rows are seeded.

	faq_section also carries FAQ_SECTION_VISIBILITY_DEPENDS_ON so the whole
	tab (everything through faq_change_log, the last field on Supplier) is
	hidden unless JFS Settings.enable_faq_section is on and the user has the
	Vendor FAQ Manager (or System Manager) role - see
	gate_faq_section_visibility for the same fix applied to sites where this
	patch already ran.
	"""
	custom_fields = {
		"Supplier": [
			{
				"fieldname": "faq_section",
				"label": "Vendor FAQs",
				"fieldtype": "Tab Break",
				"insert_after": "non_pan",
				"depends_on": FAQ_SECTION_VISIBILITY_DEPENDS_ON,
			},
			{
				"fieldname": "coc_section",
				"label": "Code of Conduct",
				"fieldtype": "Section Break",
				"insert_after": "faq_section",
			},
			{
				"fieldname": "code_of_conduct_html",
				"fieldtype": "HTML",
				"insert_after": "coc_section",
			},
			{
				"fieldname": "code_of_conduct_accepted",
				"label": "I Accept the Code of Conduct",
				"fieldtype": "Check",
				"reqd": 0,
				"insert_after": "code_of_conduct_html",
			},
		]
	}
	create_custom_fields(custom_fields, update=True)
