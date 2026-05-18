# Clearing

## Business Summary

Clearing is a Frappe/ERPNext app for managing clearing and forwarding operations from the first shipment file through clearance stages, charge tracking, accounting entries, and delivery documentation.

The app is designed around a central **Clearing File**. Each file can track the consignee/customer, shipment type, mode of transport, cargo details, required documents, TRA clearance, shipping line clearance, physical verification, port clearance, charges, reimbursements, and delivery notes.

Because the code imports ERPNext utilities and works directly with ERPNext accounting records such as `Sales Invoice`, `Payment Entry`, `Journal Entry`, `Customer`, `Item`, `Company`, and `Account`, this app should be treated as **ERPNext-required** for practical use.

## Business Problems This App Solves

| Problem | How the app helps |
|---|---|
| Clearing files are tracked across spreadsheets, emails, and paper folders | Centralizes clearing file data, cargo details, documents, stage status, and delivery records |
| Required shipment documents vary by clearance type and transport mode | Provides configurable document types and child tables for required clearance documents |
| Clearance costs are difficult to reconcile with customer invoices and reimbursements | Tracks clearance, TRA, port, shipping, transport, and agency charges against a clearing file |
| Finance teams need accounting records connected to operations | Creates and links ERPNext Journal Entries, Sales Invoices, and Payment Entries |
| Managers lack visibility into pending, cleared, delivered, or undelivered files | Provides workspace shortcuts and script reports for clearing files and clearance stages |
| Teams need Tanzania-oriented clearance references | Includes fields and fixtures for TRA, TANCIS, TANSAD, CL plans, import declarations, payment notes, and related documents |

## Who This App Is For

| Audience | Fit |
|---|---|
| Clearing and forwarding companies | Strong fit for teams that manage import, export, or transit files |
| Logistics teams using ERPNext | Useful when shipment operations need to connect with ERPNext accounting |
| Finance teams handling consignee reimbursements | Useful for matching disbursements, invoices, payments, and outstanding amounts |
| Operations managers | Useful for monitoring clearance stages, missing documents, and delivery status |
| Tanzania-focused clearing operations | The repository includes TRA, TANCIS, TANSAD, and Tanzania document terminology |

## Who This App Is Not For

| Not a fit if... | Why |
|---|---|
| You do not use Frappe/ERPNext | The app relies on Frappe and ERPNext accounting DocTypes |
| You need a generic freight marketplace | This app is an operational ERP module, not a broker marketplace |
| You need direct customs authority integration out of the box | No external customs API integration was found in the repository |
| You only need basic document storage | The app is broader than file storage and includes accounting, reports, and clearance workflows |
| You need a finished public README with screenshots today | Screenshots and production deployment assumptions still need confirmation |

## Business Benefits

| Benefit | Business Impact |
|---|---|
| Central clearing file | Reduces scattered shipment records and gives teams one operational reference |
| Stage-based clearance tracking | Helps teams follow TRA, shipping line, physical verification, and port clearance progress |
| Required document tracking | Reduces the risk of missing documents before clearance or delivery |
| ERPNext accounting linkage | Connects operational costs to Journal Entries, Sales Invoices, and Payment Entries |
| Payment and reimbursement status | Gives finance better visibility into paid, partially paid, and outstanding amounts |
| Reporting workspace | Helps managers review file, delivery note, TRA, port, shipping line, and physical verification summaries |

## Before and After

| Before | After |
|---|---|
| Clearing files tracked manually | Clearing files recorded as Frappe DocTypes with statuses and linked records |
| Charges reviewed after the fact | Charges captured by clearance stage and summarized in Clearing Charges |
| Accounting team creates entries separately | Journal Entries, Sales Invoices, and Payment Entries can be prepared from clearing records |
| Required documents depend on manual memory | Document requirements can be configured by document type and transport mode |
| Management asks for updates case by case | Reports and workspace links provide a faster operational view |

## Typical Use Cases

| Use Case | Main Records |
|---|---|
| Open and monitor a clearing file | `Clearing File`, `Clearing Document`, `Cargo` |
| Track TRA clearance and related tax/payment documents | `TRA Clearance`, `TRA Charges`, `TRA Charges Paid`, `TRA Document` |
| Track shipping line clearance | `Shipping Line Clearance`, `Shipping Charges`, `Shipping Charges Paid`, `Shipping Line` |
| Track physical verification | `Physical Verification`, `Verification Charges`, `Physical Verification Image` |
| Track port clearance | `Port Clearance`, `Port Charges`, `Port Charges Paid`, `Port clearance Document` |
| Generate delivery documentation | `CF Delivery Note`, `Container Interchange`, `Truck Detail` |
| Manage clearing charges and accounting recovery | `Clearing Charges`, `Clearing Charge Detail`, `Consignee Disbursement`, `Consignee Reimbursement` |
| Configure document and master data | `Clearing Document Type`, `Mode of Transport`, `Package Type`, `Shipper`, `Transporter`, `Airline` |

## Example Business Workflow

1. Configure clearing document types, modes of transport, service items, and clearing account settings.
2. Create a **Clearing File** for a consignee/customer, shipment type, mode of transport, company, cargo details, and shipment references.
3. Attach or record required shipment documents such as Bill of Lading, Air Waybill, Commercial Invoice, Payment Note, Assessment Document, Authorization Letter, or C.41.
4. Create stage records for TRA Clearance, Shipping Line Clearance, Physical Verification, and Port Clearance as needed.
5. Record charges paid by the clearing agent or consignee, including TRA, port, shipping, verification, transport, and agency charges.
6. Submit clearance stages after payment/status conditions are met.
7. Generate or update ERPNext Journal Entries for clearance costs and prepare Sales Invoices or Payment Entries where required.
8. Create a CF Delivery Note and track delivery or container interchange details.
9. Review operational and financial progress through the Clearing & Forwarding workspace and script reports.

## ERPNext Value Addition

This app adds a clearing and forwarding operating layer on top of ERPNext.

| ERPNext Area | Integration Found |
|---|---|
| Customers | Clearing files, clearance stages, reports, and invoices link to `Customer` |
| Companies | Clearing files and accounting functions use `Company` |
| Items | Fixture items define service lines such as TRA Clearance, Port Clearance, Shipping Line Clearance, Physical Verification, Transport, and Clearing Agency Fee |
| Accounts | Clearing Settings stores receivable and cash/bank account groups |
| Journal Entries | Clearance submissions and disbursement flows create or link `Journal Entry` records |
| Sales Invoices | Clearing charge rows can generate draft `Sales Invoice` records |
| Payment Entries | Payment Entry helpers prepare payments against Journal Entries and Sales Invoices |
| Employees | Clearance and delivery records can link staff responsible for work |
| Addresses and Files | Workspace links include ERPNext/Frappe `Address` and `File` |

## Stand-alone Value

The app is not recommended as a standalone Frappe-only app because core logic imports ERPNext and depends on ERPNext accounting DocTypes. In a full ERPNext site, it provides stand-alone operational value as a dedicated clearing and forwarding module.

## Decision Guide

| Question | Yes / No |
|---|---|
| Do you manage import, export, transit, or port clearance files? | |
| Do you need to track required shipping and customs documents per file? | |
| Do you need TRA, TANCIS, TANSAD, or Tanzania-oriented clearance references? | |
| Do clearing teams pay charges on behalf of customers and later recover them? | |
| Do you need clearing charges connected to ERPNext invoices, payments, and journal entries? | |
| Do managers need file, delivery, and clearance-stage reports? | |

If most answers are "Yes", this app is likely worth evaluating in an ERPNext test site.

## Expected Business Outcomes

| Outcome | Conservative Expectation |
|---|---|
| Better file visibility | Can help teams see where each clearing file sits in the process |
| Better charge traceability | Can help finance trace costs from clearance stage to accounting document |
| Better document readiness | Can help reduce missing-document follow-ups before clearance or delivery |
| Better management reporting | Can help managers review operational summaries without manually compiling spreadsheets |
| Better ERPNext fit for clearing companies | Extends ERPNext into a more industry-specific workflow |

## Screenshots / Visual Walkthrough

Screenshots are not included in this repository.

Suggested screenshots before publishing:

| Screenshot | Purpose |
|---|---|
| Clearing & Forwarding workspace | Show navigation and primary modules |
| Clearing File form | Show central file tracking |
| Clearing Charges form | Show charge, invoice, payment, and reimbursement tracking |
| TRA Clearance / Port Clearance forms | Show stage-specific workflow |
| Summary reports | Show management visibility |

## Demo Scenario

1. Create a Customer and Company in ERPNext.
2. Configure Clearing Settings with receivable and cash/bank account groups.
3. Create or verify service Items from fixtures.
4. Create a Clearing File for an import shipment with cargo details and a mode of transport.
5. Attach required clearing documents.
6. Create TRA, Shipping Line, Physical Verification, and Port Clearance records.
7. Mark applicable charges and complete payment status.
8. Generate Journal Entries, Sales Invoices, and Payment Entries from the clearing records.
9. Create a CF Delivery Note and review the summary reports.

## Implementation Effort

| Area | Effort | Notes |
|---|---|---|
| Basic app installation | Medium | Requires a working Frappe/ERPNext bench and site |
| Master data setup | Medium | Customers, companies, accounts, items, document types, shipping lines, airlines, transporters, and modes of transport should be ready |
| Accounting configuration | High | Clearing Settings and account groups must match the company's chart of accounts |
| Workflow fitment | Medium | Clearance statuses and required documents should be confirmed with the operating team |
| Data migration | Depends | Existing clearing files and document registers may need mapping |
| Training | Medium | Operations and finance users both need process training |
| Reporting changes | Depends | Existing reports may need client-specific columns or filters |

## What Needs to Be Ready Before Implementation

| Requirement | Why It Matters |
|---|---|
| ERPNext site | Core app logic uses ERPNext accounting and master data |
| Company and chart of accounts | Journal Entries, Payment Entries, and account selection depend on it |
| Customer/consignee records | Clearing files and invoices link to customers |
| Service items | Charges use ERPNext Items such as TRA Clearance and Port Clearance |
| Clearing Settings | Receivable and cash/bank account groups are required for accounting flows |
| Document type list | Required clearance documents depend on configured document types |
| Role assignments | Users need appropriate Clearing Agent, TRA Clearing Agent, Accounts, or System Manager roles |
| Agreed business process | Submission and payment rules should match operations |

## Risks and Considerations

| Risk | Consideration |
|---|---|
| Accounting configuration errors | Incorrect receivable or bank account setup can block Journal Entry or Payment Entry creation |
| Missing required documents | Clearance records validate required document attachments in some flows |
| ERPNext dependency | The app is not suitable for a Frappe-only deployment without code changes |
| Custom field lifecycle | The app adds fields to ERPNext DocTypes; confirm cleanup requirements before uninstalling |
| Missing referenced hook files | `hooks.py` references `clearing.clearing.utils` and `clearing/journal_entry.js`, but those files were not found in this repository snapshot |
| Publishing readiness | Screenshots, repository URL, exact supported ERPNext version, and production deployment notes need confirmation |

## Frequently Asked Business Questions

### Do we need ERPNext?

Yes. The app should be treated as ERPNext-required because it uses ERPNext accounting and master-data records.

### Will this replace ERPNext?

No. It extends ERPNext with clearing and forwarding operations. ERPNext remains the accounting and master-data foundation.

### Can managers get reports?

Yes. The repository includes script reports for Clearing File, TRA Clearance, Port Clearance, Shipping Line Clearance, Physical Verification, and CF Delivery Note summaries.

### Can this be customized?

Yes. It is a Frappe app with DocTypes, hooks, client scripts, reports, fixtures, and Python APIs that can be customized by a Frappe/ERPNext developer.

### Can existing spreadsheet data be migrated?

Likely, but the repository does not include a migration script for existing spreadsheets. Migration mapping should be confirmed per client.

### What should we prepare before implementation?

Prepare master data, chart of accounts, service items, document requirements, roles, and an agreed clearing process.

---

## Key Features

| Feature | Evidence |
|---|---|
| Central clearing file | `Clearing File` DocType with customer, company, transport mode, cargo, document, status, TRA/TANCIS/TANSAD, and delivery fields |
| Clearance stage tracking | `TRA Clearance`, `Shipping Line Clearance`, `Physical Verification`, and `Port Clearance` DocTypes |
| Charge capture | Stage charge tables plus `Clearing Charges` and `Clearing Charge Detail` |
| Accounting document generation | API modules create or prepare Journal Entries, Sales Invoices, and Payment Entries |
| Required document configuration | `Clearing Document Type`, `Mode of Transport`, and document child tables |
| Delivery note support | `CF Delivery Note`, print format, and delivery note summary report |
| Workspace navigation | `Clearing & Forwarding` workspace |
| Reporting | Six script reports under `clearing/clearing/report` |
| Fixtures and custom fields | Fixture loaders and custom fields run after install and migrate |

## Compatibility

| Component | Evidence / Status |
|---|---|
| Frappe | Frappe app structure; dependency is managed by bench |
| ERPNext | Required in practice; code imports `erpnext` and uses ERPNext DocTypes |
| ERPNext branch | `version-15` appears in `.releaserc.json` |
| Python | `>=3.10` in `pyproject.toml` |
| App version | `0.0.1` in `clearing/__init__.py` |
| Package name | `clearing` |
| License | MIT |

To confirm: exact supported Frappe/ERPNext versions, production branch, and repository URL.

## App Mode

**ERPNext required.**

Although `pyproject.toml` leaves dependencies to bench, the application imports ERPNext modules and creates or links ERPNext accounting records. Install and test it on an ERPNext site, not a Frappe-only site.

## Installation

Replace `<repo-url>` with the actual repository URL.

```bash
bench get-app clearing <repo-url> --branch version-15
bench --site your-site.local install-app clearing
bench --site your-site.local migrate
bench --site your-site.local clear-cache
```

If installing from a local folder during development:

```bash
bench get-app /path/to/clearing
bench --site your-site.local install-app clearing
bench --site your-site.local migrate
```

## Configuration

1. Install ERPNext and confirm the target company is configured.
2. Confirm customers/consignees, addresses, employees, accounts, and service items are available.
3. Open **Clearing Settings**.
4. Configure:
   - Cash or bank account group
   - Clearing receivable account group
5. Review fixture-loaded service items:
   - TRA Clearance
   - Port Clearance
   - Shipping Line Clearance
   - Physical Verification
   - Transport
   - Clearing Agency Fee
6. Review clearing document types and mode-of-transport document requirements.
7. Assign roles to users.

## Usage

| Step | Action |
|---|---|
| 1 | Create or update master data such as Shipping Line, Shipper, Transporter, Airline, Package Type, and Container Location |
| 2 | Create a Clearing File and set consignee, company, shipment type, transport mode, cargo, and references |
| 3 | Add required Clearing Documents |
| 4 | Create clearance stage records as needed |
| 5 | Capture charges paid by clearing agent or consignee |
| 6 | Submit clearance stages when payment and document requirements are satisfied |
| 7 | Generate Journal Entries, Sales Invoices, and Payment Entries |
| 8 | Generate CF Delivery Note and complete delivery tracking |
| 9 | Review reports and outstanding amounts |

## Modules and DocTypes

| Category | DocTypes |
|---|---|
| Main operations | `Clearing File`, `Clearing Document`, `Clearing Charges`, `CF Delivery Note` |
| Clearance stages | `TRA Clearance`, `Shipping Line Clearance`, `Physical Verification`, `Port Clearance` |
| Charge tables | `TRA Charges`, `TRA Charges Paid`, `Shipping Charges`, `Shipping Charges Paid`, `Verification Charges`, `Verification Charges Paid`, `Port Charges`, `Port Charges Paid`, `Clearing Charge Detail` |
| Finance helpers | `Clearing Settings`, `Clearing Asset Account Group`, `Clearing Receivable Account Group`, `Clearing Services`, `Consignee Disbursement`, `Consignee Reimbursement` |
| Document setup | `Clearing Document Type`, `Clearing Document Type Attribute`, `Clearing Document Attribute`, `Clearing File Document`, `TRA Document`, `Ship clearance Document`, `Physical Verification Document`, `Port clearance Document`, `Document Attachments` |
| Logistics master data | `Shipping Line`, `Shipper`, `Transporter`, `Transporter Truck Detail`, `Truck Detail`, `Airline`, `Airplane`, `Package Type`, `Container Location`, `Mode of Transport`, `Mode of Transport Detail` |
| Cargo and verification | `Cargo`, `Physical Verification Image`, `Container Interchange` |
| Risk | `Risk`, `Risk Assessment`, `Reason for Risk Attribute` |

## ERPNext Integration Details

| ERPNext DocType / Area | Integration |
|---|---|
| `Customer` | Used as consignee/customer in clearing files, clearance stages, reports, and accounting flows |
| `Company` | Used for company-specific accounts and currency |
| `Account` | Used for receivable, cash/bank, party, and payment accounts |
| `Item` | Used as service charge types |
| `Sales Invoice` | Custom field links invoices to Clearing Charges; API creates invoice drafts |
| `Journal Entry` | Clearance submissions and charge disbursements create or update Journal Entries |
| `Payment Entry` | API prepares payment entries from Journal Entries and Sales Invoices |
| `Employee` | Used for responsible staff on clearance and delivery records |
| `Address` | Used for consignee address data |
| `Currency` | Used throughout charge and payment records |

## Custom Fields and Fixtures

| Area | Evidence |
|---|---|
| Sales Invoice custom field | `clearing/patches/custom_fields/custom_fields.json` adds `clearing_charges` link to `Sales Invoice` |
| Journal Entry custom field | `clearing/patches/add_clearing_file_to_journal_entry.py` adds `clearing_file` to `Journal Entry` |
| Obsolete field cleanup | `clearing/patches/remove_party_accounts_from_journal_entry.py` removes older Journal Entry party account structures |
| Document type fixtures | `clearing/patches/fixtures_json/clearing_document_type.json` loads clearance document types and attributes |
| Service item fixtures | `clearing/patches/fixtures_json/item.json` loads service Items |
| Install/migrate fixture loading | `hooks.py` runs fixture and custom-field loaders after install and after migrate |

## Permissions

| Role | Evidence |
|---|---|
| System Manager | Broad access across main DocTypes and reports |
| Clearing Agent | Access on Clearing File, TRA Clearance, and Shipping Line Clearance |
| TRA Clearing Agent | Access on Clearing File, TRA Clearance, and Shipping Line Clearance |
| Accounts Manager | Access to Clearing Settings |
| Accounts User | Access to Clearing File Summary report |

Permissions should be reviewed against each organization's operating model before production rollout.

## Reports and Dashboards

| Report / Workspace | Type | Purpose |
|---|---|---|
| Clearing & Forwarding | Workspace | Main module navigation |
| Clearing File Summary | Script Report | Summary of clearing files |
| TRA Clearance Summary | Script Report | TRA clearance status and values |
| Port Clearance Summary | Script Report | Port clearance status and values |
| Shipping Line Clearance Summary | Script Report | Shipping line clearance status and values |
| Physical Verification Summary | Script Report | Physical verification status and values |
| CF Delivery Note Summary | Script Report | Delivery note tracking |

## APIs

Whitelisted methods and important API helpers include:

| Module | Methods |
|---|---|
| `clearing.api.sales_invoice` | `make_sales_invoice_draft` |
| `clearing.api.payment_entry` | `make_payment_entry_from_references`, `make_payment_entry_from_journal_entries` |
| `clearing.api.journal_entry` | `make_payment_entry_from_journal_entry`, `make_payment_entry_from_journal_entries` |
| `clearing.clearing.doctype.clearing_charges.clearing_charges` | `get_disbursement_journal_entries`, `get_reimbursement_payments_for_journal_entries`, `get_sales_invoice_currency_snapshots`, `make_disbursement_journal_entries`, `compute_clearing_charges_status`, `sync_clearing_charges_status`, `make_payment_entry_for_clearing_file` |
| Clearance stage DocTypes | `make_journal_entries` helpers for TRA, shipping line, physical verification, and port clearance |
| `clearing.clearing.doctype.clearing_file.clearing_file` | Address display, status update, and container interchange helpers |

## Hooks and Events

| Hook | Behavior |
|---|---|
| `after_install` | Loads fixtures and custom fields |
| `after_migrate` | Reloads fixtures and custom fields |
| `doctype_js` | Adds custom client scripts for `Journal Entry` and `Payment Entry` |
| `doc_events` on clearance stages | On submit, updates Clearing File status and creates/updates Journal Entry; on cancel, cancels linked Journal Entry |
| `doc_events` on `Sales Invoice` | Syncs Clearing Charges status on submit, cancel, update after submit, and update |
| `doc_events` on `Payment Entry` | Clamps references and syncs payment status on validate/submit/cancel/update |

## Background Jobs

No active `scheduler_events` were found in `hooks.py`.

## Developer Setup

```bash
bench get-app clearing <repo-url> --branch version-15
bench --site your-site.local install-app clearing
bench --site your-site.local migrate
```

Useful checks:

```bash
bench --site your-site.local run-tests --app clearing
bench --site your-site.local console
bench --site your-site.local clear-cache
```

## Project Structure

```text
clearing/
  api/                         ERPNext accounting and payment helpers
  clearing/doctype/            Frappe DocTypes for clearing operations
  clearing/report/             Script reports
  clearing/print_format/       CF Delivery Note print format
  clearing/workspace/          Clearing & Forwarding workspace
  patches/                     Custom fields, fixtures, and migrations
  public/js/                   Shared client scripts
  services/                    Currency helper service
  config/                      Frappe module config
  hooks.py                     App hooks and document events
```

## Migration Notes

| Migration Area | Notes |
|---|---|
| Fixtures | Loaded after install and after migrate |
| Custom fields | Loaded from `clearing/patches/custom_fields/custom_fields.json` |
| Journal Entry changes | Patches add `clearing_file` and remove older party-account structures |
| Existing data | No general migration script for legacy spreadsheet or external system data was found |

## Upgrade Guide

1. Backup the site database and files.
2. Pull or deploy the target app version.
3. Run:

```bash
bench --site your-site.local migrate
bench --site your-site.local clear-cache
```

4. Recheck Clearing Settings.
5. Test:
   - Clearing File submission
   - Clearance stage submission
   - Journal Entry creation
   - Sales Invoice draft creation
   - Payment Entry creation
   - Summary reports

## Uninstallation

Back up the site before uninstalling.

```bash
bench --site your-site.local uninstall-app clearing
bench --site your-site.local migrate
```

Before uninstalling, confirm whether custom fields, fixture-loaded service items, and accounting references should remain for audit purposes.

## Troubleshooting

| Symptom | Check |
|---|---|
| Journal Entry creation fails | Confirm Clearing Settings, company, customer, receivable account, and cash/bank account setup |
| Payment Entry does not reference expected documents | Confirm selected Journal Entries or Sales Invoices are submitted and outstanding |
| Sales Invoice draft fails | Confirm selected Clearing Charge rows are invoice charges with valid Item codes and positive amounts |
| Clearance record cannot be submitted | Confirm payment status, required document attachments, and stage-specific validation rules |
| Missing reports or workspace links | Run migrate, clear cache, and confirm the app is installed on the site |
| Client script not loading | Confirm referenced JS files exist and asset paths match `hooks.py` |

## Security

The repository uses standard Frappe role permissions in DocType JSON files and report roles. No external API credentials, background sync credentials, or third-party integration secrets were found in the repository.

Production deployments should review:

- Role assignments
- Account access
- Report visibility
- Write/submit permissions
- Custom script paths
- Audit requirements for clearing and finance documents

## Repository Evidence Reviewed

| File / Area | Evidence Found |
|---|---|
| `pyproject.toml` | App name `clearing`, Python `>=3.10`, bench-managed Frappe dependency |
| `clearing/hooks.py` | App metadata, install/migrate hooks, DocType JS hooks, ERPNext document events |
| `clearing/modules.txt` | Defines the `Clearing` module |
| `clearing/patches.txt` | Journal Entry migration patches |
| `clearing/patches/custom_fields/custom_fields.json` | Adds Clearing Charges link to Sales Invoice |
| `clearing/patches/fixtures_json/item.json` | Loads service Items for clearance charges |
| `clearing/patches/fixtures_json/clearing_document_type.json` | Loads clearing document types and attributes |
| `clearing/clearing/doctype/*/*.json` | Defines operational, finance, document, logistics, risk, and child-table DocTypes |
| `clearing/api/*.py` | ERPNext Sales Invoice, Payment Entry, Journal Entry, account, and currency helpers |
| `clearing/clearing/report/*` | Script reports for operational summaries |
| `clearing/clearing/workspace/clearing_&_forwarding/clearing_&_forwarding.json` | Workspace navigation and undelivered files shortcut |
| `clearing/clearing/print_format/delivery_note/delivery_note.json` | CF Delivery Note print format |
| `.releaserc.json` | Release branch appears to be `version-15` |
| `license.txt` and `hooks.py` | MIT license |

## To Confirm Before Publishing

| Item | Why |
|---|---|
| Repository URL | Needed for final installation command |
| Exact supported Frappe/ERPNext versions | `version-15` is indicated, but compatibility should be confirmed in a running bench |
| Screenshots | Needed for buyer-friendly README publishing |
| Production setup guide | Site, worker, backup, and deployment assumptions are not documented |
| Missing referenced files | `hooks.py` references `clearing.clearing.utils` and `clearing/journal_entry.js`, but those files were not found in this snapshot |
| Test status | Tests were not executed while preparing this README |
| Migration plan | No spreadsheet or legacy-data migration scripts were found |
| Business terminology | Confirm final terminology with operations users, especially TRA/TANCIS/TANSAD and document names |

## Support and Maintenance

Maintainer information found in repository metadata:

| Field | Value |
|---|---|
| Publisher | Nelson Mpanju |
| Email | nelsonnorbert87@gmail.com |
| License | MIT |

## Contributing

1. Create a branch from the supported release branch.
2. Follow Frappe/ERPNext development conventions.
3. Add or update tests for DocTypes, accounting flows, and report changes.
4. Run linting and relevant tests before submitting changes.
5. Document any new fixtures, custom fields, hooks, or migration patches.

## Versioning

The app version is currently:

```text
0.0.1
```

Release configuration references the `version-15` branch.

## License

MIT. See `license.txt`.

## Maintainers

Nelson Mpanju  
nelsonnorbert87@gmail.com
