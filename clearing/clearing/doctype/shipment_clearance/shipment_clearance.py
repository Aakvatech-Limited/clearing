# Copyright (c) 2024, Nelson Mpanju and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from clearing.clearing.doctype.port_clearance.port_clearance import ensure_all_documents_attached

class ShipmentClearance(Document):
	def before_submit(self):
		ensure_all_documents_attached(self,"Shipment_clearance_document")
		
		if self.status != "Paid":
			frappe.throw(_("You can't Submit if Payment Completed  is not Completed"))
