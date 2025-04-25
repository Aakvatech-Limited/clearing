import frappe

def set_dynamic_item_defaults():
    """
    Patch to programmatically set item_defaults for service Items
    based on the site\'s default company and warehouse.
    """
    # Fetch site defaults
    default_company = frappe.defaults.get_global_default("company")
    stock_settings = frappe.get_doc("Stock Settings")
    default_wh = stock_settings.default_warehouse

    # List of service Items to update
    items = [
        "TRA Clearance", "Port Clearance",
        "Shipping Line Clearance", "Physical Verification"
    ]

    for item_name in items:
        if frappe.db.exists("Item", item_name):
            item = frappe.get_doc("Item", item_name)
            # Only append if no defaults exist
            if not item.item_defaults:
                item.append("item_defaults", {
                    "company": default_company,
                    "default_warehouse": default_wh
                })
                item.save(ignore_permissions=True)
