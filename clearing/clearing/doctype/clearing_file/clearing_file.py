import frappe
from frappe.model.document import Document
from frappe.contacts.doctype.address.address import get_address_display
from frappe import _
from frappe.utils import cstr


class ClearingFile(Document):
    def before_save(self):
        # Check and possibly update status, but do not enforce it strictly
        self.check_and_update_status()
        # Block saving if TANCIS details are filled before reaching Open
        self.validate_tancis_details_before_open()
        # Check if declaration type is IM8 and update port clearance transit bond
        self.update_port_clearance_transit_bond()
        # Prevent editing TANCIS details after they have been captured
        self.enforce_tancis_fields_immutable()

    def before_submit(self):
        if self.status == "Delivered" and not self._has_clearing_charges():
            frappe.throw(
                _("Create Clearing Charges for this file before submitting."),
                title=_("Clearing Charges Required"),
            )
        # Allow submission only when payment has been received
        if self.status != "Payment Received":
            frappe.throw(
                _("Cannot submit Clearing File unless status is Payment Received."),
                title=_("Invalid Status"),
            )
        self._validate_container_interchange_submission()
        # On submit, enforce that all required documents are attached
        ensure_all_documents_attached(self, "clearing_file_document")
        self.check_and_validate_clearing_charges()

        # Check if clearing charges exist and validate the amounts only if relevant doctypes have total charges
        self.check_and_validate_clearing_charges()

        # Check for unreturned transit bonds and show notification
        self.check_transit_bond_status()

    def on_update_after_submit(self):
        # Check for unreturned transit bonds when status changes to Delivered
        if self.status == "Delivered":
            self.check_transit_bond_status()

    def on_submit(self):
        # Upon submission, mark as Closed
        try:
            frappe.db.set_value(self.doctype, self.name, "status", "Closed")
            self.status = "Closed"
        except Exception:
            pass

    def check_and_update_status(self):
        # First check for transit documents to set status to "Open"
        self.check_clearing_documents_and_update_status()

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

    def check_clearing_documents_and_update_status(self):
        """Check if required transit documents are attached and update status to Open"""
        if not self.mode_of_transport:
            return

        required_clearing_docs = self.get_required_clearing_documents()
        attached_docs = self.get_attached_clearing_documents()
        missing_clearing_docs = self.get_missing_clearing_documents(
            required_clearing_docs, attached_docs
        )

        if missing_clearing_docs:
            missing_labels = ", ".join(missing_clearing_docs)
            frappe.msgprint(
                _(
                    "To move this Clearing File to 'Open', attach the following clearing documents: {0}"
                ).format(missing_labels),
                title=_("Clearing Documents Required"),
                indicator="orange",
            )

        frappe.logger().info(
            "Tancis Document Check - Mode: %s, Required: %s, Attached: %s, Missing: %s, Status: %s"
            % (
                self.mode_of_transport,
                required_clearing_docs,
                attached_docs,
                missing_clearing_docs,
                self.status,
            )
        )

        if not missing_clearing_docs and self.status in ["Draft", ""]:
            old_status = self.status
            self.status = "Open"
            frappe.msgprint(
                _(
                    "Clearing File status updated from '{0}' to 'Open' - All required clearing documents are attached"
                ).format(old_status),
                title=_("Clearing Documents Complete"),
                indicator="green",
            )
            frappe.logger().info(
                "Status updated from %s to Open for Clearing File %s"
                % (old_status, self.name)
            )

    def get_required_clearing_documents(self):
        base_required_docs = [
            "Authorization Letter",
            "Commercial Invoice",
            "Packing List",
        ]

        if self.mode_of_transport == "Air":
            return base_required_docs + ["Air Waybill (AWB)"]
        if self.mode_of_transport == "Sea":
            return base_required_docs + ["Bill of Lading B/L"]

        return base_required_docs + ["Air Waybill (AWB)"]

    def get_attached_clearing_documents(self):
        documents = getattr(self, "document", None) or []
        return [
            doc.document_name
            for doc in documents
            if getattr(doc, "document_name", None)
        ]

    def get_missing_clearing_documents(self, required_docs=None, attached_docs=None):
        required_docs = required_docs or self.get_required_clearing_documents()
        attached_docs = attached_docs or self.get_attached_clearing_documents()
        return [doc for doc in required_docs if doc not in attached_docs]

    def validate_tancis_details_before_open(self):
        """Prevent saving TANCIS details before status reaches Open."""
        tancis_fields = [
            "tancis_lodging_date",
            "reference_no",
            "tansad_no",
            "declaration_type",
            "cl_plan",
        ]

        if not any(self.get(field) for field in tancis_fields):
            return

        allowed_statuses = {
            "Open",
            "Pre-Lodged",
            "On Process",
            "Cleared",
            "Bills Paid",
            "Delivered",
        }

        if self.status not in allowed_statuses:
            current_status = self.status or _("Draft")
            missing_clearing_docs = self.get_missing_clearing_documents()
            if missing_clearing_docs:
                doc_list = ", ".join(missing_clearing_docs)
                message = _(
                    "Cannot save TANCIS details while Clearing File status is {0}. Attach the following clearing documents first: {1}."
                ).format(current_status, doc_list)
            else:
                message = _(
                    "Cannot save TANCIS details while Clearing File status is {0}"
                ).format(current_status)

            frappe.throw(message, title=_("Status Must Be Open"))

    def enforce_tancis_fields_immutable(self):
        """Disallow changes to TANCIS fields after values have been saved."""
        if self.is_new():
            return

        tancis_fields = [
            "tancis_lodging_date",
            "reference_no",
            "tansad_no",
            "declaration_type",
            "cl_plan",
            "awbbl_no",
        ]

        before = self.get_doc_before_save()

        for fieldname in tancis_fields:
            previous_value = None
            if before:
                previous_value = before.get(fieldname)

            if previous_value is None:
                previous_value = self.get_db_value(fieldname)

            # Allow the first submission of a value
            if previous_value in (None, ""):
                continue

            current_value = self.get(fieldname)
            if cstr(current_value).strip() == cstr(previous_value).strip():
                continue

            meta_field = self.meta.get_field(fieldname)
            label = meta_field.label if meta_field else fieldname
            frappe.throw(
                _("You cannot change this field after it has been set."),
                title=label,
            )

    def _has_clearing_charges(self) -> bool:
        if self.is_new() or not self.name:
            return False
        return bool(
            frappe.db.exists(
                "Clearing Charges",
                {"clearing_file": self.name, "docstatus": ["<", 2]},
            )
        )

    def _validate_container_interchange_submission(self):
        if self.is_new() or not self.name:
            return
        info = check_container_interchange_completion(self.name)
        final_done = bool(info.get("final_done"))
        refund_done = bool(info.get("refund_done"))
        pending_steps = []
        if not final_done:
            pending_steps.append(_("Final EIR"))
        if not refund_done:
            pending_steps.append(_("Container Deposit Refund"))
        if pending_steps:
            frappe.throw(
                _("Complete Container Interchange before submitting: {0}").format(
                    ", ".join(pending_steps)
                ),
                title=_("Container Interchange Incomplete"),
            )

    def check_and_validate_clearing_charges(self):
        mode_of_transport = self.mode_of_transport
        # Fetch the total charges from each related doctype
        related_doctypes = [
            {
                "doctype": "TRA Clearance",
                "charge_type": "TRA Clearance",
                "field": "total_charges",
                "paid_by_agent_field": "paid_by_clearing_agent",
            },
            {
                "doctype": "Port Clearance",
                "charge_type": "Port Clearance",
                "field": "total_charges",
                "paid_by_agent_field": "paid_by_clearing_agent",
            },
            {
                "doctype": "Physical Verification",
                "charge_type": "Physical Verification",
                "field": "total_charges",
                "paid_by_agent_field": "paid_by_clearing_agent",
            },
        ]

        if mode_of_transport != "Air":
            related_doctypes.append({
                "doctype": "Shipping Line Clearance",
                "charge_type": "Shipping Line Clearance",
                "field": "total_charges",
                "paid_by_agent_field": "paid_by_clearing_agent",
            })

        charges_needed = False

        # Loop through each related doctype and check if it has total charges > 0
        for doc_info in related_doctypes:
            related_docs = frappe.get_all(
                doc_info["doctype"],
                filters={
                    "clearing_file": self.name,
                    doc_info["paid_by_agent_field"]: 1,
                },
                fields=[doc_info["field"]],
            )

            if related_docs:
                total_charges = related_docs[0].get(doc_info["field"], 0)

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

    def update_port_clearance_transit_bond(self):
        """Update has_transit_bond in Port Clearance when declaration_type is IM8 TRANSIT AND TRANSHIPMENT"""
        if self.declaration_type == "IM8 TRANSIT AND TRANSHIPMENT":
            # Find existing Port Clearance documents linked to this clearing file
            port_clearances = frappe.get_all(
                "Port Clearance",
                filters={"clearing_file": self.name},
                fields=["name", "has_transit_bond"]
            )

            for port_clearance in port_clearances:
                if not port_clearance.has_transit_bond:
                    # Update the Port Clearance to check has_transit_bond
                    frappe.db.set_value(
                        "Port Clearance",
                        port_clearance.name,
                        "has_transit_bond",
                        1
                    )
                    frappe.msgprint(
                        _("Transit Bond has been automatically checked for Port Clearance {0} due to IM8 TRANSIT AND TRANSHIPMENT declaration type.").format(port_clearance.name),
                        title=_("Transit Bond Updated")
                    )

    def check_transit_bond_status(self):
        """Check for unreturned transit bonds and display notification"""
        if self.declaration_type == "IM8 TRANSIT AND TRANSHIPMENT":
            # Check if bond_returned is not checked
            if not self.bond_returned:
                # Find Port Clearance documents with transit bonds
                port_clearances_with_bonds = frappe.get_all(
                    "Port Clearance",
                    filters={
                        "clearing_file": self.name,
                        "has_transit_bond": 1
                    },
                    fields=["name", "ref_key"]
                )

                if port_clearances_with_bonds:
                    port_clearance_refs = []
                    for pc in port_clearances_with_bonds:
                        ref_info = pc.name
                        if pc.ref_key:
                            ref_info += f" (Ref: {pc.ref_key})"
                        port_clearance_refs.append(ref_info)

                    port_clearance_list = ", ".join(port_clearance_refs)

                    frappe.msgprint(
                        _("Alert: Transit Bond has not yet been returned for this IM8 TRANSIT AND TRANSHIPMENT declaration. Port Clearance references: {0}").format(port_clearance_list),
                        title=_("Transit Bond Alert"),
                        indicator="orange"
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
def check_status_change_for_transit_bond(doc, method):
    """Hook function to check transit bond status when Clearing File status changes"""
    if hasattr(doc, '_doc_before_save') and doc._doc_before_save:
        old_status = doc._doc_before_save.get('status')
        new_status = doc.status

        # Check if status changed to Delivered
        if old_status != new_status and new_status == "Delivered":
            clearing_file_doc = frappe.get_doc("Clearing File", doc.name)
            clearing_file_doc.check_transit_bond_status()

@frappe.whitelist()
def update_status_to_cleared(doc, method):
    clearing_file_name = doc.clearing_file

    # Fetch the Clearing File's mode_of_transport
    mode_of_transport = frappe.db.get_value(
        "Clearing File", clearing_file_name, "mode_of_transport"
    )

    # List of related doctypes to check submission status
    related_doctypes = [
        {"doctype": "TRA Clearance", "link_field": "clearing_file"},
        {"doctype": "Physical Verification", "link_field": "clearing_file"},
        {"doctype": "Port Clearance", "link_field": "clearing_file"},
    ]

    # Include Shipping Line Clearance only if mode is NOT Air
    if mode_of_transport != "Air":
        related_doctypes.append(
            {"doctype": "Shipping Line Clearance", "link_field": "clearing_file"}
        )

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


@frappe.whitelist()
def check_container_interchange_completion(clearing_file: str) -> dict:
    if not clearing_file:
        return {"final_done": False, "refund_done": False}

    records = frappe.get_all(
        "Container Interchange",
        filters={"clearing_file": clearing_file},
        fields=["final", "refund"],
    )

    final_done = any(record.get("final") for record in records)
    refund_done = any(record.get("refund") for record in records)

    return {"final_done": bool(final_done), "refund_done": bool(refund_done)}
