# Copyright (c) 2026 8848 Digital LLP. All rights reserved.
# Proprietary and confidential. Unauthorized copying, distribution, or use
# of this file, via any medium, is strictly prohibited without prior
# written permission from 8848 Digital LLP.

"""Zithara flags sent to the desk at login."""

from zithara_integration.zithara_core.services.loyalty import redemption_enabled


def boot_session(bootinfo) -> None:
	"""
	Tell the desk whether the Zithara loyalty buttons should show.

	Parameters:
	        bootinfo (frappe._dict, required): Boot info sent to the browser.

	Returns:
	        None
	"""
	bootinfo.zithara = {"loyalty_redemption": redemption_enabled()}
