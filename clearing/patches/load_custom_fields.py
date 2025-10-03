"""Patch to create custom fields from JSON definition."""

import json
import os

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

CUSTOM_FIELDS_FILE = "./custom_fields/custom_fields.json"
DISALLOWED_KEYS = {
    "name",
    "owner",
    "creation",
    "modified",
    "modified_by",
    "docstatus",
    "idx",
    "is_system_generated",
    "__last_sync_on",
}


def _load_custom_fields() -> list[dict]:
    base_path = os.path.abspath(os.path.dirname(__file__))
    file_path = os.path.join(base_path, CUSTOM_FIELDS_FILE)

    if not os.path.exists(file_path):
        return []

    with open(file_path, "r") as handle:
        return json.load(handle)


def _group_by_doctype(custom_fields: list[dict]) -> dict[str, list[dict]]:
    valid_columns = frappe.get_meta("Custom Field").get_valid_columns()
    allowed_columns = set(valid_columns).difference(DISALLOWED_KEYS)
    grouped: dict[str, list[dict]] = {}

    for field in custom_fields:
        if not isinstance(field, dict):
            continue

        doctype = field.get("dt")
        if not doctype:
            continue

        prepared_field = {
            key: field.get(key)
            for key in allowed_columns
            if field.get(key) is not None
        }

        if not prepared_field:
            continue

        grouped.setdefault(doctype, []).append(prepared_field)

    return grouped


def execute() -> None:
    try:
        custom_fields = _load_custom_fields()
        if not custom_fields:
            return

        grouped_fields = _group_by_doctype(custom_fields)
        if not grouped_fields:
            return

        create_custom_fields(grouped_fields, update=False)
    except Exception:
        frappe.log_error(
            title="Clearing: Failed to load custom fields",
            message=frappe.get_traceback(),
        )

