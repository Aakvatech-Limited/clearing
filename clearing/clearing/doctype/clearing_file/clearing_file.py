import frappe
from frappe.model.document import Document
from frappe import _


class ClearingFile(Document):
    def before_save(self):
        # Check and possibly update status, but do not enforce it strictly
        self.check_and_update_status()

    def before_submit(self):
        # On submit, enforce that all required documents are attached
        ensure_all_documents_attached(self, "clearing_file_document")

        # Check if clearing charges exist and validate the amounts only if relevant doctypes have total charges
        self.check_and_validate_clearing_charges()

    def check_and_update_status(self):
        # Required fields for "Pre-Lodged" status
        required_fields = {
            "tancis_lodging_date": self.tancis_lodging_date,
            "reference_no": self.reference_no,
            "tansad_no": self.tansad_no,
            "declaration_type": self.declaration_type,
            "cl_plan": self.cl_plan,
        }

        missing_fields = [
            field_name
            for field_name, field_value in required_fields.items()
            if not field_value
        ]

        if not missing_fields:
            if self.status == "Open":
                self.status = "Pre-Lodged"
        else:
            pass

    def check_and_validate_clearing_charges(self):
        # Fetch the total charges from each related doctype
        related_doctypes = [
            {
                "doctype": "TRA Clearance",
                "charge_type": "TRA Clearance",
                "field": "total_charges",
            },
            {
                "doctype": "Port Clearance",
                "charge_type": "Port Clearance",
                "field": "total_charges",
            },
            {
                "doctype": "Shipment Clearance",
                "charge_type": "Shipment Clearance",
                "field": "total_charges",
            },
            {
                "doctype": "Physical Verification",
                "charge_type": "Physical Verification",
                "field": "total_charges",
            },
        ]

        charges_needed = False

        # Loop through each related doctype and check if it has total charges > 0
        for doc_info in related_doctypes:
            related_docs = frappe.get_all(
                doc_info["doctype"],
                filters={"clearing_file": self.name},
                fields=[doc_info["field"]],
            )

            if related_docs:
                total_charges = related_docs[0][doc_info["field"]]

                # If there are total charges, we need to validate clearing charges
                if total_charges > 0:
                    charges_needed = True

                    # Ensure clearing charges exist
                    clearing_charges = frappe.get_all(
                        "Clearing Charges",
                        filters={"clearing_file": self.name},
                        fields=["name"],
                    )

                    if not clearing_charges:
                        frappe.throw(
                            _(
                                "No Clearing Charges have been created for this Clearing File. Please create the charges before submitting."
                            )
                        )

                    # Get the clearing charge document
                    clearing_charge_doc = frappe.get_doc(
                        "Clearing Charges", clearing_charges[0].name
                    )

                    # Check if the corresponding charge type exists in Clearing Charges
                    matching_charge = next(
                        (
                            charge
                            for charge in clearing_charge_doc.charges
                            if charge.charge_type == doc_info["charge_type"]
                        ),
                        None,
                    )

                    if not matching_charge:
                        frappe.throw(
                            _(
                                "Clearing Charges entry for {0} is missing. Please create the corresponding charge."
                            ).format(doc_info["charge_type"])
                        )

                    # Check if the amount matches
                    if matching_charge.amount != total_charges:
                        frappe.throw(
                            _(
                                "The amount for {0} does not match the expected value. Expected: {1}, Found: {2}."
                            ).format(
                                doc_info["charge_type"],
                                total_charges,
                                matching_charge.amount,
                            )
                        )

        # If any of the related Doctypes has total charges, ensure that corresponding clearing charges are created
        if charges_needed:
            pass
        else:
            # If no charges are needed, allow the submission without further validation
            frappe.msgprint(
                _(
                    "No related charges found in the related doctypes, submission allowed."
                )
            )


def ensure_all_documents_attached(self, type):
    # Fetch required documents for "Pre-Lodged" status from "Mode of Transport Detail"
    required_docs = frappe.db.get_all(
        "Mode of Transport Detail",
        filters={"parentfield": type, "parent": self.mode_of_transport},
        fields=["clearing_document_type"],
    )
    # Convert list of dictionaries into a simple list of document names
    required_doc_names = [doc["clearing_document_type"] for doc in required_docs]

    # Check if each required document is present in the Clearing File's child table 'documents'
    missing_docs = []
    for doc_name in required_doc_names:
        exists = any(doc.document_name == doc_name for doc in self.document)
        if not exists:
            missing_docs.append(doc_name)
    # If documents are missing, prevent submission
    if missing_docs:
        missing_docs_str = ", ".join(missing_docs)
        frappe.throw(
            _(
                "The following required documents are missing and must be attached before submission: {0}"
            ).format(missing_docs_str),
            frappe.ValidationError,
        )


@frappe.whitelist()
def get_address_display_from_link(doctype, name):
    if not doctype or not name:
        return {"address_display": "", "customer_address": ""}

    addresses = frappe.get_all(
        "Address", filters={"link_doctype": doctype, "link_name": name}, fields=["name"]
    )

    if not addresses:
        return {"address_display": "", "customer_address": ""}

    address = frappe.get_doc("Address", addresses[0].name)
    address_display = get_address_display(address.as_dict())

    return {"address_display": address_display, "customer_address": addresses[0].name}


@frappe.whitelist()
def update_status_to_cleared(doc, method):
    clearing_file_name = doc.clearing_file

    # List of related doctypes to check submission status
    related_doctypes = [
        {"doctype": "TRA Clearance", "link_field": "clearing_file"},
        {"doctype": "Shipment Clearance", "link_field": "clearing_file"},
        {"doctype": "Physical Verification", "link_field": "clearing_file"},
        {"doctype": "Port Clearance", "link_field": "clearing_file"},
    ]

    for doc_type in related_doctypes:
        linked_docs = frappe.get_all(
            doc_type["doctype"], filters={doc_type["link_field"]: clearing_file_name}
        )

        if not linked_docs:
            return

        not_submitted_docs = frappe.get_all(
            doc_type["doctype"],
            filters={doc_type["link_field"]: clearing_file_name, "docstatus": 0},
        )

        if not_submitted_docs:
            return

    clearing_file_doc = frappe.get_doc("Clearing File", clearing_file_name)
    if clearing_file_doc.status != "Cleared":
        clearing_file_doc.status = "Cleared"
        clearing_file_doc.save()
