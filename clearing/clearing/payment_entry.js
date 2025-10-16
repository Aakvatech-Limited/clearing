// Disable ERPNext's auto outstanding fetch when Payment Entry originates from Clearing

frappe.ui.form.on('Payment Entry', {
  onload(frm) {
    disable_outstanding_fetch(frm);
    setup_clearing_payment_protection(frm);
    apply_clearing_allocated_amount(frm);
  },
  refresh(frm) {
    disable_outstanding_fetch(frm);
    setup_clearing_payment_protection(frm);
    apply_clearing_allocated_amount(frm);
  },
  paid_amount(frm) {
    // Prevent auto-calculation from overriding user input for clearing payments
    if (frm.__is_clearing_payment && frm.__user_editing_amount) {
      // User is manually editing, don't let ERPNext override
      return;
    }
  },
  received_amount(frm) {
    // Prevent auto-calculation from overriding user input for clearing payments
    if (frm.__is_clearing_payment && frm.__user_editing_amount) {
      // User is manually editing, don't let ERPNext override
      return;
    }
  }
});

function parse_clearing_marker(frm) {
  const txt = (frm.doc.custom_remarks || frm.doc.remarks || '').toString();
  const match = txt.match(/\[CFJE:([^\]]+)\]/);
  return match ? match[1].trim() : null;
}

function disable_outstanding_fetch(frm) {
  if (frm.__clearing_fetch_disabled) {
    return;
  }
  const marker = parse_clearing_marker(frm);
  if (!marker) {
    return;
  }

  const noop = () => Promise.resolve([]);
  const eventNames = [
    'get_outstanding_documents',
    'get_outstanding_invoices_or_orders',
    'get_outstanding_invoices',
    'get_outstanding_orders',
    'get_outstanding_reference_documents'
  ];

  if (frm.events) {
    eventNames.forEach((name) => {
      if (typeof frm.events[name] === 'function') {
        frm.events[name] = noop;
      }
    });
  }

  if (typeof frm.get_outstanding_reference_documents === 'function') {
    frm.get_outstanding_reference_documents = noop;
  }

  frm.__clearing_fetch_disabled = true;
}

function setup_clearing_payment_protection(frm) {
  const marker = parse_clearing_marker(frm);
  if (!marker) {
    return;
  }

  frm.__is_clearing_payment = true;

  const ensureEditable = (fieldname) => {
    const field = frm.fields_dict[fieldname];
    if (!field) return;

    field.df.read_only = 0;
    field.df.disabled = 0;
    frm.set_df_property(fieldname, 'read_only', 0);
    frm.refresh_field(fieldname);

    if (field.$input) {
      field.$input.prop('readonly', false);
      field.$input.prop('disabled', false);
    }
  };

  ['paid_amount', 'received_amount'].forEach((fieldname) => {
    ensureEditable(fieldname);
    frappe.after_ajax(() => ensureEditable(fieldname));
  });

  // Make amount fields editable by preventing auto-calculation
  if (frm.fields_dict.paid_amount) {
    frm.fields_dict.paid_amount.$input.on('focus', function() {
      frm.__user_editing_amount = true;
    });
    frm.fields_dict.paid_amount.$input.on('blur', function() {
      setTimeout(() => {
        frm.__user_editing_amount = false;
      }, 500);
    });
  }

  if (frm.fields_dict.received_amount) {
    frm.fields_dict.received_amount.$input.on('focus', function() {
      frm.__user_editing_amount = true;
    });
    frm.fields_dict.received_amount.$input.on('blur', function() {
      setTimeout(() => {
        frm.__user_editing_amount = false;
      }, 500);
    });
  }

  // Prevent references table from triggering amount recalculation
  if (frm.fields_dict.references && frm.fields_dict.references.grid) {
    const grid = frm.fields_dict.references.grid;

    // Override the grid's refresh to prevent auto-calculation
    if (!grid.__clearing_original_refresh) {
      grid.__clearing_original_refresh = grid.refresh;
      grid.refresh = function() {
        const user_editing = frm.__user_editing_amount;
        const result = grid.__clearing_original_refresh.apply(this, arguments);

        // Restore user's amounts if they were editing
        if (user_editing) {
          frm.__user_editing_amount = true;
        }

        return result;
      };
    }
  }
}

// Handle references table to prevent auto-calculation
function apply_clearing_allocated_amount(frm) {
  if (!frm.__is_clearing_payment) {
    return;
  }
  if (frm.__clearing_amount_applied) {
    return;
  }

  const references = frm.doc.references || [];
  if (!references.length) {
    return;
  }

  const allocated_total = references.reduce(
    (total, row) => total + flt(row.allocated_amount || 0),
    0
  );

  if (!allocated_total) {
    return;
  }

  frm.__clearing_amount_applied = true;
  frm.__user_editing_amount = true;

  const updates = [];
  if ((frm.doc.payment_type || 'Receive') === 'Receive') {
    updates.push(frm.set_value('received_amount', allocated_total));
    updates.push(frm.set_value('paid_amount', allocated_total));
  } else {
    updates.push(frm.set_value('paid_amount', allocated_total));
    updates.push(frm.set_value('received_amount', allocated_total));
  }

  Promise.all(updates)
    .catch(() => null)
    .finally(() => {
      setTimeout(() => {
        frm.__user_editing_amount = false;
      }, 300);
    });
}

frappe.ui.form.on('Payment Entry Reference', {
  allocated_amount(frm, cdt, cdn) {
    // When user edits allocated amount, mark as user editing
    if (frm.__is_clearing_payment) {
      frm.__user_editing_amount = true;
      setTimeout(() => {
        frm.__user_editing_amount = false;
      }, 1000);
    }
  }
});
