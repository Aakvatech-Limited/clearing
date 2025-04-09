import frappe
from frappe import _

def validate_unique_document(doc):
    """Validate document uniqueness for all clearance types"""
    if not doc.get("document_name"):
        return
        
    parent = doc.get("parent")
    parenttype = doc.get("parenttype")
    
    if parent and parenttype:
        # Check for duplicates in the same parent document
        filters = {
            "document_name": doc.document_name,
            "parent": parent,
            "parenttype": parenttype,
            "name": ("!=", doc.name)
        }
        
        if frappe.db.exists(doc.doctype, filters):
            frappe.throw(
                _("Document {0} already exists in this {1}").format(
                    frappe.bold(doc.document_name),
                    parenttype.replace(" ", " ").title()
                ),
                title=_("Duplicate Document")
            )

def before_delete(doc, method):
    """Allow deletion but show confirmation if document has attributes"""
    if doc.doctype == "Clearing Document" and doc.get("clearing_document_attributes"):
        frappe.msgprint(
            _("This document contains attributes. Are you sure you want to delete it?"),
            title=_("Confirm Deletion"),
            indicator="orange"
        )