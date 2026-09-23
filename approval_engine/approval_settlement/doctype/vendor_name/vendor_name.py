# Copyright (c) 2026 8848 Digital LLP. All rights reserved.
# Proprietary and confidential. Unauthorized copying, distribution, or use
# of this file, via any medium, is strictly prohibited without prior
# written permission from 8848 Digital LLP.

from frappe.model.document import Document


class VendorName(Document):
	"""
	Master doctype storing distinct vendor names for use elsewhere in the
	settlement module (e.g. as a selectable reference list).

	Carries no custom validation of its own; uniqueness of `vendor` is
	enforced by the DocType schema.
	"""

	pass
