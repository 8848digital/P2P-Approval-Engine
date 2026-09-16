# Copyright (c) 2026, p2p_customization
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

	return frappe.db.sql(
		"""
		select name, section_as_per_it_act_1961, tds_rate
		from `tabTDS Reference`
		where (
				name like %(txt)s
				or section_as_per_it_act_1961 like %(txt)s
				or tds_rate like %(txt)s
			)
			and name in %(allowed_services)s
		order by
			case when name = %(exact_txt)s then 0 else 1 end,
			name
		""",
		{
			"txt": "%{}%".format(txt or ""),
			"exact_txt": txt or "",
			"allowed_services": allowed_services,
		},
	)
