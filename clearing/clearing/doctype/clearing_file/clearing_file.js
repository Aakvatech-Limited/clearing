// Copyright (c) 2024, Nelson Mpanju and contributors
// For license information, please see license.txt

frappe.ui.form.on('Clearing File', {
    refresh: function(frm) {
        // Function to handle the creation or redirection of documents
        function handle_clearance_creation(doctype, label, filters, new_doc_data, success_message) {
            if (!frm.custom_buttons[`Create ${label}`]) {
                frm.add_custom_button(__(`Create ${label}`), function() {

                    frappe.call({
                        method: "frappe.client.get_list",
                        args: {
                            doctype: doctype,
                            filters: filters,
                            limit: 1
                        },
                        callback: function(r) {
                            if (r.message && r.message.length > 0) {
                                // If the document exists, redirect to the existing document
                                frappe.msgprint(__(`${label} already exists.`));
                                frappe.set_route('Form', doctype, r.message[0].name);
                            } else {
                                // If the document doesn't exist, create a new one
                                frappe.call({
                                    method: "frappe.client.insert",
                                    args: {
                                        doc: new_doc_data
                                    },
                                    callback: function(r) {
                                        if (!r.exc) {
                                            frappe.msgprint(__(`${success_message}`));
                                            frappe.set_route('Form', doctype, r.message.name);
                                        }
                                    }
                                });
                            }
                        }
                    });
                }, 'Create');
            }
        }

        // Create or redirect for TRA Clearance
        handle_clearance_creation(
            'TRA Clearance', 
            'TRA Clearance', 
            { clearing_file: frm.doc.name }, 
            { doctype: 'TRA Clearance', clearing_file: frm.doc.name, customer: frm.doc.customer, status: 'Payment Pending' },
            'TRA Clearance created successfully'
        );

        // Create or redirect for Shipment Clearance
        handle_clearance_creation(
            'Shipment Clearance', 
            'Shipment Clearance', 
            { clearing_file: frm.doc.name }, 
            { doctype: 'Shipment Clearance', clearing_file: frm.doc.name, customer: frm.doc.customer, status: 'Unpaid' },
            'Shipment Clearance created successfully'
        );

        // Create or redirect for Physical Verification
        handle_clearance_creation(
            'Physical Verification', 
            'Physical Verification', 
            { clearing_file: frm.doc.name }, 
            { doctype: 'Physical Verification', clearing_file: frm.doc.name, customer: frm.doc.customer, status: 'Pending' },
            'Physical Verification created successfully'
        );

        // Create or redirect for Port Clearance
        handle_clearance_creation(
            'Port Clearance', 
            'Port Clearance', 
            { clearing_file: frm.doc.name }, 
            { doctype: 'Port Clearance', clearing_file: frm.doc.name, customer: frm.doc.customer, status: 'Pending' },
            'Port Clearance created successfully'
        );
    },

    customer: function(frm) {
        if (frm.doc.customer) {
            frappe.call({
                method: "clearing.clearing.doctype.clearing_file.clearing_file.get_address_display_from_link",
                args: {
                    doctype: "Customer",
                    name: frm.doc.customer
                },
                callback: function(r) {
                    if (r.message) {
                        frm.set_value('address_display', r.message.address_display);
                        frm.set_value('customer_address', r.message.customer_address);
                    } else {
                        frm.set_value('address_display', '');
                        frm.set_value('customer_address', '');
                    }
                }
            });
        } else {
            frm.set_value('address_display', '');
            frm.set_value('customer_address', '');
        }
    },

    // Function to update cargo_description field on the parent doctype
    update_cargo_description: function(frm) {
        let descriptions = frm.doc.cargo_details.map(function(row) {
            return row.cargo_description;
        }).filter(Boolean); // Filters out empty descriptions

        frm.set_value('cargo_description', descriptions.join('\n'));
    },

    after_save: function(frm) {
        frm.trigger('update_cargo_description');
    }
});

frappe.ui.form.on('Cargo Details', {
    cargo_description: function(frm) {
        frm.trigger('update_cargo_description');
    }
});

frappe.ui.form.on('Cargo', {
    package_type: function(frm, cdt, cdn) {
        var row = locals[cdt][cdn];
        var container_number_df = frappe.meta.get_docfield('Cargo', 'container_number', frm.doc.name);
        var seal_number_df = frappe.meta.get_docfield('Cargo', 'seal_number', frm.doc.name);

        if (row.package_type === 'Loose') {
            frappe.model.set_value(cdt, cdn, 'container_number', '');
            frappe.model.set_value(cdt, cdn, 'seal_number', '');
            container_number_df.hidden = 1;
            seal_number_df.hidden = 1;
        } else {
            container_number_df.hidden = 0;
            seal_number_df.hidden = 0;
        }

        frm.fields_dict.cargo_details.grid.toggle_display('container_number', !container_number_df.hidden);
        frm.fields_dict.cargo_details.grid.toggle_display('seal_number', !seal_number_df.hidden);
        frm.fields_dict.cargo_details.grid.refresh();
    }
});
