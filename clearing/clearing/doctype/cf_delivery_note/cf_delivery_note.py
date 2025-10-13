# Copyright (c) 2024, Nelson Mpanju and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import nowdate


class CFDeliveryNote(Document):

    def validate(self):
        """Auto-check `has_container_interchange` if any cargo package type
        on the linked Clearing File has `has_container_interchange` enabled.
        """
        try:
            if not self.clearing_file:
                return

            # Fetch package types from the Clearing File's cargo rows
            cargo_rows = frappe.get_all(
                "Cargo",
                filters={
                    "parenttype": "Clearing File",
                    "parent": self.clearing_file,
                },
                fields=["package_type"],
            )

            package_types = [row.get("package_type") for row in cargo_rows if row.get("package_type")]
            if not package_types:
                return

            # Check if any of the package types is flagged to require container interchange
            flagged = frappe.get_all(
                "Package Type",
                filters={
                    "name": ["in", package_types],
                    "has_container_interchange": 1,
                },
                limit=1,
            )

            if flagged:
                self.has_container_interchange = 1
        except Exception:
            # Don't block save due to any lookup error; log for visibility
            frappe.log_error(frappe.get_traceback(), "CF Delivery Note: set has_container_interchange from Package Type failed")

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
