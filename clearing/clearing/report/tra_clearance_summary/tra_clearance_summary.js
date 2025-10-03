// Copyright (c) 2025, Nelson Mpanju and contributors
// For license information, please see license.txt

frappe.query_reports["TRA Clearance Summary"] = {
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
    },
    {
      "fieldname": "declaration_type",
      "label": "Declaration Type",
      "fieldtype": "Select",
      "options": "\nEX1 EXPORTATION\nEX2 TEMPORARY EXPORT\nEX3 RE-EXPORT\nIM4 ENTRY FOR HOME USE\nIM5 TEMPORARY IMPORTATION\nIM6 RE-IMPORTATION\nIM7 ENTRY FOR WAREHOUSING\nIM8 TRANSIT AND TRANSHIPMENT\nIM9 OTHER IMPORT PROCEDURES"
    }
  ]
};
