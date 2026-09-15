frappe.listview_settings["Supplier Quotation"] = {
	onload(listview) {

		listview.page.add_inner_button(__("Upload Supplier Quotation"), () => {

			new frappe.ui.FileUploader({
				doctype: "Supplier Quotation",
				folder: "Home",
				allow_multiple: false,

				on_success(file) {

					// file.name     -> File Docname
					// file.file_url -> Uploaded file URL

					frappe.call({
						method: "p2p_customization.settlement.doc_events.supplier_quotation.create_supplier_quotation_from_file",
						args: {
							file_id: file.name
						},
						freeze: true,
						freeze_message: __("Creating Supplier Quotation..."),
						callback(r) {

							if (!r.exc) {

								frappe.show_alert({
									message: __("Supplier Quotation Created Successfully"),
									indicator: "green"
								});

								// if (r.message) {
								// 	frappe.set_route(
								// 		"Form",
								// 		"Supplier Quotation",
								// 		r.message
								// 	);
								// }

								listview.refresh();
							}
						}
					});
				}
			});

		});

	}
};