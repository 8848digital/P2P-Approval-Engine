# Copyright (c) 2026 8848 Digital LLP. All rights reserved.
# Proprietary and confidential. Unauthorized copying, distribution, or use
# of this file, via any medium, is strictly prohibited without prior
# written permission from 8848 Digital LLP.

"""Seed questions for create_faq_master.py - split out to keep that patch
file under the line-count cap."""

YES_NO = "\nYes\nNo"
SUSTAINABILITY_OPTIONS = (
	"\n100% of the goods or service provided"
	"\n80% to 100% of the goods or service provided"
	"\n70% to 80% of the goods or service provided"
	"\nBelow 70% of the goods or services provided"
)

FAQ_QUESTIONS = [
	# question_code, label, options, expected_answer, reqd, order, description,
	# field_type, depends_on_question
	(
		"vendor_related_to_employee_director",
		"Vendor related to any employee/Director of the Company?",
		YES_NO,
		"No",
		1,
		1,
		"Vendor related to any employee/Director of the Company?",
		"Select",
		None,
	),
	("related_partys", "Related Party?", YES_NO, "No", 1, 2, "Related Party?", "Select", None),
	(
		"agreement_po_engagement_letter",
		"Agreement/PO/Engagement Letter exists? (If there is an Agreement or Engagement Letter, please upload the copy)",
		YES_NO,
		"Yes",
		1,
		3,
		"Agreement/PO/Engagement Letter exists? (If there is an Agreement or Engagement Letter, please upload the copy)",
		"Select",
		None,
	),
	# Dependent attachment - a FAQ Master row like any other, just with
	# field_type Attach and depends_on_question pointing at the question
	# above. Its Supplier/web form field is created, positioned right
	# after agreement_po_engagement_letter, and deleted through the exact
	# same generic path as every other row - no special-casing needed.
	(
		"agreement_attachment",
		"Agreement / PO / Engagement Letter Copy",
		"",
		"",
		0,
		4,
		"Attachment for Agreement/PO/Engagement Letter, required when the corresponding question is answered Yes.",
		"Attach",
		"agreement_po_engagement_letter",
	),
	(
		"pan_aadhaar_linked_field",
		"PAN & Aadhaar linking/seeding to avoid short deduction due to vendor default",
		YES_NO,
		"Yes",
		1,
		5,
		"PAN & Aadhaar linking/seeding to avoid short deduction due to vendor default",
		"Select",
		None,
	),
	(
		"sustainable_goods_percentage",
		"What % of the goods or service being provided by you is offered in a sustainable manner?",
		SUSTAINABILITY_OPTIONS,
		"",
		1,
		6,
		"What % of the goods or service being provided by you is offered in a sustainable manner?",
		"Select",
		None,
	),
	(
		"aadhaar_consent",
		"Aadhar Consent",
		YES_NO,
		"Yes",
		1,
		7,
		"If you choose to provide Aadhaar, you consent to its use only for verification and record "
		+ "purposes, and it will be stored and processed securely in compliance with applicable UIDAI regulations.",
		"Select",
		None,
	),
]
