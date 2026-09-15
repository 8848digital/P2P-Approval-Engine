# Copyright (c) 2026, p2p_customization
import json
import re
import frappe
from frappe.model.document import Document

PLACEHOLDER_RE = re.compile(r"\{\{\s*([a-zA-Z0-9_]+)\s*\}\}")

class KYCVendor(Document):
	def validate(self):
		self.endpoint_path = (self.endpoint_path or "").strip()
		self.success_path = (self.success_path or "").strip()

		self.validate_credential()
		self.validate_endpoint_path()
		self.validate_field_map()
		self.validate_template_placeholders()
		self.validate_json_template()
		self.validate_success_path()
		self.validate_response_classification()
	def autoname(self):
		self.name = f"{self.kyc_type} - {self.vendor}"

	def validate_credential(self):
		if not self.credential:
			frappe.throw(frappe._("Credential is mandatory"))

		is_active = frappe.db.get_value("KYC Credential", self.credential, "is_active")
		if is_active is None:
			frappe.throw(frappe._("Selected Credential {0} does not exist").format(self.credential))
		if self.enabled and not is_active:
			frappe.throw(
				frappe._(
					"Credential '{0}' is marked Inactive in JFS Settings. "
					"Activate it or disable this KYC Vendor."
				).format(self.credential)
			)

	def validate_endpoint_path(self):
		if not self.endpoint_path:
			frappe.throw(frappe._("Endpoint Path is required"))
		if self.endpoint_path.startswith("http://") or self.endpoint_path.startswith("https://"):
			frappe.throw(
				frappe._(
					"Endpoint Path should be a relative path (e.g. /api/v1/corporate/gstin), "
					"not a full URL. The Base URL already comes from the linked Credential."
				)
			)
		if not self.endpoint_path.startswith("/"):
			self.endpoint_path = "/" + self.endpoint_path

	def validate_field_map(self):
		if self.enabled and not self.field_map:
			frappe.throw(
				frappe._(
					"At least one Field Map row is required so the API knows which Supplier "
					"field(s) to send (e.g. gstin -> id_number)."
				)
			)

		seen_keys = set()
		for row in self.field_map:
			if row.placeholder_key in seen_keys:
				frappe.throw(
					frappe._("Duplicate placeholder key '{0}' in Field Map row #{1}").format(
						row.placeholder_key, row.idx
					)
				)
			seen_keys.add(row.placeholder_key)

	def validate_template_placeholders(self):
		"""Every {{token}} used in the template/endpoint must exist in field_map,
		and warn (don't block) if a mapped field is unused."""
		if self.request_style == "Query Params":
			template_text = self.endpoint_path or ""
		else:
			template_text = self.request_body_template or ""

		used_tokens = set(PLACEHOLDER_RE.findall(template_text))
		mapped_tokens = {row.placeholder_key for row in self.field_map}

		missing = used_tokens - mapped_tokens
		if missing:
			frappe.throw(
				frappe._(
					"Template uses placeholder(s) {0} that are not defined in Field Map. "
					"Add a Field Map row for each, or remove them from the template."
				).format(", ".join(sorted(missing)))
			)

		unused = mapped_tokens - used_tokens
		if unused and self.request_style != "Query Params":
			frappe.msgprint(
				frappe._(
					"Note: Field Map key(s) {0} are not referenced anywhere in the Request Body Template."
				).format(", ".join(sorted(unused))),
				indicator="orange",
				alert=True,
			)

	def validate_json_template(self):
		if self.request_style != "JSON Body":
			return
		if not self.request_body_template:
			frappe.throw(frappe._("Request Body Template is required for JSON Body style"))

		# Substitute dummy values and confirm it's syntactically valid JSON
		dummy = self.request_body_template
		for row in self.field_map:
			dummy = dummy.replace("{{" + row.placeholder_key + "}}", row.sample_value or "TEST123")

		try:
			json.loads(dummy)
		except json.JSONDecodeError as e:
			frappe.throw(
				frappe._("Request Body Template is not valid JSON once placeholders are filled: {0}").format(
					str(e)
				)
			)

	def validate_success_path(self):
		if not self.success_path:
			frappe.throw(
				frappe._(
					"Success Path is required — this is the JSON key checked in the response "
					"to decide Success vs Failed (e.g. data.gstin or success)."
				)
			)

	def validate_response_classification(self):
		# normalize keyword list: strip blanks/whitespace, lowercase for matching later
		if self.system_error_type_keywords:
			lines = [ln.strip() for ln in self.system_error_type_keywords.splitlines() if ln.strip()]
			self.system_error_type_keywords = "\n".join(lines)

		if self.expected_success_value and not self.success_path:
			frappe.throw(
				frappe._("Expected Value at Success Path requires Success Path to also be set")
			)
