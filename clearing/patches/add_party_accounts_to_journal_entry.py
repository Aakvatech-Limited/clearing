# Copyright (c) 2025, Nelson Mpanju and contributors
# For license information, please see license.txt

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute():
    """Add custom field 'party_accounts' (Table) to Journal Entry."""
    custom_fields = {
        "Journal Entry": [
            {
                "fieldname": "party_accounts",
                "label": "Party Accounts",
                "fieldtype": "Table",
                "options": "JE Party Account",
                "insert_after": "clearing_file",
                "read_only": 1,
                "allow_on_submit": 0,
                "translatable": 0,
            }
        ]
    }

    create_custom_fields(custom_fields, update=True)
    frappe.db.commit()

