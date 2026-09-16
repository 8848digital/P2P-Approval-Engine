# Copyright (c) 2026, p2p_customization
"""Link-field search logic for Supplier customizations.

Not whitelisted itself -- called from the thin wrapper in
settlement/api/v1/supplier.py.
"""

import frappe


def get_nature_of_service_options(txt: str):
	"""
	Search TDS Reference records for the Supplier Nature of Service Table
	MultiSelect, unpaginated so it isn't capped at the default page length.

	Parameters:
		txt (str, required): The search text typed into the multiselect.

	Returns:
		list[tuple]: Rows of (name, section_as_per_it_act_1961, tds_rate).
	"""
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
		.orderby(TDS.name != exact_txt)
		.orderby(TDS.name)
	).run()
