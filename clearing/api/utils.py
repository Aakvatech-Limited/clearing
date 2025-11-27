import frappe
from frappe import _
from frappe.utils import flt
from typing import List, Optional, Sequence, Tuple


def get_expense_account(doctype: str, company: Optional[str], currency: Optional[str] = None) -> str:
    """
    Deprecated: previously mapped clearance types to accounts via asset_group_account.
    Now falls back to the configured single receivable account (or Company's default).
    """
    acc = get_clearing_receivable_account(company, currency=currency)
    if not acc and company:
        acc = frappe.db.get_value(
            "Company",
            company,
            "default_receivable_account",
            cache=True,
        )
    if not acc:
        acc = frappe.db.get_value(
            "Account",
            {"account_type": "Receivable", "is_group": 0, **({"company": company} if company else {})},
            "name",
        )
    if not acc:
        frappe.throw(_(f"Please set a Clearing Receivable Account or a default Receivable account for company {company}"))
    return acc


def get_receivable_account(customer, company):
    """
    Get the receivable account for the customer.
    
    Args:
        customer: Customer name
        company: Company name
        
    Returns:
        Account name
    """
    # Get customer's default receivable account from Party Account
    receivable_account = frappe.db.get_value(
        "Party Account",
        {
            "parenttype": "Customer",
            "parent": customer,
            "company": company
        },
        "account"
    )
    
    if not receivable_account:
        # Get company's default receivable account
        receivable_account = frappe.db.get_value("Company", company, "default_receivable_account")
    
    if not receivable_account:
        # Find any receivable account for the company
        receivable_account = frappe.db.get_value(
            "Account",
            {
                "company": company,
                "account_type": "Receivable",
                "is_group": 0
            },
            "name"
        )
    
    if not receivable_account:
        frappe.throw(
            _("Please configure a Receivable Account for customer {0} or company {1}").format(customer, company)
        )
    
    return receivable_account


def get_clearing_receivable_account(company: Optional[str], currency: Optional[str] = None) -> Optional[str]:
    """
    Return a Receivable account configured in Clearing Settings.
    - When multiple accounts are configured, prefer one matching `currency`.
    - Falls back to Company's default receivable account if not configured.
    """
    try:
        cs = frappe.get_single("Clearing Settings")
    except Exception:
        cs = None

    leaves: List[str] = []

    # Handle Table MultiSelect rows
    if cs and getattr(cs, "clearing_receivable_account", None):
        for row in cs.get("clearing_receivable_account") or []:
            acc_name = getattr(row, "account", None)
            if not acc_name:
                continue
            is_group = frappe.db.get_value("Account", acc_name, "is_group")
            if is_group == 0:
                leaves.append(acc_name)
            else:
                leaves.extend(
                    _get_descendant_leaf_accounts(acc_name, company=company, root_type="Asset")
                )

    # Deduplicate preserving order
    seen = set()
    leaves = [x for x in leaves if not (x in seen or seen.add(x))]

    # Prefer matching currency
    if currency and leaves:
        for acc in leaves:
            acc_currency = frappe.db.get_value("Account", acc, "account_currency")
            if acc_currency == currency:
                return acc

    if leaves:
        return leaves[0]

    # Fallback to Company's default receivable
    if company:
        fallback = frappe.db.get_value("Company", company, "default_receivable_account")
        if fallback:
            if not currency or frappe.db.get_value("Account", fallback, "account_currency") == currency:
                return fallback

    # Absolute fallback: any Receivable leaf
    acc = frappe.db.get_value(
        "Account",
        {
            "account_type": "Receivable",
            "is_group": 0,
            **({"company": company} if company else {}),
        },
        "name",
    )
    return acc


def get_cash_or_bank_account(company: Optional[str]) -> str:
    """
    Resolve the Cash/Bank GL account from Clearing Settings.

    Supports both of these configurations:
    - Table MultiSelect rows that point to an Account which can be either a group or a leaf.
      • If a group is selected, the first descendant leaf is used.
      • If a leaf (is_group=0) is selected, that account is used directly.
    - Future-proof: if the field is converted to a single Link to Account, use it as-is.

    Falls back to any leaf Account with account_type in (Cash, Bank) for the given company.
    """
    try:
        cs = frappe.get_single("Clearing Settings")
    except Exception:
        cs = None

    leaves: List[str] = []

    # 1) Handle a single Link value (in case the doctype gets changed)
    direct_value = None
    if cs is not None:
        try:
            # When fieldtype is Link, attribute will be a string (account name)
            if isinstance(cs.cash_or_bank_group_account, str) and cs.cash_or_bank_group_account:
                direct_value = cs.cash_or_bank_group_account
        except Exception:
            pass

    if direct_value:
        # Verify it is a leaf; if group, pick a descendant leaf
        is_group = frappe.db.get_value("Account", direct_value, "is_group")
        if not is_group:
            leaves.append(direct_value)
        else:
            leaves.extend(
                _get_descendant_leaf_accounts(direct_value, company=company, root_type="Asset")
            )

    # 2) Handle Table MultiSelect child rows
    if cs and getattr(cs, "cash_or_bank_group_account", None):
        for row in cs.get("cash_or_bank_group_account") or []:
            acc_name = getattr(row, "account_group", None)
            if not acc_name:
                continue
            is_group = frappe.db.get_value("Account", acc_name, "is_group")
            if is_group == 0:
                # A leaf account was selected explicitly; use it directly
                leaves.append(acc_name)
            else:
                # A group was selected; find leaf accounts under it
                leaves.extend(
                    _get_descendant_leaf_accounts(acc_name, company=company, root_type="Asset")
                )

    # Deduplicate leaves preserving order
    seen = set()
    leaves = [x for x in leaves if not (x in seen or seen.add(x))]

    if leaves:
        return leaves[0]

    # Fallback: any leaf cash/bank account for company
    acc = frappe.db.get_value(
        "Account",
        {
            "company": company,
            "is_group": 0,
            "account_type": ["in", ["Cash", "Bank"]],
        },
        "name",
    )
    if not acc:
        frappe.throw(
            _(
                f"Please configure a Cash/Bank account in Clearing Settings or create a Bank/Cash account for company {company}"
            )
        )
    return acc


def infer_party_from_journal_entry(je) -> Tuple[Optional[str], Optional[str]]:
    """Pick the primary party on a Journal Entry, preferring explicit party rows."""
    for row in getattr(je, "accounts", []) or []:
        party_type = row.get("party_type")
        party = row.get("party")
        if party_type and party:
            return party_type, party

    cf_name = getattr(je, "clearing_file", None)
    if cf_name:
        customer = frappe.db.get_value("Clearing File", cf_name, "customer")
        if customer:
            return "Customer", customer

    return None, None


def get_journal_entry_party_summary(je, party_type: Optional[str] = None, party: Optional[str] = None):
    """Return total, paid, outstanding amounts for the party on a Journal Entry."""
    if isinstance(je, str):
        je = frappe.get_doc("Journal Entry", je)

    if not party_type or not party:
        inferred_type, inferred_party = infer_party_from_journal_entry(je)
        party_type = party_type or inferred_type
        party = party or inferred_party

    total = 0.0
    if party_type and party:
        for row in getattr(je, "accounts", []) or []:
            if row.get("party_type") == party_type and row.get("party") == party:
                debit = flt(row.get("debit_in_account_currency") or row.get("debit") or 0)
                credit = flt(row.get("credit_in_account_currency") or row.get("credit") or 0)
                net = debit - credit
                if net:
                    total += net
    total = abs(total)

    paid = frappe.db.sql(
        """
        select sum(ref.allocated_amount)
        from `tabPayment Entry Reference` ref
        join `tabPayment Entry` pe on pe.name = ref.parent
        where pe.docstatus = 1
          and ref.reference_doctype = 'Journal Entry'
          and ref.reference_name = %s
        """,
        (je.name,),
    )[0][0] or 0.0

    outstanding = max(total - flt(paid), 0.0)

    return frappe._dict(
        total=flt(total),
        paid=flt(paid),
        outstanding=flt(outstanding),
        party_type=party_type,
        party=party,
    )


def _get_descendant_leaf_accounts(group_account_name: str, company: Optional[str] = None, root_type: Optional[str] = None) -> List[str]:
    """Return all non-group Account names under a given group using nested set (lft/rgt)."""
    grp = frappe.db.get_value(
        "Account",
        {"name": group_account_name},
        ["lft", "rgt", "company", "root_type"],
        as_dict=True,
    )
    if not grp:
        return []

    filters = {
        "lft": (">", grp["lft"]),
        "rgt": ("<", grp["rgt"]),
        "is_group": 0,
    }
    # Respect company if provided, else prefer group's company (when present)
    eff_company = company or grp.get("company")
    if eff_company:
        filters["company"] = eff_company

    if root_type:
        filters["root_type"] = root_type

    # when using pluck, Frappe returns a list of strings
    return frappe.get_all("Account", filters=filters, pluck="name")
