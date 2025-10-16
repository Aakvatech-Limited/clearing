# Copyright (c) 2024, Nelson Mpanju and contributors
# For license information, please see license.txt

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute():
    """
    Add custom field 'clearing_file' to Journal Entry doctype
    """
    custom_fields = {
        "Journal Entry": [
            {
                "fieldname": "clearing_file",
                "label": "Clearing File",
                "fieldtype": "Link",
                "options": "Clearing File",
                "insert_after": "user_remark",
                "read_only": 1,
                "allow_on_submit": 0,
                "translatable": 0,
            }
        ]
    }
    
    create_custom_fields(custom_fields, update=True)
    frappe.db.commit()

