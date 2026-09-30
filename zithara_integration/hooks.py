# Copyright (c) 2026 8848 Digital LLP. All rights reserved.
# Proprietary and confidential. Unauthorized copying, distribution, or use
# of this file, via any medium, is strictly prohibited without prior
# written permission from 8848 Digital LLP.

app_name = "zithara_integration"
app_title = "Zithara Integration"
app_publisher = "8848 Digital LLP"
app_description = "Zithara integration for Frappe/ERPNext"
app_email = "mahak@8848digital.com"
app_license = "Proprietary"

required_apps = ["erpnext"]

custom_fixtures = [{"dt": "Custom Field", "filters": {"module": "Zithara Core"}}]

commands = ["zithara_integration.commands.export_fixtures.export_fixtures"]

after_request = [
	"zithara_integration.utils.api_handlers.response_formatter.format_frappe_response_to_custom"
]
