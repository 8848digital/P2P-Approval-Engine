# Copyright (c) 2026 8848 Digital LLP. All rights reserved.
# Proprietary and confidential. Unauthorized copying, distribution, or use
# of this file, via any medium, is strictly prohibited without prior
# written permission from 8848 Digital LLP.
"""Link-field search logic for Purchase Invoice customizations.

Not whitelisted itself -- called from the thin wrapper in
settlement/api/v1/purchase_invoice.py.
"""

import frappe


def get_nature_of_service_options_for_supplier(txt: str, supplier: str | None):
	"""
	Search TDS Reference records for BRN's Nature of Service Table
	MultiSelect, restricted to only the values selected on the linked
	Supplier's Nature of Services multiselect.

	Parameters:
	        txt (str, required): The search text typed into the multiselect.
	        supplier (str, optional): The Supplier to restrict allowed services to.
	                Returns an empty list if not given.

	Returns:
	        list[tuple]: Rows of (name, section_as_per_it_act_1961, tds_rate).
	"""
	if not supplier:
		return []

	allowed_services = frappe.get_all(
		"Nature of Service Reference",
		filters={"parent": supplier, "parenttype": "Supplier"},
		pluck="nature_of_service",
	)

	if not allowed_services:
		return []

	TDS = frappe.qb.DocType("TDS Reference")
	txt_like = f"%{txt or ''}%"
	exact_txt = txt or ""

	return (
		frappe.qb.from_(TDS)
		.select(TDS.name, TDS.section_as_per_it_act_1961, TDS.tds_rate)
		.where(
			(TDS.name.like(txt_like))
			| (TDS.section_as_per_it_act_1961.like(txt_like))
			| (TDS.tds_rate.like(txt_like))
		)
		.where(TDS.name.isin(allowed_services))
		.orderby(TDS.name != exact_txt)
		.orderby(TDS.name)
	).run()
