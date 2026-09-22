# Copyright (c) 2026, p2p_customization
import frappe
from frappe.model.document import Document

STATUS_STYLE = {
	"Success": {"color": "#2f9e44", "bg": "#ebfbee", "icon": "&#10003;"},  # check
	"Failed": {"color": "#e03131", "bg": "#fff5f5", "icon": "&#10007;"},  # cross
	"Error": {"color": "#e8590c", "bg": "#fff4e6", "icon": "&#9888;"},  # warn
	"Skipped": {"color": "#868e96", "bg": "#f1f3f5", "icon": "&#8226;"},
	"Pending": {"color": "#1971c2", "bg": "#e7f5ff", "icon": "&#8987;"},
}


def build_status_html(status: str) -> str:
	"""Render a colored pill span for status, per STATUS_STYLE (falls back
	to the Pending style for an unrecognised status)."""
	style = STATUS_STYLE.get(status, STATUS_STYLE["Pending"])
	return (
		f'<span style="display:inline-flex;align-items:center;gap:4px;'
		f"padding:2px 10px;border-radius:12px;font-size:11px;font-weight:600;"
		f'color:{style["color"]};background:{style["bg"]};border:1px solid {style["color"]}33;">'
		f"{style['icon']} {status}</span>"
	)


class KYCValidationLog(Document):
	"""KYC Validation Run child table row: one attempt of one vendor check
	against one Supplier."""

	def validate(self) -> None:
		"""Default checked_on/checked_by/attempt_no, and keep status_html
		in sync with the current status value."""
		if not self.checked_on:
			self.checked_on = frappe.utils.now_datetime()
		if not self.checked_by:
			self.checked_by = frappe.session.user
		if not self.attempt_no:
			self.attempt_no = 1
		# keep the rendered pill in sync with the raw status value at all times
		self.status_html = build_status_html(self.status or "Pending")
