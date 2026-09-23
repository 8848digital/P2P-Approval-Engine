# Copyright (c) 2026 8848 Digital LLP. All rights reserved.
# Proprietary and confidential. Unauthorized copying, distribution, or use
# of this file, via any medium, is strictly prohibited without prior
# written permission from 8848 Digital LLP.

# import frappe
from frappe.model.document import Document


class DocumentWorkflowLog(Document):
	"""Audit record of one workflow state change: who moved the document, from where to where, and why."""

	pass
