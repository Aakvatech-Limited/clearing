// Copyright (c) 2025, Nelson Mpanju and contributors
// For license information, please see license.txt

frappe.query_reports["Physical Verification Summary"] = {
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
      "fieldname": "verification_status",
      "label": "Verification Status",
      "fieldtype": "Select",
      "options": "\nCompleted\nPending"
    },
    {
      "fieldname": "clearing_file",
      "label": "Clearing File",
      "fieldtype": "Link",
      "options": "Clearing File"
    }
  ]
};
