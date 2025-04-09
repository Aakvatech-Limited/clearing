from frappe import _
import frappe

def get_data():
    # Get mode_of_transport from current doc
    mode_of_transport = frappe.db.get_value("Clearing File", frappe.form_dict.name, "mode_of_transport")
    
    clearance_processes = ["TRA Clearance", "Physical Verification", "Port Clearance"]
    
    # Only include Shipping Line Clearance if not Air transport
    if mode_of_transport != "Air":
        clearance_processes.append("Shipping Line Clearance")
        
    return {
        "fieldname": "name",
        "non_standard_fieldnames": {
            "TRA Clearance": "clearing_file",
            "Physical Verification": "clearing_file",
            "Shipping Line Clearance": "clearing_file",
            "Port Clearance": "clearing_file",
            "Clearing Document": "clearing_file",
            "Clearing Charges": "clearing_file",
        },
        "transactions": [
            {
                "label": _("Clearance Processes"),
                "items": clearance_processes
            },
            {
                "label": _("Attached Documents"),
                "items": ["Clearing Document"]
            },
            {
                "label": _("Finance"),
                "items": ["Clearing Charges"]
            }
        ]
    }