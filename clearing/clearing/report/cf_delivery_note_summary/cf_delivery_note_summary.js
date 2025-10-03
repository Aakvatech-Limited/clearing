// Copyright (c) 2025, Nelson Mpanju and contributors
// For license information, please see license.txt

frappe.query_reports["CF Delivery Note Summary"] = {
	"filters": [
    {"fieldname": "from_date", "label": "From Date", "fieldtype": "Date", "reqd": 1},
    {"fieldname": "to_date", "label": "To Date", "fieldtype": "Date", "reqd": 1},
    {"fieldname": "consignee", "label": "Consignee", "fieldtype": "Link", "options": "Customer"},
    {"fieldname": "clearing_file", "label": "Clearing File", "fieldtype": "Link", "options": "Clearing File"},
    {"fieldname": "delivery_id", "label": "Delivery ID", "fieldtype": "Link", "options": "CF Delivery Note"},
    {"fieldname": "has_container_interchange", "label": "Has Container Interchange", "fieldtype": "Check"}
  ]
};
