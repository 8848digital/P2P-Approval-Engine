# Copyright (c) 2026, Satya and contributors
# For license information, please see license.txt

# import frappe
from frappe.model.document import Document


class RequisitionID(Document):
	pass

def block_requisition_id(doc, method):
	if doc.requisition_id:
		existing_doc = frappe.get_all('Requisition ID', filters={'requisition_id': doc.requisition_id, 'name': ['!=', doc.name]})
		if existing_doc:
			frappe.throw(f"Requisition ID '{doc.requisition_id}' already exists in another document.")