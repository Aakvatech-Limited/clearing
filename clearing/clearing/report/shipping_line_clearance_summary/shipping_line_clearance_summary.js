// Copyright (c) 2025, Nelson Mpanju and contributors
// For license information, please see license.txt

frappe.query_reports["Shipping Line Clearance Summary"] = {
	"filters": [
    {
      "fieldname": "from_date",
      "label": "From Date",
      "fieldtype": "Date",
      "reqd": 1
    },
    {
      "fieldname": "to_date",
      "label": "To Date",
      "fieldtype": "Date",
      "reqd": 1
    },
    {
      "fieldname": "consignee",
      "label": "Consignee",
      "fieldtype": "Link",
      "options": "Customer"
    },
    {
      "fieldname": "status",
      "label": "Status",
      "fieldtype": "Select",
      "options": "\nPayment Pending\nPayment Completed"
    },
    {
      "fieldname": "clearing_file",
      "label": "Clearing File",
      "fieldtype": "Link",
      "options": "Clearing File"
    }
  ]
};
