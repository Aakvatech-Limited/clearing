import frappe
import json
import os


def import_clearing_document_types():
    """
    Patch to import Clearing Document Type records and their nested attributes
    from `fixtures/clearing_document_type.json` into the site.
    """
    # Locate the fixtures JSON file
    app_path = os.path.dirname(__file__)
    fixtures_file = os.path.join(app_path, '..', 'fixtures', 'clearing_document_type.json')

    if not os.path.exists(fixtures_file):
        frappe.throw(f"Fixtures file not found: {fixtures_file}")

    with open(fixtures_file, 'r', encoding='utf-8') as f:
        entries = json.load(f)

    for entry in entries:
        # Use the JSON 'name' or fallback to 'document_type'
        name = entry.get('name') or entry['document_type']

        if frappe.db.exists('Clearing Document Type', name):
            doc = frappe.get_doc('Clearing Document Type', name)
            # Update linked_document if provided
            doc.linked_document = entry.get('linked_document')
            # Clear existing attributes
            doc.set('clearing_document_attribute', [])
        else:
            doc = frappe.new_doc('Clearing Document Type')
            doc.name = name
            doc.document_type = entry['document_type']
            doc.linked_document = entry.get('linked_document')

        # Append each attribute row
        for attr in entry.get('clearing_document_attribute', []):
            doc.append('clearing_document_attribute', {
                'document_attribute': attr['document_attribute']
            })

        # Save the document
        doc.flags.ignore_mandatory = True
        doc.save(ignore_permissions=True)
