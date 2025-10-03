# Copyright (c) 2024, Nelson Mpanju and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import nowdate


class CFDeliveryNote(Document):

    def before_submit(self):
        # Check if the Delivery Note has a linked Clearing File
        if not self.clearing_file:
            frappe.throw(
                _(
                    "This Delivery Note is not linked to a Clearing File. Please link a Clearing File before submitting."
                )
            )

        # Get the linked Clearing File document
        clearing_file_doc = frappe.get_doc("Clearing File", self.clearing_file)

        # Check if the Clearing File status is 'Cleared'
        if clearing_file_doc.status == "Cleared":
            # Update the status of the Delivery Note to 'Delivered'
            clearing_file_doc.status = "Delivered"
            clearing_file_doc.save()
        else:
            # Raise an error if the Clearing File is not cleared
            frappe.throw(
                _(
                    "The linked Clearing File {0} is not cleared. You must clear it before submitting the Delivery Note."
                ).format(self.clearing_file)
            )

    def on_update(self):
        if not self.has_container_interchange:
            return

        if not self.clearing_file:
            return

        filters = {
            "clearing_file": self.clearing_file,
            "posting_date": self.posting_date,
        }

        container_name = frappe.db.exists("Container Interchange", filters)

        if not container_name:
            container = frappe.new_doc("Container Interchange")
            container.clearing_file = self.clearing_file
            container.posting_date = self.posting_date or nowdate()
            container.insert()
            container_name = container.name

        if container_name and self.container_interchange != container_name:
            frappe.db.set_value(
                "CF Delivery Note",
                self.name,
                "container_interchange",
                container_name,
                update_modified=False,
            )
            self.container_interchange = container_name
