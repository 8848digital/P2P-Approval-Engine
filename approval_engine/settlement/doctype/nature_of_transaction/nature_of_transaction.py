# Copyright (c) 2026 8848 Digital LLP. All rights reserved.
# Proprietary and confidential. Unauthorized copying, distribution, or use
# of this file, via any medium, is strictly prohibited without prior
# written permission from 8848 Digital LLP.

from frappe.model.document import Document


class NatureOfTransaction(Document):
	"""
	Master doctype storing the distinct kinds of financial transaction
	(e.g. Advance, Settlement) used to classify related settlement records.

	Carries no custom validation of its own; uniqueness of
	`nature_of_transition` is enforced by the DocType schema.
	"""

	pass
