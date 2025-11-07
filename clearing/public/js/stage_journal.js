frappe.provide("clearing.stageJournal");

if (!clearing.stageJournal.handle) {
  const helpers = {
    getCandidates(frm, tableField) {
      const defaultCurrency =
        (frappe.sys_defaults && frappe.sys_defaults.currency) || undefined;

      return (frm.doc[tableField] || [])
        .filter((row) => row && row.name && !row.journal_entry)
        .filter((row) => flt(row.amount || 0) > 0)
        .map((row, index) => {
          const amount = flt(row.amount || 0);
          const currency = row.currency || frm.doc.currency || defaultCurrency;
          const label = `${row.item || __("Charge")} | ${format_currency(
            amount,
            currency
          )}`;
          return {
            key: row.name || `${tableField}-${index + 1}`,
            rowName: row.name,
            label,
          };
        });
    },

    openDialog(frm, candidates, serverMethod) {
      const valueMap = {};
      const options = candidates.map((entry) => {
        valueMap[entry.key] = entry.rowName;
        return {
          label: entry.label,
          value: entry.key,
          checked: true,
        };
      });

      const dialog = new frappe.ui.Dialog({
        title: __("Create Journal Entries"),
        fields: [
          {
            fieldname: "charges",
            label: __("Charges"),
            fieldtype: "MultiCheck",
            options,
            reqd: 1,
            columns: "20rem",
          },
          {
            fieldname: "posting_date",
            label: __("Posting Date"),
            fieldtype: "Date",
            default:
              frappe.datetime && typeof frappe.datetime.nowdate === "function"
                ? frappe.datetime.nowdate()
                : undefined,
          },
        ],
        primary_action_label: __("Create"),
        async primary_action(values) {
          const selected = (values.charges || []).filter(Boolean);
          if (!selected.length) {
            frappe.msgprint(__("Select at least one charge."));
            return;
          }

          const names = selected
            .map((value) => valueMap[value])
            .filter((name) => !!name);
          if (!names.length) {
            frappe.msgprint(
              __("Unable to locate the selected charges. Please try again.")
            );
            return;
          }

          dialog.hide();

          try {
            const response = await frappe.call({
              method: serverMethod,
              args: {
                name: frm.doc.name,
                charges: names,
                posting_date: values.posting_date,
              },
              freeze: true,
              freeze_message: __("Creating Journal Entries..."),
            });

            const created = response.message || [];
            if (created.length) {
              const createdNames = created
                .map((item) => item.journal_entry)
                .join(", ");
              frappe.msgprint(
                __("Created Journal Entry {0}.", [createdNames]),
                __("Success")
              );
            } else {
              frappe.msgprint(__("No Journal Entries were created."));
            }
            await frm.reload_doc();
          } catch (error) {
            console.error("Failed to create journal entries", error);
            frappe.msgprint(
              __("Unable to create Journal Entries. Please try again.")
            );
          }
        },
      });

      dialog.show();
    },
  };

  clearing.stageJournal.handle = async function (frm, config) {
    if (!config || !config.tableField || !config.serverMethod) {
      return;
    }

    if (frm.is_new()) {
      frappe.msgprint(__("Please save the document first."));
      return;
    }

    if (!frm.doc.clearing_file) {
      frappe.msgprint(
        __("Please set a Clearing File before creating Journal Entries.")
      );
      return;
    }

    const candidates = helpers.getCandidates(frm, config.tableField);
    if (!candidates.length) {
      frappe.msgprint(
        __("All charges already have a Journal Entry or have zero amount.")
      );
      return;
    }

    helpers.openDialog(frm, candidates, config.serverMethod);
  };
}
