# apps/p2p_customization/p2p_customization/patches/v1_0/create_faq_master.py
import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute():
    _create_faq_master_doctype()
    _create_supplier_faq_answer_doctype()
    _seed_faq_master_questions()


def _create_faq_master_doctype():
    if frappe.db.exists("DocType", "FAQ Master"):
        return
    frappe.get_doc({
        "doctype": "DocType",
        "name": "FAQ Master",
        "module": "settlement",
        "custom": 1,
        "naming_rule": "By fieldname",
        "autoname": "field:question_code",
        "fields": [
            {"fieldname": "question_code", "label": "Question Code", "fieldtype": "Data",
             "reqd": 1, "unique": 1, "in_list_view": 1,
             "description": "Must be a valid fieldname: lowercase letters, numbers, underscores only. Becomes the Supplier fieldname directly."},
            {"fieldname": "question_label", "label": "Question", "fieldtype": "Data",
             "reqd": 1, "in_list_view": 1},
            {"fieldname": "options", "label": "Answer Options", "fieldtype": "Small Text",
             "reqd": 1, "default": "\nYes\nNo",
             "description": "Newline-separated list of selectable answers, e.g.\nYes\nNo  (leading blank line = optional/unanswered state)."},
            {"fieldname": "expected_answer", "label": "Expected Answer", "fieldtype": "Data",
             "in_list_view": 1,
             "description": "Optional. If set, must exactly match one of the values in Answer Options. Leave blank if this question has no right/wrong answer (e.g. informational questions)."},
            {"fieldname": "reqd_on_supplier", "label": "Mandatory on Supplier Form", "fieldtype": "Check",
             "default": "1"},
            {"fieldname": "sort_order", "label": "Sort Order", "fieldtype": "Int",
             "default": "0", "in_list_view": 1},
            {"fieldname": "is_active", "label": "Is Active", "fieldtype": "Check",
             "default": "1", "in_list_view": 1},
            {"fieldname": "description", "label": "Description", "fieldtype": "Small Text"},
        ],
        "sort_field": "sort_order",
        "sort_order": "ASC",
        "permissions": [
            {"role": "System Manager", "read": 1, "write": 1, "create": 1, "delete": 1},
        ],
    }).insert(ignore_permissions=True)


def _create_supplier_faq_answer_doctype():
    if frappe.db.exists("DocType", "Supplier FAQ Answer"):
        return
    frappe.get_doc({
        "doctype": "DocType",
        "name": "Supplier FAQ Answer",
        "module": "settlement",
        "custom": 1,
        "istable": 1,
        "editable_grid": 1,
        "fields": [
            {"fieldname": "faq_question", "label": "Question", "fieldtype": "Link",
             "options": "FAQ Master", "reqd": 1, "read_only": 1,
             "in_list_view": 1, "columns": 4},
            {"fieldname": "question_label", "label": "Question Text", "fieldtype": "Data",
             "fetch_from": "faq_question.question_label", "read_only": 1,
             "in_list_view": 1, "columns": 5},
            {"fieldname": "answer", "label": "Answer", "fieldtype": "Select",
             "options": "\nYes\nNo", "reqd": 1, "in_list_view": 1, "columns": 3},
        ],
        "permissions": [
            {"role": "System Manager", "read": 1, "write": 1, "create": 1},
        ],
    }).insert(ignore_permissions=True)


def _seed_faq_master_questions():
    """Seeds FAQ Master with all 6 vendor onboarding questions, including
    sustainable_goods_percentage (4-option, no enforced expected_answer)."""
    yes_no = "\nYes\nNo"
    sustainability_options = (
        "\n100% of the goods or service provided"
        "\n80% to 100% of the goods or service provided"
        "\n70% to 80% of the goods or service provided"
        "\nBelow 70% of the goods or services provided"
    )

    questions = [
        # question_code, label, options, expected_answer, reqd, order, description,
        # field_type, depends_on_question
        ("vendor_related_to_employee_director",
         "Vendor related to any employee/Director of the Company?",
         yes_no, "No", 1, 1,
         "Vendor related to any employee/Director of the Company?",
         "Select", None),
        ("related_partys",
         "Related Party?",
         yes_no, "No", 1, 2,
         "Related Party?",
         "Select", None),
        ("agreement_po_engagement_letter",
         "Agreement/PO/Engagement Letter exists? (If there is an Agreement or Engagement Letter, please upload the copy)",
         yes_no, "Yes", 1, 3,
         "Agreement/PO/Engagement Letter exists? (If there is an Agreement or Engagement Letter, please upload the copy)",
         "Select", None),
        # Dependent attachment - a FAQ Master row like any other, just with
        # field_type Attach and depends_on_question pointing at the question
        # above. Its Supplier/web form field is created, positioned right
        # after agreement_po_engagement_letter, and deleted through the exact
        # same generic path as every other row - no special-casing needed.
        ("agreement_attachment",
         "Agreement / PO / Engagement Letter Copy",
         "", "", 0, 4,
         "Attachment for Agreement/PO/Engagement Letter, required when the corresponding question is answered Yes.",
         "Attach", "agreement_po_engagement_letter"),
        ("pan_aadhaar_linked_field",
         "PAN & Aadhaar linking/seeding to avoid short deduction due to vendor default",
         yes_no, "Yes", 1, 5,
         "PAN & Aadhaar linking/seeding to avoid short deduction due to vendor default",
         "Select", None),
        ("sustainable_goods_percentage",
         "What % of the goods or service being provided by you is offered in a sustainable manner?",
         sustainability_options, "", 1, 6,
         "What % of the goods or service being provided by you is offered in a sustainable manner?",
         "Select", None),
        ("aadhaar_consent",
         "Aadhar Consent",
         yes_no, "Yes", 1, 7,
         "If you choose to provide Aadhaar, you consent to its use only for verification and record "
         "purposes, and it will be stored and processed securely in compliance with applicable UIDAI regulations.",
         "Select", None),
    ]

    for question_code, label, options, expected, reqd, order, desc, field_type, depends_on_question in questions:
        if frappe.db.exists("FAQ Master", question_code):
            continue
        frappe.get_doc({
            "doctype": "FAQ Master",
            "question_code": question_code,
            "question_label": label,
            "field_type": field_type,
            "options": options,
            "expected_answer": expected,
            "reqd_on_supplier": reqd,
            "sort_order": order,
            "is_active": 1,
            "description": desc,
            "depends_on_question": depends_on_question,
        }).insert(ignore_permissions=True)