# Copyright (c) 2026 8848 Digital LLP. All rights reserved.
# Proprietary and confidential. Unauthorized copying, distribution, or use
# of this file, via any medium, is strictly prohibited without prior
# written permission from 8848 Digital LLP.

# Copyright (c) 2026, Satya and Contributors
# See license.txt

from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase, UnitTestCase

from approval_engine.settlement.doctype.portal_invoice_log.utils import (
	get_po_text,
	send_portal_invoice_notification,
)

# On IntegrationTestCase, the doctype test records and all
# link-field test record dependencies are recursively loaded
# Use these module variables to add/remove to/from that list
EXTRA_TEST_RECORD_DEPENDENCIES = []  # eg. ["User"]
IGNORE_TEST_RECORD_DEPENDENCIES = []  # eg. ["User"]


class IntegrationTestPortalInvoiceLog(IntegrationTestCase):
	"""
	Integration tests for PortalInvoiceLog.
	Use this class for testing interactions between multiple components.
	"""

	def test_create_portal_invoice_log(self) -> None:
		"""
		Creating a Portal Invoice Log entry succeeds even with no linked
		Purchase Invoice/Supplier, since neither field is mandatory.
		"""
		doc = frappe.get_doc(doctype="Portal Invoice Log")

		with patch("frappe.enqueue"):
			doc.insert()

		self.assertTrue(doc.name)

	def test_after_insert_enqueues_notification_job(self) -> None:
		"""
		after_insert queues send_portal_invoice_notification on the
		"short" queue, passing this log's own name.
		"""
		doc = frappe.get_doc(doctype="Portal Invoice Log")

		with patch("frappe.enqueue") as mock_enqueue:
			doc.insert()

		self.assertEqual(mock_enqueue.call_count, 1)
		_, kwargs = mock_enqueue.call_args
		self.assertEqual(kwargs["method"], send_portal_invoice_notification)
		self.assertEqual(kwargs["queue"], "short")
		self.assertEqual(kwargs["log_name"], doc.name)


class UnitTestPortalInvoiceLogUtils(UnitTestCase):
	"""
	Unit tests for the pure/mockable logic in portal_invoice_log/utils.py.
	"""

	def test_get_po_text_joins_unique_sorted_purchase_orders(self) -> None:
		"""
		get_po_text returns a sorted, comma-separated, de-duplicated list
		of Purchase Order names, skipping rows without one.
		"""
		pi = frappe._dict(
			items=[
				frappe._dict(purchase_order="PO-0002"),
				frappe._dict(purchase_order="PO-0001"),
				frappe._dict(purchase_order="PO-0001"),
				frappe._dict(purchase_order=None),
			]
		)

		self.assertEqual(get_po_text(pi), "PO-0001, PO-0002")

	def test_get_po_text_returns_na_when_no_purchase_orders(self) -> None:
		"""
		get_po_text falls back to "N/A" when no item row references a
		Purchase Order.
		"""
		pi = frappe._dict(items=[frappe._dict(purchase_order=None)])

		self.assertEqual(get_po_text(pi), "N/A")

	def test_send_portal_invoice_notification_skips_when_email_not_configured(self) -> None:
		"""
		send_portal_invoice_notification exits early and logs an error
		instead of trying to load the Purchase Invoice when no default
		outgoing Email Account is configured.
		"""
		with (
			patch(
				"approval_engine.settlement.doctype.portal_invoice_log.utils.is_email_configured",
				return_value=None,
			),
			patch("frappe.get_doc") as mock_get_doc,
			patch("frappe.log_error") as mock_log_error,
		):
			send_portal_invoice_notification("Nonexistent Log Name")

		mock_get_doc.assert_not_called()
		mock_log_error.assert_called_once()
