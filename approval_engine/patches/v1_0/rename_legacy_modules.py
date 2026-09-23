# Copyright (c) 2026 8848 Digital LLP. All rights reserved.
# Proprietary and confidential. Unauthorized copying, distribution, or use
# of this file, via any medium, is strictly prohibited without prior
# written permission from 8848 Digital LLP.

from approval_engine.install import rename_legacy_modules


def execute():
	"""
	Rename the "Settlement" and "Vendor Portal" modules to "Approval
	Settlement" and "Approval Vendor Portal" on sites that already had
	them (install-app marks patches done without running them, so
	after_install covers fresh installs). See install.rename_legacy_modules.

	Returns:
	        None
	"""
	rename_legacy_modules()
