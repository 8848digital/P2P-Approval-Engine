# Copyright (c) 2026 8848 Digital LLP. All rights reserved.
# Proprietary and confidential. Unauthorized copying, distribution, or use
# of this file, via any medium, is strictly prohibited without prior
# written permission from 8848 Digital LLP.

"""Unit tests for the Payment Entry MSA block (msa_check.py): payment against
a BRN-linked Purchase Invoice or Purchase Order is refused while the
vendor's BRN row says "Has MSA" but has no attachment. Lookups are patched
-- no database needed."""

from unittest.mock import MagicMock, patch

import frappe
from frappe.tests import UnitTestCase

from approval_engine.approval_settlement.customization.payment_entry.msa_check import (
	block_payment_without_msa_attachment,
)

REFERENCES = {
	("Purchase Invoice", "PI-1"): {
		"brn": "BRN-1",
		"supplier": "SUP-1",
		"supplier_name": "Vendor One",
	},
	("Purchase Order", "PO-1"): {"brn": "BRN-1", "supplier": "SUP-1", "supplier_name": "Vendor One"},
	("Purchase Invoice", "PI-NO-BRN"): {
		"brn": None,
		"supplier": "SUP-1",
		"supplier_name": "Vendor One",
	},
}


def _payment_entry(*references):
	"""A Payment Entry stand-in with the given (reference_doctype, reference_name) rows."""
	return frappe._dict(
		references=[frappe._dict(reference_doctype=dt, reference_name=dn) for dt, dn in references]
	)


class TestPaymentEntryMSABlock(UnitTestCase):
	"""block_payment_without_msa_attachment."""

	def _run(self, payment_entry, msa_rows):
		"""Run the check with the given BRN Comparision rows (MSA ticked) returned by get_all."""
		db = MagicMock()
		db.get_value.side_effect = lambda dt, dn, fields, as_dict=False: frappe._dict(
			REFERENCES[(dt, dn)]
		)
		get_all = MagicMock(return_value=[frappe._dict(r) for r in msa_rows])
		with (
			patch("frappe.db", db),
			patch("frappe.get_all", get_all),
			patch("frappe.utils.get_link_to_form", side_effect=lambda dt, dn: dn),
		):
			block_payment_without_msa_attachment(payment_entry)
		return get_all

	def test_invoice_with_missing_attachment_is_blocked(self):
		"""MSA ticked on the vendor's BRN row but no attachment: payment is refused."""
		self.assertRaises(
			frappe.ValidationError,
			self._run,
			_payment_entry(("Purchase Invoice", "PI-1")),
			[{"msa_agreement_attachment": None}],
		)

	def test_advance_against_po_is_blocked(self):
		"""Advance payments against a BRN-linked Purchase Order are checked too."""
		self.assertRaises(
			frappe.ValidationError,
			self._run,
			_payment_entry(("Purchase Order", "PO-1")),
			[{"msa_agreement_attachment": None}],
		)

	def test_attachment_present_passes(self):
		"""With the MSA attachment uploaded, payment goes through."""
		self._run(
			_payment_entry(("Purchase Invoice", "PI-1")), [{"msa_agreement_attachment": "/files/msa.pdf"}]
		)

	def test_reference_without_brn_is_skipped(self):
		"""Documents not linked to a BRN aren't checked at all."""
		get_all = self._run(_payment_entry(("Purchase Invoice", "PI-NO-BRN")), [])
		get_all.assert_not_called()

	def test_query_filters_on_parenttype(self):
		"""Only BRN Comparision rows of a BRN parent are considered."""
		get_all = self._run(_payment_entry(("Purchase Invoice", "PI-1")), [])
		self.assertEqual(get_all.call_args.kwargs["filters"]["parenttype"], "BRN")
