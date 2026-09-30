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

P = "zithara_integration.zithara_core.customization"

doc_events = {
	"Sales Invoice": {
		"on_submit": f"{P}.sales_invoice.sales_invoice.on_submit",
		"on_cancel": f"{P}.sales_invoice.sales_invoice.on_cancel",
	},
	"POS Invoice": {
		"on_submit": f"{P}.pos_invoice.pos_invoice.on_submit",
		"on_cancel": f"{P}.pos_invoice.pos_invoice.on_cancel",
	},
	"Payment Entry": {"on_submit": f"{P}.payment_entry.payment_entry.on_submit"},
	"Journal Entry": {"on_submit": f"{P}.journal_entry.journal_entry.on_submit"},
	"Communication": {"after_insert": f"{P}.communication.communication.after_insert"},
	# New records of the configured Store DocType get a Zithara Store; exits after
	# a cached settings lookup for everything else.
	"*": {"after_insert": f"{P}.all.all.after_insert"},
}

scheduler_events = {"hourly": ["zithara_integration.zithara_core.tasks.retry_failed_syncs"]}
