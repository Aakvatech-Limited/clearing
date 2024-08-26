# Clearing Document Python Script for ERPNext
# © 2024, Nelson Mpanju and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document

class ClearingDocument(Document):
    def before_save(self):
        populate_document_in_parent(self)

def populate_document_in_parent(doc):
    parent_doctype_map = {
        "Clearing File": {
            "doctype": "Clearing File",
            "child_table": "document"
        },
        "TRA Clearance": {
            "doctype": "TRA Clearance",
            "child_table": "document",
            "link_field": "clearing_file"  
        },
        "Port Clearance": {
            "doctype": "Port Clearance",
            "child_table": "document",
            "link_field": "clearing_file"  
        },
        "Shipment Clearance": {
            "doctype": "Shipment Clearance",
            "child_table": "document",
            "link_field": "clearing_file"  
        }
    }

    parent_config = parent_doctype_map.get(doc.linked_file)

    if parent_config:
        if parent_config['doctype'] == "Clearing File":
            parent_doc = frappe.get_doc(parent_config['doctype'], doc.clearing_file)
        else:
            parent_doc = frappe.get_doc(parent_config['doctype'], {parent_config['link_field']: doc.clearing_file})

        if not parent_doc.meta.has_field(parent_config['child_table']):
            frappe.throw(f"The child table '{parent_config['child_table']}' does not exist in '{parent_config['doctype']}'.")

        document_attributes = ""
        for row in doc.clearing_document_attributes:
            attribute = row.document_attribute
            value = row.document_attribute_value
            if attribute and value:
                document_attributes += f"{attribute}: {value}\n"

        existing_entry = None
        for entry in parent_doc.get(parent_config['child_table']):
            if entry.document_name == doc.document_type:
                existing_entry = entry
                break

        if existing_entry:
            # Update the existing entry with the new attributes
            existing_entry.document_received = doc.get("document_received", 1)
            existing_entry.view_document = doc.document_attachment
            existing_entry.submission_date = doc.get("submission_date", frappe.utils.now_datetime())
            existing_entry.document_attributes = document_attributes
            frappe.msgprint(f"Document {doc.document_type} in {parent_config['doctype']} updated successfully.")
        else:
            # Append a new document entry
            document_entry = {
                "document_name": doc.document_type,
                'view_document': doc.document_attachment,
                "document_received": doc.get("document_received", 1), 
                "submission_date": doc.get("submission_date", frappe.utils.now_datetime()),
                "document_attributes": document_attributes
            }
            parent_doc.append(parent_config['child_table'], document_entry)
            frappe.msgprint(f"Document {doc.document_type} appended to {parent_config['doctype']}.")

        parent_doc.save()

