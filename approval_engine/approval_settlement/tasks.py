# Copyright (c) 2026 8848 Digital LLP. All rights reserved.
# Proprietary and confidential. Unauthorized copying, distribution, or use
# of this file, via any medium, is strictly prohibited without prior
# written permission from 8848 Digital LLP.

"""Scheduled jobs for the Approval Settlement module (targets of hooks.py's
scheduler_events). Thin wrappers -- the logic lives next to the feature.
"""

from approval_engine.approval_settlement.customization.purchase_invoice.itc_reversal import (
	run_daily_itc_reversal_sweep,
)
from approval_engine.approval_settlement.doctype.vendor_email.utils import (
	send_reminder_for_non_registered_vendors,
)


def send_vendor_onboarding_reminders() -> None:
	"""
	Daily 09:00: remind invited vendors who still haven't completed the
	onboarding form.

	Returns:
	        None
	"""
	send_reminder_for_non_registered_vendors()


def reverse_prior_year_itc() -> None:
	"""
	Daily: re-check every ITC Reversal Log not yet Reversed and post the
	reversal Journal Entry for any invoice that has now crossed its cut-off.

	Returns:
	        None
	"""
	run_daily_itc_reversal_sweep()
