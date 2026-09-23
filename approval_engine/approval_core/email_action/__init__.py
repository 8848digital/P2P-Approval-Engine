# Copyright (c) 2026 8848 Digital LLP. All rights reserved.
# Proprietary and confidential. Unauthorized copying, distribution, or use
# of this file, via any medium, is strictly prohibited without prior
# written permission from 8848 Digital LLP.
"""Act on a governed document from an email, without logging in.

Flow: a state change emails each approver of the tier that must act a personal,
single-use link (`notify.py`, `action_link.py`). The link opens the guest page
`/approval_action`; the approver picks an action, requests a one-time code sent to
their own mailbox (`otp.py`), and confirms. The action then runs through Frappe's
standard `apply_workflow` *as that approver* (`link_actions.py`, `session.py`), so
every workflow condition, band check and audit record applies unchanged.
"""
