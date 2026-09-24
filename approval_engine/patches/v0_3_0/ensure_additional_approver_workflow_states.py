# Copyright (c) 2026 8848 Digital LLP. All rights reserved.
# Proprietary and confidential. Unauthorized copying, distribution, or use
# of this file, via any medium, is strictly prohibited without prior
# written permission from 8848 Digital LLP.
from approval_engine.approval_core.generator import ensure_workflow_states


def execute():
	"""
	Create Workflow State masters for the additional approver states on existing sites.

	The additional approver feature introduced two new states ("Additionally Approved"
	and "On Hold by Additional Approver"). These masters are normally created when a
	matrix is submitted, but sites that had matrices submitted before the feature
	shipped never got them — causing LinkValidationError when cancelling a matrix
	(build_workflow references the states but they don't exist).

	Returns:
		None
	"""
	ensure_workflow_states()
