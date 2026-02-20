from typing import Dict, Iterable, List, Optional

import frappe
from frappe.utils import cstr, flt

from erpnext.setup.utils import get_exchange_rate


def _get_latest_currency_exchange(
    from_currency: str, to_currency: str, posting_date: Optional[str]
) -> Optional[Dict[str, object]]:
    filters = {
        "from_currency": from_currency,
        "to_currency": to_currency,
    }
    if posting_date:
        filters["date"] = ["<=", posting_date]

    row = frappe.get_all(
        "Currency Exchange",
        filters=filters,
        fields=["exchange_rate", "date"],
        order_by="date desc",
        limit=1,
    )
    return row[0] if row else None


def _resolve_invoice_totals_in_party_currency(invoice: Dict[str, object]) -> float:
    party_currency = cstr(invoice.get("party_account_currency") or "").strip()
    company_currency = cstr(invoice.get("company_currency") or "").strip()

    if party_currency and company_currency and party_currency == company_currency:
        return flt(
            invoice.get("base_rounded_total")
            or invoice.get("base_grand_total")
            or invoice.get("rounded_total")
            or invoice.get("grand_total")
            or 0
        )

    return flt(invoice.get("rounded_total") or invoice.get("grand_total") or 0)


def _resolve_exchange_rate(
    from_currency: str, to_currency: str, posting_date: Optional[str]
) -> float:
    from_currency = cstr(from_currency).strip()
    to_currency = cstr(to_currency).strip()
    if not from_currency or not to_currency:
        return 1.0
    if from_currency == to_currency:
        return 1.0

    direct = _get_latest_currency_exchange(from_currency, to_currency, posting_date)
    inverse = _get_latest_currency_exchange(to_currency, from_currency, posting_date)

    direct_rate = flt((direct or {}).get("exchange_rate") or 0)
    inverse_rate = flt((inverse or {}).get("exchange_rate") or 0)
    inverse_based_rate = (1 / inverse_rate) if inverse_rate > 0 else 0

    if direct_rate > 0:
        return direct_rate
    if inverse_based_rate > 0:
        return inverse_based_rate

    exchange_rate = flt(get_exchange_rate(from_currency, to_currency, posting_date))
    if exchange_rate <= 0:
        frappe.log_error(
            title="Missing Currency Exchange Rate for Clearing",
            message=(
                f"Unable to resolve exchange rate from {from_currency} to {to_currency}"
                f" for date {posting_date or 'N/A'}."
            ),
        )
        return 0.0

    return exchange_rate


def resolve_exchange_rate(
    from_currency: str, to_currency: str, posting_date: Optional[str] = None
) -> float:
    """Resolve exchange rate for any currency pair using direct, inverse, then ERPNext fallback."""
    return _resolve_exchange_rate(from_currency, to_currency, posting_date)


def build_invoice_currency_snapshot(
    invoice_name: str, *, target_currency: Optional[str] = None
) -> Optional[Dict[str, object]]:
    invoice_name = cstr(invoice_name).strip()
    if not invoice_name:
        return None

    invoice = frappe.db.get_value(
        "Sales Invoice",
        invoice_name,
        [
            "name",
            "status",
            "docstatus",
            "posting_date",
            "due_date",
            "company",
            "currency",
            "party_account_currency",
            "rounded_total",
            "grand_total",
            "base_rounded_total",
            "base_grand_total",
            "outstanding_amount",
        ],
        as_dict=True,
    )
    if not invoice:
        return None

    if not invoice.get("company_currency") and invoice.get("company"):
        invoice["company_currency"] = frappe.get_cached_value(
            "Company", invoice.get("company"), "default_currency"
        )

    party_account_currency = cstr(
        invoice.get("party_account_currency") or invoice.get("currency") or ""
    ).strip()
    invoice_currency = cstr(invoice.get("currency") or party_account_currency).strip()
    target_currency = cstr(target_currency or party_account_currency or invoice_currency).strip()

    party_grand_total = _resolve_invoice_totals_in_party_currency(invoice)
    party_outstanding = flt(invoice.get("outstanding_amount") or 0)

    exchange_rate = _resolve_exchange_rate(
        party_account_currency, target_currency, invoice.get("posting_date")
    )
    target_grand_total = flt(party_grand_total * exchange_rate)
    target_outstanding = flt(party_outstanding * exchange_rate)

    return {
        "name": invoice.get("name"),
        "status": invoice.get("status"),
        "docstatus": int(invoice.get("docstatus") or 0),
        "posting_date": invoice.get("posting_date"),
        "due_date": invoice.get("due_date"),
        "company": invoice.get("company"),
        "company_currency": invoice.get("company_currency"),
        "invoice_currency": invoice_currency,
        "party_account_currency": party_account_currency,
        "grand_total_in_party_currency": party_grand_total,
        "outstanding_amount_in_party_currency": party_outstanding,
        "target_currency": target_currency,
        "exchange_rate_to_target": exchange_rate,
        "grand_total_in_target_currency": target_grand_total,
        "outstanding_amount_in_target_currency": target_outstanding,
    }


def build_invoice_currency_snapshots(
    invoice_names: Iterable[str], *, target_currency: Optional[str] = None
) -> List[Dict[str, object]]:
    snapshots: List[Dict[str, object]] = []
    seen = set()

    for raw_name in invoice_names or []:
        invoice_name = cstr(raw_name).strip()
        if not invoice_name or invoice_name in seen:
            continue
        seen.add(invoice_name)

        snapshot = build_invoice_currency_snapshot(
            invoice_name, target_currency=target_currency
        )
        if not snapshot:
            continue
        snapshots.append(snapshot)

    return snapshots
