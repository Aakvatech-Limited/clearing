# Copyright (c) 2024, Nelson Mpanju and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe import _
from clearing.clearing.doctype.port_clearance.port_clearance import ensure_all_documents_attached

class TRAClearance(Document):

    def before_submit(self):
         ensure_all_documents_attached(self,"tra_clearance_document")
         
         if self.status != "Payment Completed":
             frappe.throw(_("You can't Submit if Payment Completed  is not Completed"))
            
    
    def validate(self):
        self.check_required_documents()

    def check_required_documents(self):
        # Fetch the related Clearing File document
        clearing_file_doc = frappe.get_doc('Clearing File', self.clearing_file)

        # Required documents
        required_docs = ['Packing List', 'Commercial Invoice']

        # Check if each required document is present in the Clearing File's child table 'documents'
        missing_docs = []
        for doc_name in required_docs:
            exists = any(doc.document_name == doc_name for doc in clearing_file_doc.document)
            if not exists:
                missing_docs.append(doc_name)

        # Check if either "Air Waybill (AWB)" or "Bill of Lading B/L" is present
        if clearing_file_doc.mode_of_transport == 'Sea':
            has_bill_of_lading = any(doc.document_name == 'Bill of Lading B/L' for doc in clearing_file_doc.document)
            if not has_bill_of_lading:
                missing_docs.append('Bill of Lading B/L')
        elif clearing_file_doc.mode_of_transport == 'Air':
            has_air_waybill = any(doc.document_name == 'Air Waybill (AWB)' for doc in clearing_file_doc.document)
            if not has_air_waybill:
                missing_docs.append('Air Waybill (AWB)')

        # If any required document is missing, raise a validation error
        if missing_docs:
            frappe.throw(_('The following documents are required before creating TRA Clearance: {0}').format(', '.join(missing_docs)))
