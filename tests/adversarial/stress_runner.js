/**
 * Milestone M2 Adversarial Node.js Runtime Stress Test
 * Executes the exact JavaScript controller logic from static/dag.html.
 */

const fs = require('fs');
const path = require('path');
const assert = require('assert');

const dagHtml = fs.readFileSync(path.join(__dirname, '../../static/dag.html'), 'utf-8');

// Extract script blocks
const scripts = dagHtml.match(/<script[\s\S]*?>([\s\S]*?)<\/script>/gi) || [];
assert(scripts.length >= 2, 'Expected at least 2 script tags in dag.html');

console.log(`[PASS] Found ${scripts.length} script blocks in dag.html`);

// Build mock DOM environment
const elements = new Map();

class MockElement {
  constructor(id = '', tag = 'div') {
    this.id = id;
    this.tagName = tag.toUpperCase();
    this.className = '';
    this.textContent = '';
    this.innerHTML = '';
    this.attributes = new Map();
    this.classList = {
      _set: new Set(),
      contains: (c) => this.classList._set.has(c),
      add: (...cls) => cls.forEach(c => this.classList._set.add(c)),
      remove: (...cls) => cls.forEach(c => this.classList._set.delete(c)),
      toggle: (c) => {
        if (this.classList._set.has(c)) this.classList._set.delete(c);
        else this.classList._set.add(c);
      }
    };
    this.disabled = false;
    this.children = [];
    this.onclick = null;
    this.onkeydown = null;
    this.href = '';
    this.download = '';
  }

  click() { if (this.onclick) this.onclick(); }
  remove() {}
  setAttribute(name, val) { this.attributes.set(name, String(val)); }
  getAttribute(name) { return this.attributes.get(name); }
  removeAttribute(name) { this.attributes.delete(name); }
  appendChild(child) { this.children.push(child); }
  showModal() { this.setAttribute('open', 'true'); }
  close() { this.removeAttribute('open'); }
  focus() {}
}

function getElementById(id) {
  if (!elements.has(id)) {
    elements.set(id, new MockElement(id));
  }
  return elements.get(id);
}

function querySelectorAll(selector) {
  const matches = [];
  const bindMatch = selector.match(/\[data-bind="([^"]+)"\]/);
  if (bindMatch) {
    const key = bindMatch[1];
    elements.forEach(el => {
      if (el.getAttribute('data-bind') === key) {
        matches.push(el);
      }
    });
  }
  return matches;
}

// Global window/document mocks
global.document = {
  getElementById,
  querySelectorAll,
  createElement: (tag) => new MockElement('', tag),
  body: new MockElement('body', 'body'),
  addEventListener: () => {}
};
global.window = {
  location: { origin: 'https://finance-agent-83632260440.asia-south1.run.app' },
  crypto: {
    randomUUID: () => '11111111-2222-4333-8444-555555555555'
  }
};
global.localStorage = {
  _store: new Map(),
  getItem: (k) => global.localStorage._store.get(k) || null,
  setItem: (k, v) => global.localStorage._store.set(k, String(v))
};
global.Blob = class { constructor(parts, opts) { this.parts = parts; this.opts = opts; } };
global.URL = {
  createObjectURL: () => 'blob:mock-url',
  revokeObjectURL: () => {}
};
global.navigator = {
  clipboard: {
    writeText: async (text) => { global.__copiedText = text; }
  }
};

// Evaluate the script content in VM
const vm = require('vm');
const scriptContent = scripts.map(s => s.replace(/<\/?script[\s\S]*?>/gi, '')).join('\n');

const context = vm.createContext({
  ...global,
  tailwind: { config: {} },
  Blob: global.Blob,
  URL: global.URL,
  console,
  setTimeout: (fn) => fn(),
  Promise,
  Math,
  Date,
  Number,
  String,
  parseFloat,
  JSON
});

vm.runInContext(scriptContent, context);

console.log('[PASS] Script executed in mock DOM VM without runtime syntax/evaluation errors.');

// -------------------------------------------------------------
// Test 1: updateTickerBar calculation with simulated queue
// -------------------------------------------------------------
const testQueue = [
  { invoice_number: 'INV-884', vendor_name: 'Alpha', severity: 'EMERALD', triage_state: 'SETTLED', net_formatted: '₹1,08,000.00', tds_formatted: '₹10,000.00' },
  { invoice_number: 'INV-742', vendor_name: 'Beta', severity: 'AMBER', triage_state: 'COOLING_HOLD', net_formatted: '₹2,71,000.00', tds_formatted: '₹20,000.00' },
  { invoice_number: 'INV-619', vendor_name: 'Gamma', severity: 'BLUE', triage_state: 'READY_TO_DISBURSE', net_formatted: '₹1,08,000.00', tds_formatted: '₹10,000.00' }
];

context.updateTickerBar(testQueue);

const settledVal = getElementById('ticker-settled-val').textContent;
const pipelineVal = getElementById('ticker-pipeline-val').textContent;
const taxVal = getElementById('ticker-tax-val').textContent;

console.log(`Ticker Settled: ${settledVal}`);
console.log(`Ticker Pipeline: ${pipelineVal}`);
console.log(`Ticker Tax: ${taxVal}`);

assert(settledVal.includes('1,24,50,000.00'), 'Settled value calculation mismatch');
assert(pipelineVal.includes('3,79,000.00'), 'Pipeline value calculation mismatch');
assert(taxVal.includes('40,000.00'), 'Tax reserve calculation mismatch');
console.log('[PASS] Ticker Bar calculation matches financial invariants.');

// -------------------------------------------------------------
// Test 2: updateQueueTabCounters
// -------------------------------------------------------------
context.updateQueueTabCounters(testQueue);
assert.strictEqual(getElementById('qtab-all').textContent, 'All (3)');
assert.strictEqual(getElementById('qtab-action').textContent, 'Needs Attention (1)');
assert.strictEqual(getElementById('qtab-ready').textContent, 'Ready to Disburse (1)');
assert.strictEqual(getElementById('qtab-settled').textContent, 'Settled (1)');
console.log('[PASS] Queue tab counters correctly reflect 3 items categorized.');

// -------------------------------------------------------------
// Test 3: filterQueue tabs
// -------------------------------------------------------------
context.queueData = testQueue;
context.filterQueue('ACTION_REQUIRED');
assert.strictEqual(getElementById('qtab-action').getAttribute('aria-selected'), 'true');
assert.strictEqual(getElementById('qtab-all').getAttribute('aria-selected'), 'false');
console.log('[PASS] filterQueue correctly manages ARIA selection.');

// -------------------------------------------------------------
// Test 4: openPayoutModal and idempotency key generation
// -------------------------------------------------------------
context.openPayoutModal();
const modalIdem = getElementById('modal-idempotency-key').textContent;
assert(/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(modalIdem), `Invalid UUID format: ${modalIdem}`);
assert.strictEqual(getElementById('payout-confirm-modal').getAttribute('open'), 'true');
console.log(`[PASS] openPayoutModal generates and displays valid UUID v4 idempotency key: ${modalIdem}`);

// -------------------------------------------------------------
// Test 5: executeDisbursalConfirmed in-flight submit locking
// -------------------------------------------------------------
async function testDisbursalExecution() {
  const readyItem = { invoice_number: 'INV-619', vendor_name: 'Gamma', severity: 'BLUE', triage_state: 'READY_TO_DISBURSE' };
  vm.runInContext("queueData = [{ invoice_number: 'INV-619', vendor_name: 'Gamma', severity: 'BLUE', triage_state: 'READY_TO_DISBURSE' }]; currentActiveInvoice = 'INV-619'; currentActiveDecision = { invoice_number: 'INV-619', status: 'AUTO_APPROVED', gross_amount: 118000, tds_deducted: 10000, credit_deducted: 0, net_payable: 108000 };", context);

  const promise = context.executeDisbursalConfirmed();
  
  // Verify synchronous submit lock
  assert.strictEqual(getElementById('payout-confirm-btn').disabled, true);
  assert.strictEqual(getElementById('payout-cancel-btn').disabled, true);
  assert.strictEqual(getElementById('payout-close-btn').disabled, true);
  assert(getElementById('payout-confirm-btn').innerHTML.includes('animate-spin'));

  await promise;

  // Verify post-execution state
  const mutatedItem = vm.runInContext("queueData.find(i => i.invoice_number === 'INV-619')", context);
  assert.strictEqual(mutatedItem.severity, 'EMERALD');
  assert.strictEqual(mutatedItem.triage_state, 'SETTLED');
  assert.strictEqual(mutatedItem.stage_progress, '7/7 Disbursed');
  assert(mutatedItem.utr.startsWith('RZX'));
  assert.strictEqual(getElementById('payout-confirm-btn').disabled, false);
  console.log('[PASS] executeDisbursalConfirmed executes in-flight locking and mutates state cleanly.');
}

// -------------------------------------------------------------
// Test 6: downloadProofManifest schema verification
// -------------------------------------------------------------
context.currentActiveInvoice = 'INV-884';
context.currentActiveDecision = {
  invoice_number: 'INV-884',
  vendor_name: 'Alpha Technologies Pvt Ltd',
  gross_amount: 118000.0,
  tds_deducted: 10000.0,
  net_payable: 108000.0,
  payout_telemetry: { utr: 'RZX20260827184001A8F' },
  cryptographic_proof: {
    canonical_sha256: '4646e5d10175d30773d1917f8a9e0465a58a7199c084eb2e3a139e3dfdb5f762',
    signing_algorithm: 'Ed25519 (Edwards-curve Digital Signature)',
    trust_anchor: 'Google Cloud KMS / HSM Root of Trust',
    public_key_id: 'kms-key-asia-south1-fintech-ed25519-v1',
    signature: 'sig_ed25519_c305e783ab94d018f3a9e1029c5b62a67e108848d7be0174092b7c62de1872851897e9db8a91702f354ab916cf6289b0d1e57a82910793617aa810058b76250e'
  }
};

let appendedChild = null;
global.document.body.appendChild = (child) => { appendedChild = child; };
global.document.body.removeChild = () => {};

context.downloadProofManifest();

assert(appendedChild, 'Expected download anchor to be created');
assert.strictEqual(appendedChild.download, 'settlement-proof-INV-884.json');
console.log('[PASS] downloadProofManifest triggers settlement-proof-INV-884.json download.');

testDisbursalExecution().then(() => {
  console.log('\n========================================');
  console.log('ALL NODE.JS ADVERSARIAL STRESS TESTS PASSED!');
  console.log('========================================\n');
}).catch(err => {
  console.error('Test failed:', err);
  process.exit(1);
});
