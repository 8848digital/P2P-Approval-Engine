# apps/p2p_customization/p2p_customization/patches/v1_0/gate_faq_section_visibility.py
"""
Patch: apply FAQ_SECTION_VISIBILITY_DEPENDS_ON to the existing
Supplier-faq_section Custom Field on sites where add_vendor_faq_coc_fields
already ran (so it created faq_section without the depends_on that patch
now carries for fresh installs).

faq_section is the last Tab Break on Supplier - hiding it hides every field
in and after the Vendor FAQs tab (questions, Code of Conduct, FAQ change
log) in one place, gated on JFS Settings.enable_faq_section plus the new
Vendor FAQ Manager role (see boot.boot_session and fixtures/role.json).

Registered in patches.txt as:
    p2p_customization.patches.v1_0.gate_faq_section_visibility
"""

from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

from p2p_customization.settlement.doc_events.faq_master import (
    FAQ_SECTION_VISIBILITY_DEPENDS_ON,
)


def execute():
    custom_fields = {
        "Supplier": [
            {
                "fieldname": "faq_section",
                "fieldtype": "Tab Break",
                "label": "Vendor FAQs",
                "insert_after": "non_pan",
                "depends_on": FAQ_SECTION_VISIBILITY_DEPENDS_ON,
            },
        ]
    }
    create_custom_fields(custom_fields, update=True)
