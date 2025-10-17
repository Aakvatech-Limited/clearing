# Copyright (c) 2025, Nelson Mpanju and contributors
# For license information, please see license.txt

import frappe


def execute():
    """Remove obsolete Journal Entry custom field and child table."""

    cf_name = frappe.db.get_value(
        "Custom Field",
        {"dt": "Journal Entry", "fieldname": "party_accounts"},
        "name",
    )

    if cf_name:
        try:
            frappe.delete_doc("Custom Field", cf_name, force=1, ignore_permissions=True)
        except Exception:
            frappe.db.sql("DELETE FROM `tabCustom Field` WHERE name = %s", (cf_name,))

    if frappe.db.table_exists("JE Party Account"):
        frappe.db.sql("DROP TABLE IF EXISTS `tabJE Party Account`")

    frappe.db.commit()

