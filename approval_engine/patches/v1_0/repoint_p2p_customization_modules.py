# Copyright (c) 2026 8848 Digital LLP. All rights reserved.
# Proprietary and confidential. Unauthorized copying, distribution, or use
# of this file, via any medium, is strictly prohibited without prior
# written permission from 8848 Digital LLP.

from approval_engine.install import repoint_p2p_customization_module_defs


def execute():
	"""
	Hand the Settlement and Vendor Portal Module Defs over from
	p2p_customization to approval_engine on sites where approval_engine was
	already installed (install-app marks patches done without running them,
	so after_install covers fresh installs). See
	install.repoint_p2p_customization_module_defs.

	Returns:
		None
	"""
	repoint_p2p_customization_module_defs()
