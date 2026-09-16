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
	return frappe.db.sql(
		"""
		select name, section_as_per_it_act_1961, tds_rate
		from `tabTDS Reference`
		where name like %(txt)s
			or section_as_per_it_act_1961 like %(txt)s
			or tds_rate like %(txt)s
		order by
			case when name = %(exact_txt)s then 0 else 1 end,
			name
		""",
		{
			"txt": "%{}%".format(txt or ""),
			"exact_txt": txt or "",
		},
	)
