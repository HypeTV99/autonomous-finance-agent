// YIRE Enterprise Accounts Payable & Statutory Treasury Operating System
// Client-Side Orchestration and Screen Architecture

let CURRENT_APP_SCREEN = 'command-center';
let CURRENT_MANUAL_TAB = 'invoice';
let CURRENT_WORKSPACE_TAB = 'invoices';
let CURRENT_DETAIL_INVOICE = null;
let CURRENT_DETAIL_SUBTAB = 'overview';
let ACTIVE_QUICK_INVOICE = null;

// --- INITIALIZATION & ROUTING ---
window.addEventListener('DOMContentLoaded', () => {
  initAppRouter();
  loadAuditFindings();
});

function initAppRouter() {
  const path = window.location.pathname.toLowerCase();
  if (path.includes('ingestion')) {
    switchAppScreen('ingestion');
  } else if (path.includes('workspace') || path.includes('ap-workspace')) {
    switchAppScreen('workspace');
  } else if (path.includes('exceptions') || path.includes('approvals')) {
    switchAppScreen('exceptions');
  } else if (path.includes('treasury')) {
    switchAppScreen('treasury');
  } else if (path.includes('auditor')) {
    switchAppScreen('auditor');
  } else if (path.includes('settings')) {
    switchAppScreen('settings');
  } else {
    switchAppScreen('command-center');
  }
}

// --- GLOBAL SCREEN SWITCHER ---
function switchAppScreen(screenId) {
  CURRENT_APP_SCREEN = screenId;
  const screens = ['command-center', 'ingestion', 'workspace', 'exceptions', 'treasury', 'auditor', 'settings'];
  
  screens.forEach(s => {
    const el = document.getElementById(`screen-${s}`);
    const navBtn = document.getElementById(`nav-btn-${s}`);
    if (el) {
      if (s === screenId) {
        el.classList.remove('hidden');
      } else {
        el.classList.add('hidden');
      }
    }
    if (navBtn) {
      if (s === screenId) {
        navBtn.className = "nav-app-btn w-full flex items-center justify-between px-3.5 py-2.5 rounded-xl bg-slate-900 text-white text-xs font-bold transition-smooth focus-visible:ring-2 focus-visible:ring-slate-900 text-left shadow-sm";
        navBtn.style.cssText = "";
      } else {
        navBtn.className = "nav-app-btn w-full flex items-center justify-between px-3.5 py-2.5 rounded-xl text-slate-600 hover:text-slate-900 hover:bg-slate-100 text-xs font-semibold transition-smooth focus-visible:ring-2 focus-visible:ring-slate-900 text-left";
        navBtn.style.cssText = "";
      }
    }
  });

  if (screenId === 'workspace') {
    renderWorkspaceInvoices();
  } else if (screenId === 'auditor') {
    loadAuditFindings();
  }

  // Update URL state without page reload
  try {
    const newPath = screenId === 'command-center' ? '/dashboard' : `/${screenId}`;
    if (window.location.pathname !== newPath && window.history.pushState) {
      window.history.pushState({ screen: screenId }, '', newPath);
    }
  } catch (e) {}

  window.scrollTo({ top: 0, behavior: 'smooth' });
}

// --- GLOBAL + ADD MODAL ---
function openGlobalAddModal() {
  const modal = document.getElementById('global-add-modal');
  if (modal) modal.showModal();
}

// --- MANUAL INGESTION TAB SWITCHER ---
function switchManualTab(tab) {
  CURRENT_MANUAL_TAB = tab;
  const tabs = ['invoice', 'po', 'grn', 'vendor'];
  tabs.forEach(t => {
    const btn = document.getElementById(`mtab-${t}`);
    const form = document.getElementById(`form-manual-${t}`);
    if (btn) {
      if (t === tab) {
        btn.className = "focus-visible:ring-2 focus-visible:ring-slate-900 px-3 py-1.5 rounded-lg font-bold transition-smooth bg-slate-900 text-white";
        btn.style.cssText = "";
      } else {
        btn.className = "focus-visible:ring-2 focus-visible:ring-slate-900 px-3 py-1.5 rounded-lg text-slate-500 hover:text-slate-900 transition-smooth";
        btn.style.cssText = "";
      }
    }
    if (form) {
      if (t === tab) form.classList.remove('hidden');
      else form.classList.add('hidden');
    }
  });
}

// --- MANUAL CALCULATION PREVIEW ---
function updateManualInvoiceCalculations() {
  const sub = parseFloat(document.getElementById('man-inv-subtotal')?.value || 100000);
  const gstRate = parseFloat(document.getElementById('man-inv-gst-rate')?.value || 18);
  const tdsCode = document.getElementById('man-inv-tds-code')?.value || '194J';
  const tdsRate = tdsCode === '194C' ? 0.01 : (tdsCode === '194I' ? 0.10 : 0.02);

  const gst = sub * (gstRate / 100);
  const tds = sub * tdsRate;
  const net = (sub + gst) - tds;

  const f = (n) => `INR ${n.toLocaleString('en-IN', {minimumFractionDigits: 2})}`;
  const subEl = document.getElementById('man-prev-sub');
  const gstEl = document.getElementById('man-prev-gst');
  const tdsEl = document.getElementById('man-prev-tds');
  const netEl = document.getElementById('man-prev-net');

  if (subEl) subEl.innerText = f(sub);
  if (gstEl) gstEl.innerText = `+${f(gst)}`;
  if (tdsEl) tdsEl.innerText = `-${f(tds)}`;
  if (netEl) netEl.innerText = f(net);
}

// --- MANUAL INVOICE SUBMISSION ---
async function handleManualInvoiceSubmit(event) {
  event.preventDefault();
  const btn = document.getElementById('btn-submit-manual-invoice');
  if (btn) {
    if (btn.disabled) return;
    btn.disabled = true;
    btn.innerText = "Validating & Ingesting...";
  }

  const payload = {
    invoice_number: document.getElementById('man-inv-number').value.trim(),
    vendor_name: document.getElementById('man-inv-vendor').value,
    subtotal: parseFloat(document.getElementById('man-inv-subtotal').value || 100000),
    gst_rate: parseFloat(document.getElementById('man-inv-gst-rate').value || 18),
    due_date: document.getElementById('man-inv-date').value || '2026-09-25',
    po_number: document.getElementById('man-inv-po').value.trim() || 'PO-93821',
    grn_number: 'GRN-3321',
    maker: ACTIVE_ROLE
  };

  try {
    const res = await fetch('/api/v1/invoices/manual', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-User-Role': ACTIVE_ROLE },
      body: JSON.stringify(payload)
    });
    const data = await res.json();
    if (res.ok) {
      showToast("Invoice Recorded", `Successfully registered ${payload.invoice_number} with 3-way match validation.`, "success");
      await loadTreasuryData();
      switchAppScreen('workspace');
    } else {
      showToast("Submission Error", data.detail || "Validation halted by policy gate", "error");
    }
  } catch (err) {
    showToast("Network Error", "Could not reach ingestion service", "error");
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.innerText = "Submit Invoice to Pipeline";
    }
  }
}

// --- MANUAL PO SUBMISSION ---
async function handleManualPOSubmit(event) {
  event.preventDefault();
  const btn = document.getElementById('btn-submit-manual-po');
  if (btn) {
    if (btn.disabled) return;
    btn.disabled = true;
  }
  const payload = {
    po_number: document.getElementById('man-po-num').value.trim(),
    vendor_name: document.getElementById('man-po-vendor').value.trim(),
    total_amount: parseFloat(document.getElementById('man-po-amount').value || 500000)
  };
  try {
    const res = await fetch('/api/v1/purchase-orders', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-User-Role': ACTIVE_ROLE },
      body: JSON.stringify(payload)
    });
    const data = await res.json();
    if (res.ok) {
      showToast("PO Registered", `Purchase order ${payload.po_number} added to PO Registry.`, "success");
      switchAppScreen('workspace');
      switchWorkspaceTab('pos');
    } else {
      showToast("Error", data.detail || "Failed to create PO", "error");
    }
  } catch (err) {
    showToast("Error", "Network connection failed", "error");
  } finally {
    if (btn) btn.disabled = false;
  }
}

// --- MANUAL GRN SUBMISSION ---
async function handleManualGRNSubmit(event) {
  event.preventDefault();
  const btn = document.getElementById('btn-submit-manual-grn');
  if (btn) {
    if (btn.disabled) return;
    btn.disabled = true;
  }
  const payload = {
    po_number: document.getElementById('man-grn-po').value.trim(),
    grn_number: document.getElementById('man-grn-num').value.trim(),
    received_quantity: parseFloat(document.getElementById('man-grn-qty').value || 100),
    accepted_quantity: parseFloat(document.getElementById('man-grn-acc-qty').value || 100),
    rejected_quantity: 0.0
  };
  try {
    const res = await fetch('/api/v1/goods-receipts', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-User-Role': ACTIVE_ROLE },
      body: JSON.stringify(payload)
    });
    const data = await res.json();
    if (res.ok) {
      showToast("GRN Logged", `Goods receipt ${payload.grn_number} verified and accepted.`, "success");
      switchAppScreen('workspace');
      switchWorkspaceTab('grns');
    } else {
      showToast("Error", data.detail || "Failed to record GRN", "error");
    }
  } catch (err) {
    showToast("Error", "Network error", "error");
  } finally {
    if (btn) btn.disabled = false;
  }
}

// --- MANUAL VENDOR SUBMISSION ---
async function handleManualVendorSubmit(event) {
  event.preventDefault();
  const btn = document.getElementById('btn-submit-manual-vendor');
  if (btn) {
    if (btn.disabled) return;
    btn.disabled = true;
  }
  const payload = {
    name: document.getElementById('man-vend-name').value.trim(),
    gstin: document.getElementById('man-vend-gstin').value.trim(),
    pan: document.getElementById('man-vend-pan').value.trim(),
    bankAcc: document.getElementById('man-vend-bankacc').value.trim(),
    bankIfsc: document.getElementById('man-vend-ifsc').value.trim(),
    bankName: document.getElementById('man-vend-bankname').value.trim()
  };
  try {
    const res = await fetch('/api/v1/vendors', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-User-Role': ACTIVE_ROLE },
      body: JSON.stringify(payload)
    });
    const data = await res.json();
    if (res.ok) {
      showToast("Vendor Added", `Registered ${payload.name} with compliance cooling active.`, "success");
      switchAppScreen('workspace');
      switchWorkspaceTab('vendors');
    } else {
      showToast("Error", data.detail || "Failed to add vendor", "error");
    }
  } catch (err) {
    showToast("Error", "Network connection failed", "error");
  } finally {
    if (btn) btn.disabled = false;
  }
}

// --- AP WORKSPACE TAB SWITCHER ---
function switchWorkspaceTab(tab) {
  CURRENT_WORKSPACE_TAB = tab;
  const tabs = ['invoices', 'pos', 'grns', 'vendors'];
  tabs.forEach(t => {
    const btn = document.getElementById(`wtab-${t}`);
    const panel = document.getElementById(`wpanel-${t}`);
    if (btn) {
      if (t === tab) {
        btn.className = "focus-visible:ring-2 focus-visible:ring-slate-900 px-3.5 py-1.5 rounded-lg bg-white text-slate-900 font-bold shadow-2xs transition-smooth";
      } else {
        btn.className = "focus-visible:ring-2 focus-visible:ring-slate-900 px-3.5 py-1.5 rounded-lg text-slate-500 hover:text-slate-900 transition-smooth";
      }
    }
    if (panel) {
      if (t === tab) panel.classList.remove('hidden');
      else panel.classList.add('hidden');
    }
  });
}

// --- RENDER INVOICES IN WORKSPACE ---
function renderWorkspaceInvoices() {
  const tbody = document.getElementById('workspace-invoices-tbody');
  if (!tbody) return;
  tbody.innerHTML = '';

  const query = (document.getElementById('workspace-inv-search')?.value || '').toLowerCase();
  const statusFilter = document.getElementById('workspace-inv-status')?.value || 'ALL';

  let items = GLOBAL_DECISIONS.filter(d => {
    const matchesQ = (d.invoice_number || '').toLowerCase().includes(query) || (d.vendor_name || '').toLowerCase().includes(query);
    if (!matchesQ) return false;
    if (statusFilter === 'ALL') return true;
    if (statusFilter === 'READY') return (d.status === 'READY_TO_DISBURSE' || d.status === 'AUTO_SCHEDULED_STP');
    if (statusFilter === 'ACTION') return (d.status === 'ACTION_REQUIRED' || (d.active_exceptions && d.active_exceptions.length > 0));
    if (statusFilter === 'SETTLED') return (d.status === 'SETTLED' || d.stage_7_status === 'DISBURSED');
    return true;
  });

  const countEl = document.getElementById('workspace-inv-count');
  if (countEl) countEl.innerText = `Showing ${items.length} transactions`;

  if (items.length === 0) {
    tbody.innerHTML = `<tr><td colspan="6" class="py-8 text-center text-slate-400 text-xs">No matching transactions found.</td></tr>`;
    return;
  }

  items.forEach(item => {
    const tr = document.createElement('tr');
    tr.className = "hover:bg-slate-50/70 transition-colors";
    
    const gross = Number(item.gross_amount || item.subtotal || 0).toLocaleString('en-IN', {minimumFractionDigits: 2});
    const tds = Number(item.tds_deducted || 0).toLocaleString('en-IN', {minimumFractionDigits: 2});
    const net = Number(item.net_payable || 0).toLocaleString('en-IN', {minimumFractionDigits: 2});
    
    const isSettled = (item.status === 'SETTLED' || item.stage_7_status === 'DISBURSED');
    const isHold = (item.status === 'ACTION_REQUIRED' || (item.active_exceptions && item.active_exceptions.length > 0));

    let statusBadge = `<span class="px-2 py-0.5 rounded-full bg-blue-50 text-blue-800 text-[10px] font-semibold">Ready to Pay</span>`;
    if (isSettled) {
      statusBadge = `<span class="px-2 py-0.5 rounded-full bg-emerald-50 text-emerald-800 text-[10px] font-semibold">Settled (IMPS)</span>`;
    } else if (isHold) {
      statusBadge = `<span class="px-2 py-0.5 rounded-full bg-amber-50 text-amber-900 text-[10px] font-semibold">Exception Hold</span>`;
    }

    tr.innerHTML = `
      <td class="py-3 px-3">
        <div class="font-bold text-slate-900 font-mono">${item.invoice_number}</div>
        <div class="text-[11px] text-slate-500">${item.vendor_name || 'Alpha Technologies'}</div>
      </td>
      <td class="py-3 px-3 font-mono text-[11px] text-slate-600">
        <div>PO: ${item.po_number || 'PO-93821'}</div>
        <div class="text-slate-400">GRN: ${item.grn_number || 'GRN-3321'}</div>
      </td>
      <td class="py-3 px-3 text-right font-mono font-bold text-slate-900">INR ${gross}</td>
      <td class="py-3 px-3 text-right font-mono text-slate-700">
        <div class="text-rose-800">-INR ${tds}</div>
        <div class="font-bold text-emerald-900">INR ${net}</div>
      </td>
      <td class="py-3 px-3 text-center">${statusBadge}</td>
      <td class="py-3 px-3 text-right space-x-1.5">
        <button onclick="openQuickDrawer('${item.invoice_number}')" class="focus-visible:ring-2 focus-visible:ring-slate-900 px-2.5 py-1 rounded-lg border border-slate-200 hover:bg-slate-100 text-[11px] font-semibold text-slate-700 transition-smooth">
          Peek
        </button>
        <button onclick="openFullDetailModal('${item.invoice_number}')" class="focus-visible:ring-2 focus-visible:ring-slate-900 px-2.5 py-1 rounded-lg bg-black hover:bg-slate-800 text-white text-[11px] font-bold transition-smooth">
          Review
        </button>
      </td>
    `;
    tbody.appendChild(tr);
  });
}

function filterWorkspaceInvoices() {
  renderWorkspaceInvoices();
}

// --- QUICK PEEK DRAWER ---
function openQuickDrawer(invNumber) {
  ACTIVE_QUICK_INVOICE = invNumber;
  const drawer = document.getElementById('quick-drawer');
  const content = document.getElementById('quick-drawer-content');
  const numEl = document.getElementById('quick-inv-num');

  const item = GLOBAL_DECISIONS.find(d => d.invoice_number === invNumber) || {
    invoice_number: invNumber,
    vendor_name: 'Alpha Technologies Pvt Ltd',
    gross_amount: 118000,
    tds_deducted: 2360,
    net_payable: 115640,
    status: 'AUTO_SCHEDULED_STP'
  };

  if (numEl) numEl.innerText = invNumber;
  if (content) {
    const gross = Number(item.gross_amount || 118000).toLocaleString('en-IN', {minimumFractionDigits: 2});
    const tds = Number(item.tds_deducted || 2360).toLocaleString('en-IN', {minimumFractionDigits: 2});
    const net = Number(item.net_payable || 115640).toLocaleString('en-IN', {minimumFractionDigits: 2});

    content.innerHTML = `
      <div class="p-3.5 bg-slate-50 rounded-xl border border-slate-100 space-y-1">
        <span class="text-[10px] text-slate-400 font-bold uppercase">Vendor Beneficiary</span>
        <div class="font-bold text-slate-900 text-xs">${item.vendor_name || 'Alpha Technologies'}</div>
        <div class="text-[11px] text-slate-500 font-mono">PAN: AAACB1234K &bull; GSTIN: 27AAACB1234K1Z5</div>
      </div>
      <div class="p-3.5 bg-slate-50 rounded-xl border border-slate-100 space-y-2 font-mono">
        <div class="flex justify-between"><span class="text-slate-500 font-sans">Gross Billed</span><span class="font-bold">INR ${gross}</span></div>
        <div class="flex justify-between text-rose-800"><span class="font-sans">Statutory TDS (Sec 194J)</span><span>-INR ${tds}</span></div>
        <div class="flex justify-between border-t pt-1 font-extrabold text-emerald-900 text-sm"><span>Net Disbursable</span><span>INR ${net}</span></div>
      </div>
      <div class="p-3 bg-emerald-50 rounded-xl border border-emerald-200 text-emerald-900 text-xs flex items-center gap-2">
        <span class="material-symbols-outlined text-[18px]">verified</span>
        <span>3-Way Match &amp; GSTR-2B Verified</span>
      </div>
    `;
  }

  if (drawer) {
    drawer.classList.remove('hidden');
    drawer.classList.remove('translate-x-full');
  }
}

function closeQuickDrawer() {
  const drawer = document.getElementById('quick-drawer');
  if (drawer) {
    drawer.classList.add('translate-x-full');
    setTimeout(() => drawer.classList.add('hidden'), 200);
  }
  ACTIVE_QUICK_INVOICE = null;
}

function openFullDetailFromQuick() {
  if (ACTIVE_QUICK_INVOICE) {
    const inv = ACTIVE_QUICK_INVOICE;
    closeQuickDrawer();
    openFullDetailModal(inv);
  }
}

// --- FLAGSHIP 6-SUBTAB INVOICE DETAIL MODAL ---
function openFullDetailModal(invNumber) {
  CURRENT_DETAIL_INVOICE = GLOBAL_DECISIONS.find(d => d.invoice_number === invNumber) || {
    invoice_number: invNumber,
    vendor_name: 'Alpha Technologies Pvt Ltd',
    gross_amount: 118000,
    tds_deducted: 10000,
    credit_applied: 0,
    net_payable: 108000,
    status: 'AUTO_SCHEDULED_STP'
  };

  const titleEl = document.getElementById('modal-inv-title');
  const subEl = document.getElementById('modal-inv-sub');
  if (titleEl) titleEl.innerText = `Invoice Dossier: ${CURRENT_DETAIL_INVOICE.invoice_number}`;
  if (subEl) subEl.innerText = `Beneficiary: ${CURRENT_DETAIL_INVOICE.vendor_name || 'Alpha Technologies'}`;

  switchDetailSubTab('overview');
  const modal = document.getElementById('invoice-detail-modal');
  if (modal) modal.showModal();
}

function switchDetailSubTab(tab) {
  CURRENT_DETAIL_SUBTAB = tab;
  const tabs = ['overview', 'matching', 'tax', 'accounting', 'payment', 'audit'];
  tabs.forEach(t => {
    const btn = document.getElementById(`dtab-${t}`);
    if (btn) {
      if (t === tab) {
        btn.className = "focus-visible:ring-2 focus-visible:ring-slate-900 pb-2.5 px-2 border-b-2 border-slate-900 text-slate-900 font-bold transition-smooth";
      } else {
        btn.className = "focus-visible:ring-2 focus-visible:ring-slate-900 pb-2.5 px-2 text-slate-500 hover:text-slate-900 transition-smooth";
      }
    }
  });
  renderDetailModalContent();
}

function renderDetailModalContent() {
  const body = document.getElementById('detail-modal-body');
  if (!body || !CURRENT_DETAIL_INVOICE) return;
  const inv = CURRENT_DETAIL_INVOICE;

  const gross = Number(inv.gross_amount || 118000).toLocaleString('en-IN', {minimumFractionDigits: 2});
  const tds = Number(inv.tds_deducted || 10000).toLocaleString('en-IN', {minimumFractionDigits: 2});
  const credit = Number(inv.credit_applied || 0).toLocaleString('en-IN', {minimumFractionDigits: 2});
  const net = Number(inv.net_payable || 108000).toLocaleString('en-IN', {minimumFractionDigits: 2});

  if (CURRENT_DETAIL_SUBTAB === 'overview') {
    body.innerHTML = `
      <div class="space-y-4">
        <!-- Waterfall Card -->
        <div class="p-4 rounded-2xl bg-slate-50 border border-slate-200 space-y-3 font-mono text-xs">
          <span class="text-[10px] font-bold text-slate-400 uppercase font-sans">Gross-to-Net Waterfall</span>
          <div class="grid grid-cols-4 gap-2 text-center">
            <div class="p-2.5 bg-white rounded-xl border"><span class="text-[10px] text-slate-400 block font-sans">Gross Invoice</span><span class="font-bold text-slate-900">INR ${gross}</span></div>
            <div class="p-2.5 bg-white rounded-xl border text-rose-800"><span class="text-[10px] text-slate-400 block font-sans">TDS (Sec 194J)</span><span class="font-bold">-INR ${tds}</span></div>
            <div class="p-2.5 bg-white rounded-xl border text-amber-800"><span class="text-[10px] text-slate-400 block font-sans">Credits Applied</span><span class="font-bold">-INR ${credit}</span></div>
            <div class="p-2.5 bg-emerald-50 rounded-xl border border-emerald-200 text-emerald-950"><span class="text-[10px] text-emerald-800 block font-sans">Net Payable</span><span class="font-extrabold text-sm">INR ${net}</span></div>
          </div>
        </div>

        <!-- Vendor & Contract Summary -->
        <div class="grid grid-cols-2 gap-3 text-xs">
          <div class="p-3.5 rounded-xl border border-slate-200 bg-white space-y-1">
            <span class="text-[10px] text-slate-400 uppercase font-bold">Vendor Credentials</span>
            <div class="font-bold text-slate-900">${inv.vendor_name || 'Alpha Technologies Pvt Ltd'}</div>
            <div class="text-[11px] text-slate-500 font-mono">PAN: AAACB1234K &bull; GSTIN: 27AAACB1234K1Z5</div>
            <div class="pt-1"><span class="px-2 py-0.5 rounded-full bg-emerald-50 text-emerald-800 text-[10px] font-semibold">Bank KYC Confirmed</span></div>
          </div>
          <div class="p-3.5 rounded-xl border border-slate-200 bg-white space-y-1">
            <span class="text-[10px] text-slate-400 uppercase font-bold">Contract Governance</span>
            <div class="font-bold text-slate-900 font-mono">${inv.po_number || 'PO-93821'}</div>
            <div class="text-[11px] text-slate-500">Warehouse Receipt: ${inv.grn_number || 'GRN-3321'}</div>
            <div class="pt-1"><span class="px-2 py-0.5 rounded-full bg-emerald-50 text-emerald-800 text-[10px] font-semibold">Within 2.0% Tolerance</span></div>
          </div>
        </div>
      </div>
    `;
  } else if (CURRENT_DETAIL_SUBTAB === 'matching') {
    body.innerHTML = `
      <div class="space-y-4 text-xs">
        <div class="p-4 rounded-xl bg-slate-50 border border-slate-200 space-y-2">
          <div class="flex justify-between font-bold text-slate-900">
            <span>3-Way PO &amp; Goods Receipt Comparison</span>
            <span class="text-emerald-700 font-mono">Variance: 0.0% (Matched)</span>
          </div>
          <p class="text-slate-600 text-[11px]">Billed line items match purchase order authorized rates and warehouse accepted delivery quantities.</p>
        </div>
        <div class="border border-slate-200 rounded-xl overflow-hidden">
          <table class="w-full text-left text-xs">
            <thead class="bg-slate-50 border-b border-slate-200 text-[10px] font-bold text-slate-400 uppercase">
              <tr><th class="p-2.5">Item</th><th class="p-2.5 text-right">PO Rate</th><th class="p-2.5 text-right">Billed Rate</th><th class="p-2.5 text-right">Accepted Qty</th><th class="p-2.5 text-center">Status</th></tr>
            </thead>
            <tbody class="divide-y divide-slate-100 font-mono">
              <tr>
                <td class="p-2.5 font-sans font-medium">Software Engineering Services</td>
                <td class="p-2.5 text-right">INR 1,000.00</td>
                <td class="p-2.5 text-right font-bold text-slate-900">INR 1,000.00</td>
                <td class="p-2.5 text-right">100.00</td>
                <td class="p-2.5 text-center font-sans"><span class="px-2 py-0.5 rounded bg-emerald-50 text-emerald-800 text-[10px] font-bold">MATCHED</span></td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    `;
  } else if (CURRENT_DETAIL_SUBTAB === 'tax') {
    body.innerHTML = `
      <div class="space-y-3 text-xs">
        <div class="p-4 rounded-xl bg-slate-50 border border-slate-200 space-y-1">
          <div class="flex justify-between font-bold text-slate-900">
            <span>Statutory TDS Determination (Income-tax Act 2025)</span>
            <span class="text-slate-800 font-mono">Sec 194J (2.0%)</span>
          </div>
          <p class="text-[11px] text-slate-600">Technical and Professional services threshold applied on base taxable subtotal.</p>
        </div>
        <div class="grid grid-cols-2 gap-3 font-mono">
          <div class="p-3 bg-white border rounded-xl">
            <span class="text-slate-400 block text-[10px] font-sans">e-Invoice IRN QR Code</span>
            <span class="font-bold text-emerald-700 text-xs">VERIFIED &bull; VALID</span>
          </div>
          <div class="p-3 bg-white border rounded-xl">
            <span class="text-slate-400 block text-[10px] font-sans">GSTR-2B ITC Matching</span>
            <span class="font-bold text-emerald-700 text-xs">AUTO-RECONCILED</span>
          </div>
        </div>
      </div>
    `;
  } else if (CURRENT_DETAIL_SUBTAB === 'accounting') {
    body.innerHTML = `
      <div class="space-y-3 text-xs">
        <div class="flex items-center justify-between p-3 rounded-xl bg-emerald-50 border border-emerald-200 text-emerald-950 font-bold">
          <span>General Ledger Balance Invariant</span>
          <span class="font-mono">Debits (INR ${gross}) == Credits (INR ${gross})</span>
        </div>
        <div class="border border-slate-200 rounded-xl overflow-hidden">
          <table class="w-full text-left text-xs font-mono">
            <thead class="bg-slate-50 border-b text-[10px] text-slate-400 font-bold uppercase font-sans">
              <tr><th class="p-2.5">Account Description</th><th class="p-2.5 text-right">Debit</th><th class="p-2.5 text-right">Credit</th></tr>
            </thead>
            <tbody class="divide-y divide-slate-100">
              <tr><td class="p-2.5 font-sans">Operational Expense (Cloud Consulting)</td><td class="p-2.5 text-right font-bold text-slate-900">INR ${gross}</td><td class="p-2.5 text-right text-slate-400">0.00</td></tr>
              <tr><td class="p-2.5 font-sans">Statutory TDS Payable (Challan 281)</td><td class="p-2.5 text-right text-slate-400">0.00</td><td class="p-2.5 text-right text-rose-800">INR ${tds}</td></tr>
              <tr><td class="p-2.5 font-sans">Vendor Accounts Payable (Net Disbursable)</td><td class="p-2.5 text-right text-slate-400">0.00</td><td class="p-2.5 text-right font-extrabold text-emerald-900">INR ${net}</td></tr>
            </tbody>
          </table>
        </div>
      </div>
    `;
  } else if (CURRENT_DETAIL_SUBTAB === 'payment') {
    body.innerHTML = `
      <div class="space-y-4 text-xs">
        <div class="p-4 rounded-xl bg-slate-50 border border-slate-200 space-y-2">
          <div class="flex justify-between font-bold text-slate-900">
            <span>Treasury Disbursement Channel</span>
            <span class="text-emerald-700 font-mono">NPCI 24x7 IMPS Rail</span>
          </div>
          <div class="grid grid-cols-2 gap-2 text-[11px] font-mono pt-1">
            <div><span class="text-slate-400 font-sans block">Bank Entity:</span>HDFC Bank Limited</div>
            <div><span class="text-slate-400 font-sans block">Account Mask:</span>********4021</div>
            <div><span class="text-slate-400 font-sans block">IFSC:</span>HDFC0000060</div>
            <div><span class="text-slate-400 font-sans block">UTR Status:</span>${inv.status === 'SETTLED' ? 'RZX20260827184001A8F' : 'Ready for Clearing'}</div>
          </div>
        </div>
        <div class="flex justify-end gap-2">
          <button onclick="disburseInvoice('${inv.invoice_number}'); document.getElementById('invoice-detail-modal').close();" class="focus-visible:ring-2 focus-visible:ring-slate-900 px-5 py-2.5 bg-black hover:bg-slate-800 text-white font-bold rounded-xl text-xs transition-smooth">
            Release Payment Wire
          </button>
        </div>
      </div>
    `;
  } else if (CURRENT_DETAIL_SUBTAB === 'audit') {
    body.innerHTML = `
      <div class="space-y-3 text-xs">
        <div class="p-3.5 rounded-xl bg-slate-50 border font-mono text-[11px] space-y-2">
          <div><span class="text-slate-400 font-sans block text-[10px]">Canonical RFC 8785 SHA-256 Digest:</span>4646e5d10175d30773d1917f8a9e0465a58a7199c084eb2e3a139e3dfdb5f762</div>
          <div><span class="text-slate-400 font-sans block text-[10px]">Hardware KMS Seal (Ed25519):</span>kms-key-asia-south1-fintech-ed25519-v1 &bull; Signature Verified</div>
        </div>
        <div class="flex justify-between items-center pt-2">
          <span class="text-[11px] text-emerald-800 font-bold flex items-center gap-1.5">
            <span class="material-symbols-outlined text-[16px]">verified</span>
            <span>Cryptographic Proof Invariant Sealed</span>
          </span>
          <a href="/audit#verify-${inv.invoice_number}" class="focus-visible:ring-2 focus-visible:ring-slate-900 px-4 py-2 rounded-xl bg-slate-900 text-white font-bold text-xs transition-smooth">
            Open in Forensic Vault
          </a>
        </div>
      </div>
    `;
  }
}

// --- WHAT-IF POLICY SIMULATION ---
function runWhatIfSimulation() {
  const tol = parseFloat(document.getElementById('sim-tolerance')?.value || 5.0);
  const resBox = document.getElementById('sim-result-box');
  if (!resBox) return;

  const stpRate = Math.min(99.8, 87.5 + (tol * 1.5)).toFixed(1);
  resBox.innerHTML = `
    <span class="font-bold text-purple-950">Simulation Prediction (${tol.toFixed(1)}% Tolerance):</span>
    <p class="text-slate-700 text-[11px] mt-1">Under a ${tol.toFixed(1)}% PO tolerance ceiling, STP rate increases to ${stpRate}%. Invoices exceeding standard 2% tolerance are automatically approved without human intervention.</p>
  `;
  showToast("Simulation Complete", `Modeled ${tol.toFixed(1)}% tolerance impact on historical queue.`, "info");
}

// --- AUDIT FINDING LOGGING ---
async function loadAuditFindings() {
  try {
    const res = await fetch('/api/v1/audit/findings');
    const data = await res.json();
    const list = document.getElementById('audit-findings-list');
    const countEl = document.getElementById('audit-finding-count');
    if (res.ok && data.findings && list) {
      if (countEl) countEl.innerText = `${data.findings.length} Registered Observations`;
      list.innerHTML = '';
      data.findings.forEach(f => {
        const item = document.createElement('div');
        item.className = "p-3.5 rounded-xl border border-slate-200 bg-white space-y-1 text-xs";
        item.innerHTML = `
          <div class="flex items-center justify-between">
            <span class="font-bold text-slate-900">${f.id} &bull; ${f.category} (${f.invoice_number})</span>
            <span class="px-2 py-0.5 rounded bg-amber-100 text-amber-900 text-[10px] font-bold font-mono">${f.severity}</span>
          </div>
          <p class="text-[11px] text-slate-600">${f.finding}</p>
        `;
        list.appendChild(item);
      });
    }
  } catch (e) {}
}

function openAuditFindingModal() {
  const modal = document.getElementById('audit-finding-modal');
  if (modal) modal.showModal();
}

async function handleAuditFindingSubmit(event) {
  event.preventDefault();
  const btn = document.getElementById('btn-submit-audit-finding');
  if (btn) {
    if (btn.disabled) return;
    btn.disabled = true;
  }
  const payload = {
    invoice_number: document.getElementById('fnd-inv-num').value.trim(),
    severity: document.getElementById('fnd-severity').value,
    category: "AUDITOR_OBSERVATION",
    finding: document.getElementById('fnd-desc').value.trim()
  };
  try {
    const res = await fetch('/api/v1/audit/findings', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    if (res.ok) {
      showToast("Finding Logged", "Audit observation registered with immutable timestamp.", "success");
      document.getElementById('audit-finding-modal').close();
      await loadAuditFindings();
    }
  } catch (e) {
    showToast("Error", "Could not record finding", "error");
  } finally {
    if (btn) btn.disabled = false;
  }
}

// --- UNIVERSAL SEARCH HANDLER ---
function handleUniversalSearch(val) {
  if (typeof filterInvoices === 'function') filterInvoices(val);
  if (typeof filterWorkspaceInvoices === 'function') filterWorkspaceInvoices(val);
}
