# Copyright (c) 2024, Nelson Mpanju and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document

class PortClearance(Document):
	def before_submit(self):
		if self.status != "Paid":
			frappe.throw(_("You can't Submit if Payment Completed  is not Completed"))

	def before_submit(self):
        # On submit, enforce that all required documents are attached
    		ensure_all_documents_attached(self,"port_clearance_document")


def ensure_all_documents_attached(self,type):
        # Fetch required documents for "Pre-Lodged" status from "Mode of Transport Detail"
        required_docs = frappe.db.get_all(
            "Mode of Transport Detail",
            filters={
                "parentfield": type,
                'parent':frappe.db.get_value('Clearing File',self.clearing_file,'mode_of_transport')
            },
            fields=['clearing_document_type']
        )
        frappe.throw(str(required_docs))
        # Convert list of dictionaries into a simple list of document names
        required_doc_names = [doc['clearing_document_type'] for doc in required_docs]

        # Check if each required document is present in the Clearing File's child table 'documents'
        missing_docs = []
        for doc_name in required_doc_names:
            exists = any(doc.document_name == doc_name for doc in self.document)
            if not exists:
                missing_docs.append(doc_name)
        # If documents are missing, prevent submission
        if missing_docs:
            missing_docs_str = ', '.join(missing_docs)
            frappe.throw(_('The following required documents are missing and must be attached before submission: {0}')
                        .format(missing_docs_str), frappe.ValidationError)