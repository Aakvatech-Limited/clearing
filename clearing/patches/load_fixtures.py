import json
import os
import frappe

folder = "./fixtures_json"


def load_json(file):
    """Load JSON data from fixtures_json folder"""
    CURR_DIR = os.path.abspath(os.path.dirname(__file__))
    json_file_path = os.path.join(CURR_DIR, folder, file)
    
    if not os.path.exists(json_file_path):
        return []
        
    with open(json_file_path, "r") as f:
        data = json.load(f)
    return data


def create_documents_from_json(documents_data):
    """Create documents from JSON data"""
    if not isinstance(documents_data, list):
        return
        
    for doc_data in documents_data:
        if not isinstance(doc_data, dict):
            continue
            
        doctype = doc_data.get("doctype")
        if not doctype:
            continue
            
        # For Clearing Document Type, use document_type as the name
        if doctype == "Clearing Document Type":
            name = doc_data.get("document_type")
        else:
            # For other doctypes like Item, use the name field
            name = doc_data.get("name") or doc_data.get("item_code")
            
        if not name:
            continue
            
        # Check if document already exists (idempotent)
        if frappe.db.exists(doctype, name):
            continue
            
        try:
            # Create new document
            doc = frappe.get_doc(doc_data)
            doc.insert(ignore_permissions=True, ignore_if_duplicate=True)
            frappe.db.commit()
            
        except frappe.DuplicateEntryError:
            # Skip if duplicate (race condition safety)
            continue
        except Exception:
            frappe.log_error(
                title=f"Clearing: Failed to insert {doctype} '{name}'",
                message=frappe.get_traceback(),
            )


def execute():
    """
    Load all fixtures from JSON files in fixtures_json folder.
    Following the icd_tz/csf_tz pattern for master data creation.
    """
    # Get all JSON files in the fixtures_json folder
    CURR_DIR = os.path.abspath(os.path.dirname(__file__))
    fixtures_dir = os.path.join(CURR_DIR, folder)
    
    if not os.path.exists(fixtures_dir):
        return
        
    files = [f for f in os.listdir(fixtures_dir) if f.endswith('.json')]
    
    for file in files:
        try:
            data = load_json(file)
            create_documents_from_json(data)
        except Exception:
            frappe.log_error(
                title=f"Clearing: Failed to process fixture file '{file}'",
                message=frappe.get_traceback(),
            )
