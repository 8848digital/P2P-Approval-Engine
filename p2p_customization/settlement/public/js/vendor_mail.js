frappe.provide("p2p_customization.vendor");

p2p_customization.vendor = {
	send_vendor_invitation_mail(doctype, docname = null, default_email = null, default_vendor_name = null, default_company = null) {
		frappe.dom.unfreeze();

		return new Promise((resolve, reject) => {
			const show_prompt = (vendor_name = "", read_only = 0) => {
				frappe.prompt(
					[
						{
							label: "Name",
							fieldname: "name",
							fieldtype: "Data",
							default: vendor_name,
							read_only: read_only,
						},
						{
							label: "Company",
							fieldname: "company",
							fieldtype: "Link",
							options: "Company",
							// Auto-captured from BRN's own Company field when called
							// from there -- still editable, same as Name.
							default: default_company || "",
							reqd: 1,
						},
						{
							label: "Email 1",
							fieldname: "email",
							fieldtype: "Data",
							// Auto-captured from the comparison table's Preferred
							// row when called from BRN -- still editable, just
							// pre-filled, same as Name already is.
							default: default_email || "",
							reqd: 1,
						},
						{
							label: "Email 2 (Optional)",
							fieldname: "email_2",
							fieldtype: "Data",
						},
						{
							fieldname: "kyc_note",
							fieldtype: "HTML",
							options:
								'<div class="text-muted small" style="margin-top: -8px;">' +
								"Please update the email Id of the vendor who will be providing " +
								"necessary KYC Requirements for vendor registration." +
								"</div>",
						},
					],
					(values) => {
						const email_pattern = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

						if (!email_pattern.test(values.email)) {
							frappe.msgprint("Please enter a valid email for Email 1");
							return;
						}
						if (values.email_2 && !email_pattern.test(values.email_2)) {
							frappe.msgprint("Please enter a valid email for Email 2");
							return;
						}

						frappe.call({
							method: "p2p_customization.settlement.api.v1.vendor_email.send_vendor_mail",
							args: {
								reference_doctype: doctype,
								reference_docname: docname,
								mail: values.email,
								email_2: values.email_2,
								name: values.name,
								company: values.company,
							},
							callback: function (r) {
								if (r.message) {
									if (r.message.status === "success") {
										frappe.msgprint(r.message.message);
										resolve();
									} else {
										frappe.msgprint("Error: " + r.message.message);
										reject();
									}
								} else {
									reject();
								}
							},
						});
					},
					// Only one account is ever created, against Email 1 --
					// Email 2 (when given) just also receives that same
					// invite/login link, for a second contact at the vendor.
					"Please Enter Vendor Details",
					"Submit"
				);
			};

			if (doctype === "Supplier") {
				show_prompt();
				return;
			}

			if (default_vendor_name) {
				// BRN with a Preferred comparison row already gives us the
				// vendor name directly -- no need for the extra round trip
				// below to BRN's own (unrelated) new_vendor field.
				show_prompt(default_vendor_name, 1);
				return;
			}

			frappe.db.get_value(doctype, docname, "new_vendor")
				.then((r) => {
					const vendor_name = r.message?.new_vendor || "";
					show_prompt(vendor_name, vendor_name ? 1 : 0);
				})
				.catch(() => {
					show_prompt();
				});
		});
	},
};
