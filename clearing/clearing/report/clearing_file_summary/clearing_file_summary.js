// Copyright (c) 2025, Nelson Mpanju and contributors
// For license information, please see license.txt

frappe.query_reports["Clearing File Summary"] = {
	"filters": [
    {"fieldname": "from_date", "label": "From Date", "fieldtype": "Date", "reqd": 1},
    {"fieldname": "to_date", "label": "To Date", "fieldtype": "Date", "reqd": 1},
    {"fieldname": "status", "label": "Status", "fieldtype": "Select", "options": "\nOpen\nPre-Lodged\nOn Process\nCleared\nBills Paid\nDelivered\nCancelled"},
    {"fieldname": "customer", "label": "Consignee", "fieldtype": "Link", "options": "Customer"},
    {"fieldname": "clearing_file", "label": "Clearing File", "fieldtype": "Link", "options": "Clearing File"},
    {"fieldname": "mode_of_transport", "label": "Mode of Transport", "fieldtype": "Link", "options": "Mode of Transport"},
    {"fieldname": "declaration_type", "label": "Declaration Type", "fieldtype": "Select", "options": "\nEX1 EXPORTATION\nEX2 TEMPORARY EXPORT\nEX3 RE-EXPORT\nIM4 ENTRY FOR HOME USE\nIM5 TEMPORARY IMPORTATION\nIM6 RE-IMPORTATION\nIM7 ENTRY FOR WAREHOUSING\nIM8 TRANSIT AND TRANSHIPMENT\nIM9 OTHER IMPORT PROCEDURES"},
    {"fieldname": "cl_plan", "label": "CL Plan", "fieldtype": "Select", "options": "\nPAD Pre-Arrival Declaration\nPMD Post-Manifest Declaration\nLAD Land Arrival Declaration\nEWD EX Warehouse Declaration\nPBD Passangers Baggage Declaration\nCGD Courier Goods Declaration\nEXD Export Declaration\nPCD Pre-Arrival Courier Declaration\nPOE Post Entry\nESA Escrow Accounts\nUCP Use for Other Purposes"}
  ]
};
