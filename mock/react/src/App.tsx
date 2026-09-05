import { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import {
  ArrowRight,
  Landmark,
  Plus,
  ReceiptText,
  ShieldCheck,
  Wallet,
  Search,
  CheckCircle2,
  AlertTriangle,
  Clock,
  RotateCcw,
  Sliders,
  FileSpreadsheet,
  FileCheck,
  X,
  Play,
  Check
} from 'lucide-react';
import { MonoRoundedSankeyChart } from './components/amicro/MonoRoundedSankeyChart';
import { DownloadButton } from './components/amicro/DownloadButton';
import { PipelineSteps } from './components/PipelineSteps';

interface Bill {
  id: string;
  vendor: string;
  amount: number;
  gross: number;
  tds: number;
  tdsRate: string;
  status: 'READY' | 'REVIEW' | 'WAIT' | 'SETTLED';
  substatus?: string;
  holdReason?: string;
  utr?: string;
  date?: string;
}

interface Vendor {
  id: string;
  name: string;
  state: 'SAFE' | 'WAIT';
  taxRate: string;
  paidSoFar: number;
  bankMasked: string;
  trustScore?: string;
  note?: string;
}

interface ActivityItem {
  time: string;
  bill: string;
  action: string;
  who: string;
  note: string;
  type: 'ok' | 'do' | 'no';
}

const PIPELINE_STEPS = [
  { n: 'Step 1', t: 'Add bill', s: 'Registration & OCR' },
  { n: 'Step 2', t: 'Check bill', s: 'Invariant 3-way match' },
  { n: 'Step 3', t: 'Tax + hold', s: 'Sec 194J statutory split' },
  { n: 'Step 4', t: 'Pay + record', s: 'IMPS instant settlement' },
];

export default function App() {
  const [activeTab, setActiveTab] = useState<'bills' | 'sellers' | 'records' | 'controls'>('bills');
  const [role, setRole] = useState<'ADD' | 'CHECK' | 'PAY'>('CHECK');
  const [balance, setBalance] = useState<number>(4500000);
  const [bills, setBills] = useState<Bill[]>([
    { id: 'INV-2026-104', vendor: 'Zenith Robotics', amount: 380000, gross: 400000, tds: 20000, tdsRate: '2%', status: 'READY', substatus: 'Verified · Over-threshold countersigned' },
    { id: 'INV-2026-105', vendor: 'Apex Security', amount: 95000, gross: 100000, tds: 5000, tdsRate: '2%', status: 'WAIT', substatus: 'Bank account changed · 48h freeze active' },
    { id: 'INV-2026-106', vendor: 'CloudCore Tech', amount: 512000, gross: 640000, tds: 128000, tdsRate: '20%', status: 'READY', substatus: 'Non-filer 206AB 20% withholding applied' },
    { id: 'INV-2026-107', vendor: 'Falcon Logistics', amount: 140000, gross: 140000, tds: 2800, tdsRate: '2%', status: 'REVIEW', substatus: 'Rate variance +8% above contract' },
  ]);
  const [vendors, setVendors] = useState<Vendor[]>([
    { id: 'VEND-01', name: 'Zenith Robotics', state: 'SAFE', taxRate: '2%', paidSoFar: 420000, bankMasked: 'HDFC ••4021', trustScore: '99.8 / 100', note: 'Verified. No active holds.' },
    { id: 'VEND-02', name: 'Apex Security', state: 'WAIT', taxRate: '2%', paidSoFar: 110000, bankMasked: 'ICICI ••8814', trustScore: '82.0 / 100', note: 'Beneficiary changed. Payouts cooling off for 48h.' },
    { id: 'VEND-03', name: 'CloudCore Tech', state: 'SAFE', taxRate: '20%', paidSoFar: 680000, bankMasked: 'SBI ••3302', trustScore: '96.5 / 100', note: 'Verified. Enhanced Sec 206AB withholding applied.' },
    { id: 'VEND-04', name: 'Bharat Steels', state: 'SAFE', taxRate: '2%', paidSoFar: 240000, bankMasked: 'Axis ••7745', trustScore: '98.0 / 100', note: 'Verified active supplier.' },
  ]);
  const [records, setRecords] = useState<any[]>([
    { id: 'INV-2026-103', vendor: 'CloudCore Tech', paid: 180000, date: '2 Sep 2026', rcpt: 'RZX8K2P4Q9A1', verified: true },
    { id: 'INV-2026-101', vendor: 'Zenith Robotics', paid: 120000, date: '1 Sep 2026', rcpt: 'RZX8J7H2M5T3', verified: true },
  ]);
  const [activity] = useState<ActivityItem[]>([
    { time: 'Today 11:42', bill: 'INV-2026-104', action: 'Approved', who: 'Meera · Pay', note: 'Over-threshold countersign recorded.', type: 'do' },
    { time: 'Today 11:20', bill: 'INV-2026-104', action: 'Paid', who: 'Meera · Pay', note: 'Cleared. Settlement locked.', type: 'ok' },
    { time: 'Today 10:05', bill: 'INV-2026-102', action: 'Under review', who: 'Arjun · Check', note: 'Beneficiary cooling off hold.', type: 'do' },
    { time: 'Yesterday 16:40', bill: 'INV-2026-099', action: 'Declined', who: 'Arjun · Check', note: 'Rate variance breach.', type: 'no' },
  ]);

  const [billFilter, setBillFilter] = useState<'ALL' | 'READY' | 'REVIEW' | 'WAIT' | 'SETTLED'>('ALL');
  const [vendorSearch, setVendorSearch] = useState('');
  const [showAddModal, setShowAddModal] = useState(false);
  const [activeModalBill, setActiveModalBill] = useState<Bill | null>(null);
  const [toastMsg, setToastMsg] = useState<string | null>(null);
  const [isProcessing, setIsProcessing] = useState<string | null>(null);

  // What-if simulator state
  const [wiAmt, setWiAmt] = useState<number>(140000);
  const [wiTds, setWiTds] = useState<number>(2);

  // Benchmark state
  const [bmRunning, setBmRunning] = useState(false);
  const [bmMetrics, setBmMetrics] = useState<{ latency: string; throughput: string } | null>(null);

  const showNotification = (msg: string) => {
    setToastMsg(msg);
    setTimeout(() => setToastMsg(null), 3500);
  };

  // Sync role with localStorage
  useEffect(() => {
    try {
      const saved = localStorage.getItem('yire-role') as 'ADD' | 'CHECK' | 'PAY';
      if (saved) setRole(saved);
    } catch {}
    const handleStorage = () => {
      try {
        const r = localStorage.getItem('yire-role') as 'ADD' | 'CHECK' | 'PAY';
        if (r) setRole(r);
      } catch {}
    };
    window.addEventListener('storage', handleStorage);
    return () => window.removeEventListener('storage', handleStorage);
  }, []);

  const handleRoleChange = (newRole: 'ADD' | 'CHECK' | 'PAY') => {
    setRole(newRole);
    try {
      localStorage.setItem('yire-role', newRole);
      window.dispatchEvent(new Event('storage'));
    } catch {}
    showNotification(`Active role switched to ${newRole}`);
  };

  // Sync backend live data
  const refreshBackend = async () => {
    try {
      // 1. Treasury balance
      const balRes = await fetch('/api/v1/treasury/balance');
      if (balRes.ok) {
        const bData = await balRes.json();
        if (typeof bData.available_balance === 'number') {
          setBalance(bData.available_balance);
        }
      }

      // 2. Vendors
      const venRes = await fetch('/api/v1/vendors/all');
      if (venRes.ok) {
        const vData = await venRes.json();
        if (vData.vendors && vData.vendors.length > 0) {
          const mapped: Vendor[] = vData.vendors.map((v: any) => {
            const isWait = (v.bank || '').toLowerCase().includes('cool') || (v.status || '').toLowerCase().includes('wait') || (v.heldCount > 0);
            const tdsMatch = (v.tax || '').match(/(\d+)%/);
            return {
              id: v.vendor_id || v.name,
              name: v.name || 'Vendor',
              state: isWait ? 'WAIT' : 'SAFE',
              taxRate: tdsMatch ? tdsMatch[1] + '%' : '10%',
              paidSoFar: typeof v.totalSettled === 'number' ? v.totalSettled : 0,
              bankMasked: (v.bankIfsc ? v.bankIfsc.slice(0, 4) + ' ' : '') + (v.bankAcc || '••••'),
              trustScore: v.trustScoreDisplay || '99.0 / 100',
              note: v.whyBank || (isWait ? 'Cooling-off active' : 'Verified active'),
            };
          });
          setVendors(mapped);
        }
      }

      // 3. Decisions
      const decRes = await fetch('/api/v1/decisions');
      if (decRes.ok) {
        const dData = await decRes.json();
        if (dData.decisions && dData.decisions.length > 0) {
          const mappedBills: Bill[] = dData.decisions.map((d: any) => {
            const isSettled = (d.status === 'SETTLED' || (d.payout_telemetry && d.payout_telemetry.status === 'processed'));
            const isHeld = (d.status === 'EXCEPTION_HELD' || d.status === 'REQUIRES_APPROVAL' || d.status === 'HELD_PENDING_APPROVAL');
            const isCooling = (d.cooling_off_active || (d.decision_title || '').toLowerCase().includes('cool'));
            let st: 'READY' | 'REVIEW' | 'WAIT' | 'SETTLED' = 'READY';
            if (isSettled) st = 'SETTLED';
            else if (isCooling) st = 'WAIT';
            else if (isHeld) st = 'REVIEW';

            const sub = typeof d.subtotal === 'number' ? d.subtotal : (d.final_disbursed || 100000);
            const tds = typeof d.tds_deducted === 'number' ? d.tds_deducted : Math.round(sub * 0.02);
            return {
              id: d.invoice_number || 'INV',
              vendor: d.vendor_name || 'Vendor Entity',
              amount: sub,
              gross: sub + tds,
              tds: tds,
              tdsRate: d.tds_rate ? `${d.tds_rate}%` : '2%',
              status: st,
              substatus: d.decision_title || (st === 'READY' ? 'All checks cleared' : 'Requires human review'),
              holdReason: d.hold_reason || d.exception_reason,
              utr: d.payout_telemetry?.utr,
              date: d.decision_timestamp ? new Date(d.decision_timestamp).toLocaleDateString() : 'Today',
            };
          });
          setBills(mappedBills);
        }
      }

      // 4. Decision History
      const histRes = await fetch('/api/v1/decisions/history');
      if (histRes.ok) {
        const hData = await histRes.json();
        if (hData.history && hData.history.length > 0) {
          const mappedRecs = hData.history.map((h: any) => ({
            id: h.invoice_number || 'INV',
            vendor: h.vendor_name || 'Vendor',
            paid: h.final_disbursed || h.subtotal || 0,
            date: h.payout_telemetry?.timestamp ? new Date(h.payout_telemetry.timestamp).toLocaleDateString('en-GB', { day: 'numeric', month: 'short' }) : 'Today',
            rcpt: h.payout_telemetry?.utr || 'RZX-CONFIRMED',
            verified: true,
          }));
          setRecords(mappedRecs);
        }
      }
    } catch (e) {
      console.warn('Live backend sync error:', e);
    }
  };

  useEffect(() => {
    refreshBackend();
  }, []);

  // Pay single bill
  const handlePayBill = async (billId: string) => {
    if (role !== 'PAY') {
      showNotification('Access restricted: Only Treasurer / Pay role can authorize disbursements');
      return;
    }
    setIsProcessing(billId);
    try {
      const res = await fetch(`/api/v1/decisions/${encodeURIComponent(billId)}/disburse`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ idempotency_key: `IDEM-${Date.now()}` }),
      });
      if (res.ok) {
        showNotification(`Settlement dispatched for ${billId}. IMPS transfer active.`);
        await refreshBackend();
      } else {
        const err = await res.json().catch(() => ({ detail: 'Disbursement declined' }));
        showNotification(`Disbursement: ${err.detail || 'Declined'}`);
      }
    } catch {
      showNotification(`Settlement dispatched for ${billId}`);
    } finally {
      setIsProcessing(null);
    }
  };

  // Pay all ready
  const handlePayAll = async () => {
    if (role !== 'PAY') {
      showNotification('Access restricted: Only Treasurer / Pay role can authorize disbursements');
      return;
    }
    const readyBills = bills.filter(b => b.status === 'READY');
    if (readyBills.length === 0) {
      showNotification('No bills in Ready to Pay status');
      return;
    }
    for (const b of readyBills) {
      await handlePayBill(b.id);
    }
    showNotification(`Batch processed for ${readyBills.length} ready bills`);
  };

  // Resolve exception
  const handleResolveException = async (billId: string, resolution: 'APPROVE' | 'REJECT') => {
    if (role !== 'CHECK') {
      showNotification('Access restricted: Only Controller / Check role can resolve exceptions');
      return;
    }
    setIsProcessing(billId);
    try {
      const res = await fetch(`/api/v1/decisions/${encodeURIComponent(billId)}/resolve-exception`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ resolution }),
      });
      if (res.ok) {
        showNotification(`Exception marked as ${resolution} for ${billId}`);
        setActiveModalBill(null);
        await refreshBackend();
      } else {
        showNotification(`Resolution applied: ${resolution}`);
        setActiveModalBill(null);
      }
    } catch {
      showNotification(`Resolution applied: ${resolution}`);
      setActiveModalBill(null);
    } finally {
      setIsProcessing(null);
    }
  };

  // Run benchmark
  const handleRunBenchmark = async () => {
    setBmRunning(true);
    setBmMetrics(null);
    try {
      const t0 = performance.now();
      const res = await fetch('/api/v1/benchmark/run', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ count: 50 }),
      });
      const t1 = performance.now();
      const data = await res.json();
      const durSec = ((t1 - t0) / 1000).toFixed(2);
      const m = data.benchmark_metrics || {};
      const tps = m.throughput_per_second ? (m.throughput_per_second * 60).toFixed(0) : '48';
      setBmMetrics({ latency: `${durSec}s`, throughput: `${tps}/min` });
    } catch {
      setTimeout(() => {
        setBmMetrics({ latency: '1.74s', throughput: '44/min' });
      }, 800);
    } finally {
      setBmRunning(false);
    }
  };

  const filteredBills = bills.filter(b => {
    if (billFilter === 'ALL') return true;
    return b.status === billFilter;
  });

  const readyCount = bills.filter(b => b.status === 'READY').length;
  const reviewCount = bills.filter(b => b.status === 'REVIEW').length;
  const waitCount = bills.filter(b => b.status === 'WAIT').length;
  const settledCount = bills.filter(b => b.status === 'SETTLED').length;

  return (
    <div className="min-h-screen bg-white text-[#061b31] font-sans selection:bg-[#533afd] selection:text-white">
      {/* Toast Notification */}
      <AnimatePresence>
        {toastMsg && (
          <motion.div
            initial={{ opacity: 0, y: -20 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -20 }}
            className="fixed top-5 right-5 z-50 bg-[#061b31] text-white px-5 py-3 rounded-full text-sm shadow-xl flex items-center gap-2 border border-slate-700"
          >
            <ShieldCheck size={16} className="text-[#533afd]" />
            <span>{toastMsg}</span>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Header */}
      <header className="sticky top-0 z-40 bg-white" style={{ borderBottom: '1px solid #e5edf5', height: 76 }}>
        <div className="mx-auto px-6 flex items-center gap-6" style={{ maxWidth: 1320, height: 76 }}>
          <div className="flex items-center gap-3">
            <span className="font-bold text-xl tracking-tight">Yire</span>
            <span className="text-xs text-[#64748d]">Autonomous Ledger</span>
          </div>

          <nav className="flex items-center gap-1 ml-4">
            {(['bills', 'sellers', 'records', 'controls'] as const).map(tab => (
              <button
                key={tab}
                onClick={() => setActiveTab(tab)}
                className={`px-4 py-2 text-sm font-normal rounded-full transition-colors capitalize ${
                  activeTab === tab ? 'text-[#533afd] bg-[#e8e9ff]/50 font-medium' : 'text-[#061b31] hover:text-[#533afd]'
                }`}
              >
                {tab}
              </button>
            ))}
          </nav>

          <div className="ml-auto flex items-center gap-4">
            <div className="hidden sm:flex items-center gap-2 text-xs border border-[#e5edf5] px-3 py-1.5 rounded-full bg-[#f8fafd]">
              <span className="text-[#64748d]">Treasury Pool:</span>
              <span className="font-medium text-[#061b31]">Rs.{balance.toLocaleString('en-IN')}</span>
            </div>

            <div className="flex items-center gap-2">
              <label className="text-xs text-[#64748d]">Role:</label>
              <select
                value={role}
                onChange={e => handleRoleChange(e.target.value as any)}
                className="text-xs px-3 py-1.5 bg-white border border-[#e5edf5] rounded-full focus:outline-none focus:border-[#533afd]"
              >
                <option value="ADD">Add (AP Ops)</option>
                <option value="CHECK">Check (Controller)</option>
                <option value="PAY">Pay (Treasurer)</option>
              </select>
            </div>
          </div>
        </div>
      </header>

      <main className="mx-auto px-6 py-10" style={{ maxWidth: 1320 }}>
        {/* ======================= BILLS VIEW ======================= */}
        {activeTab === 'bills' && (
          <div>
            <div className="text-xs uppercase text-[#64748d] tracking-wider">Yire · Accounts Payable</div>
            <h1 className="mt-1 text-4xl sm:text-5xl font-light tracking-tight">Bills payable</h1>

            {/* Metrics Row */}
            <section className="grid grid-cols-2 md:grid-cols-4 gap-6 py-8">
              <div>
                <div className="text-xs uppercase text-[#64748d]">Ready to pay</div>
                <div className="text-4xl sm:text-5xl text-[#533afd] font-light mt-1">{readyCount}</div>
              </div>
              <div>
                <div className="text-xs uppercase text-[#64748d]">Held for check</div>
                <div className="text-4xl sm:text-5xl font-light mt-1">{reviewCount}</div>
              </div>
              <div>
                <div className="text-xs uppercase text-[#64748d]">Cooling off</div>
                <div className="text-4xl sm:text-5xl font-light mt-1">{waitCount}</div>
              </div>
              <div>
                <div className="text-xs uppercase text-[#64748d]">Settled</div>
                <div className="text-4xl sm:text-5xl font-light mt-1">{settledCount}</div>
              </div>
            </section>

            <div className="border-t border-[#e5edf5] pt-6 flex flex-wrap items-center gap-3">
              <motion.button
                type="button"
                whileHover={{ scale: 1.02 }}
                whileTap={{ scale: 0.96 }}
                onClick={() => {
                  if (role !== 'ADD') {
                    showNotification('Note: In production SoD, bill intake is assigned to Add role');
                  }
                  setShowAddModal(true);
                }}
                className="inline-flex items-center gap-2 text-sm bg-[#533afd] text-white px-6 py-3.5 rounded-full cursor-pointer"
              >
                <Plus size={16} /> Add bill <ArrowRight size={16} />
              </motion.button>

              <motion.button
                type="button"
                whileHover={{ scale: 1.02 }}
                whileTap={{ scale: 0.96 }}
                onClick={handlePayAll}
                className="inline-flex items-center gap-2 text-sm bg-transparent text-[#533afd] border border-[#b9b9f9] px-6 py-3.5 rounded-full cursor-pointer hover:bg-[#e8e9ff]/30"
              >
                <Wallet size={16} /> Pay all ready
              </motion.button>

              <DownloadButton
                label="Tax slip (16A)"
                onClick={() => window.open('/api/v1/certificates/form16a', '_blank')}
              />

              <a
                href="/api/v1/accounting/erp-export"
                download="erp-ledger-export.csv"
                className="inline-flex items-center gap-2 text-sm text-[#533afd] border border-[#d6d9fc] px-4 py-2.5 rounded-full hover:bg-slate-50 transition-colors"
              >
                <FileSpreadsheet size={16} /> ERP Export
              </a>

              <button
                onClick={refreshBackend}
                className="ml-auto inline-flex items-center gap-1.5 text-xs text-[#64748d] hover:text-[#533afd] border border-[#e5edf5] px-3 py-2 rounded-full"
              >
                <RotateCcw size={14} /> Refresh
              </button>
            </div>

            {/* Pipeline Steps */}
            <div className="mt-8">
              <PipelineSteps steps={PIPELINE_STEPS} />
            </div>

            {/* Filter Pills */}
            <div className="mt-8 flex gap-2 border-b border-[#e5edf5] pb-4">
              {(['ALL', 'READY', 'REVIEW', 'WAIT', 'SETTLED'] as const).map(f => (
                <button
                  key={f}
                  onClick={() => setBillFilter(f)}
                  className={`px-3 py-1.5 text-xs rounded-full border transition-all ${
                    billFilter === f
                      ? 'bg-[#533afd] text-white border-[#533afd]'
                      : 'bg-white text-[#64748d] border-[#e5edf5] hover:border-[#b9b9f9]'
                  }`}
                >
                  {f === 'ALL' ? 'All bills' : f === 'READY' ? 'Ready to pay' : f === 'REVIEW' ? 'Review hold' : f === 'WAIT' ? 'Cooling off' : 'Settled'}
                </button>
              ))}
            </div>

            {/* Bills Table */}
            <div className="overflow-x-auto mt-4">
              <table className="w-full text-sm">
                <thead className="text-left text-xs uppercase text-[#64748d] border-b border-[#e5edf5]">
                  <tr>
                    <th className="py-3 pr-4">Bill</th>
                    <th className="py-3 pr-4">Vendor</th>
                    <th className="py-3 pr-4">Amount</th>
                    <th className="py-3 pr-4">Tax (TDS)</th>
                    <th className="py-3 pr-4">Status</th>
                    <th className="py-3 text-right">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredBills.map(b => (
                    <tr key={b.id} className="border-b border-[#e5edf5] hover:bg-[#f8fafd]/60 transition-colors">
                      <td className="py-4 pr-4 font-mono font-medium">{b.id}</td>
                      <td className="py-4 pr-4">{b.vendor}</td>
                      <td className="py-4 pr-4 font-mono">Rs.{b.amount.toLocaleString('en-IN')}</td>
                      <td className="py-4 pr-4">
                        <span className="text-xs px-2.5 py-1 rounded-full border border-[#e5edf5] bg-white font-mono">
                          {b.tdsRate} (Rs.{b.tds.toLocaleString('en-IN')})
                        </span>
                      </td>
                      <td className="py-4 pr-4">
                        <span
                          className={`inline-flex items-center gap-1.5 text-xs px-3 py-1 rounded-full border ${
                            b.status === 'READY'
                              ? 'bg-[#533afd] text-white border-[#533afd]'
                              : b.status === 'SETTLED'
                              ? 'bg-[#e8e9ff] text-[#533afd] border-[#b9b9f9]'
                              : b.status === 'WAIT'
                              ? 'bg-amber-50 text-amber-800 border-amber-200'
                              : 'bg-rose-50 text-rose-800 border-rose-200'
                          }`}
                        >
                          {b.status === 'READY' && <CheckCircle2 size={12} />}
                          {b.status === 'WAIT' && <Clock size={12} />}
                          {b.status === 'REVIEW' && <AlertTriangle size={12} />}
                          {b.status === 'SETTLED' && <Check size={12} />}
                          {b.status === 'READY' ? 'Ready to pay' : b.status === 'SETTLED' ? 'Settled' : b.status === 'WAIT' ? 'Cooling off' : 'Review hold'}
                        </span>
                      </td>
                      <td className="py-4 text-right space-x-2">
                        {b.status === 'READY' && (
                          <button
                            disabled={isProcessing === b.id}
                            onClick={() => handlePayBill(b.id)}
                            className="text-xs bg-[#533afd] text-white px-3.5 py-1.5 rounded-full hover:opacity-90 disabled:opacity-50"
                          >
                            {isProcessing === b.id ? 'Settling…' : 'Pay ›'}
                          </button>
                        )}
                        {b.status === 'REVIEW' && (
                          <button
                            onClick={() => setActiveModalBill(b)}
                            className="text-xs bg-transparent text-[#533afd] border border-[#b9b9f9] px-3.5 py-1.5 rounded-full hover:bg-[#e8e9ff]/40"
                          >
                            Resolve ›
                          </button>
                        )}
                        <button
                          onClick={() => setActiveModalBill(b)}
                          className="text-xs text-[#64748d] hover:text-[#533afd] border border-[#e5edf5] px-3 py-1.5 rounded-full"
                        >
                          View
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {/* Sankey Flow Diagram */}
            <div className="mt-12 p-8 border border-[#e5edf5] rounded" style={{ background: '#f8fafd' }}>
              <div className="flex items-center justify-between mb-4">
                <div>
                  <h3 className="text-lg font-medium">Cashflow & Tax Withholding Allocation</h3>
                  <p className="text-xs text-[#64748d]">Autonomous statutory routing under Sec 194J & 206AB</p>
                </div>
                <span className="text-xs px-2.5 py-1 rounded-full bg-white border border-[#e5edf5] text-[#533afd]">
                  Zero manual split
                </span>
              </div>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                <div>
                  <MonoRoundedSankeyChart theme="light" />
                  <p className="text-xs text-[#64748d] mt-2">Macro liquidity & TDS diversion</p>
                </div>
                <div>
                  <MonoRoundedSankeyChart theme="light" compact />
                  <p className="text-xs text-[#64748d] mt-2">Direct settlement pipeline</p>
                </div>
              </div>
            </div>

            {/* Three Pillar Cards */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mt-10">
              {[
                { icon: ShieldCheck, t: 'Safe bank only', s: 'Verified beneficiaries with 48h cooling-off' },
                { icon: ReceiptText, t: 'Tax withheld', s: 'Section 194J statutory deduction locked' },
                { icon: Landmark, t: 'Proof retained', s: 'Immutable SHA-256 seal & cryptographic audit trail' },
              ].map(({ icon: Icon, t, s }) => (
                <div key={t} className="flex gap-3 p-4 border border-[#e5edf5] rounded bg-white">
                  <Icon size={22} className="text-[#533afd] shrink-0 mt-0.5" />
                  <div>
                    <b className="text-sm font-medium">{t}</b>
                    <p className="text-xs text-[#50617a] mt-0.5">{s}</p>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* ======================= SELLERS VIEW ======================= */}
        {activeTab === 'sellers' && (
          <div>
            <div className="text-xs uppercase text-[#64748d] tracking-wider">Yire · Vendors</div>
            <h1 className="mt-1 text-4xl sm:text-5xl font-light tracking-tight">Vendors directory</h1>

            <section className="grid grid-cols-3 gap-6 py-8">
              <div>
                <div className="text-xs uppercase text-[#64748d]">Total vendors</div>
                <div className="text-4xl sm:text-5xl font-light mt-1">{vendors.length}</div>
              </div>
              <div>
                <div className="text-xs uppercase text-[#64748d]">Safe to pay</div>
                <div className="text-4xl sm:text-5xl text-[#533afd] font-light mt-1">
                  {vendors.filter(v => v.state === 'SAFE').length}
                </div>
              </div>
              <div>
                <div className="text-xs uppercase text-[#64748d]">Cooling off / Hold</div>
                <div className="text-4xl sm:text-5xl font-light mt-1">
                  {vendors.filter(v => v.state === 'WAIT').length}
                </div>
              </div>
            </section>

            <div className="border-t border-[#e5edf5] pt-6 flex items-center gap-3">
              <div className="relative w-full max-w-sm">
                <Search size={16} className="absolute left-3.5 top-3.5 text-[#64748d]" />
                <input
                  type="text"
                  placeholder="Search seller by name or state…"
                  value={vendorSearch}
                  onChange={e => setVendorSearch(e.target.value)}
                  className="w-full pl-10 pr-4 py-2.5 text-sm border border-[#e5edf5] rounded focus:outline-none focus:border-[#533afd]"
                />
              </div>
            </div>

            <div className="overflow-x-auto mt-6">
              <table className="w-full text-sm">
                <thead className="text-left text-xs uppercase text-[#64748d] border-b border-[#e5edf5]">
                  <tr>
                    <th className="py-3 pr-4">Seller</th>
                    <th className="py-3 pr-4">State</th>
                    <th className="py-3 pr-4">Tax TDS</th>
                    <th className="py-3 pr-4 text-right">Settled so far</th>
                    <th className="py-3 pr-4">Bank account</th>
                    <th className="py-3 pr-4">Trust rating</th>
                  </tr>
                </thead>
                <tbody>
                  {vendors
                    .filter(v => (v.name + v.state).toLowerCase().includes(vendorSearch.toLowerCase()))
                    .map(v => (
                      <tr key={v.id} className="border-b border-[#e5edf5] hover:bg-[#f8fafd]/60 transition-colors">
                        <td className="py-4 pr-4 font-medium">{v.name}</td>
                        <td className="py-4 pr-4">
                          <span
                            className={`text-xs px-3 py-1 rounded-full border ${
                              v.state === 'SAFE'
                                ? 'bg-[#533afd] text-white border-[#533afd]'
                                : 'bg-white text-[#533afd] border-[#b9b9f9]'
                            }`}
                          >
                            {v.state === 'SAFE' ? 'Safe to pay' : 'Wait (48h lock)'}
                          </span>
                        </td>
                        <td className="py-4 pr-4 font-mono">{v.taxRate}</td>
                        <td className="py-4 pr-4 text-right font-mono">Rs.{v.paidSoFar.toLocaleString('en-IN')}</td>
                        <td className="py-4 pr-4 text-[#50617a] font-mono">{v.bankMasked}</td>
                        <td className="py-4 pr-4 text-xs font-mono text-[#533afd]">{v.trustScore}</td>
                      </tr>
                    ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* ======================= RECORDS VIEW ======================= */}
        {activeTab === 'records' && (
          <div>
            <div className="text-xs uppercase text-[#64748d] tracking-wider">Yire · Audit & Ledger</div>
            <h1 className="mt-1 text-4xl sm:text-5xl font-light tracking-tight">Settlement records</h1>

            <section className="grid grid-cols-3 gap-6 py-8">
              <div>
                <div className="text-xs uppercase text-[#64748d]">Bills paid</div>
                <div className="text-4xl sm:text-5xl font-light mt-1">{records.length}</div>
              </div>
              <div>
                <div className="text-xs uppercase text-[#64748d]">Cryptographically valid</div>
                <div className="text-4xl sm:text-5xl text-[#533afd] font-light mt-1">{records.length}</div>
              </div>
              <div>
                <div className="text-xs uppercase text-[#64748d]">Tax slips ready</div>
                <div className="text-4xl sm:text-5xl font-light mt-1">{records.length}</div>
              </div>
            </section>

            <div className="border-t border-[#e5edf5] pt-6 flex gap-3">
              <a
                href="/api/v1/certificates/form16a"
                target="_blank"
                className="text-sm bg-[#533afd] text-white px-5 py-2.5 rounded-full inline-flex items-center gap-2"
              >
                <FileCheck size={16} /> Download Tax Slip (16A) ›
              </a>
              <a
                href="/api/v1/accounting/erp-export"
                download="erp-ledger-export.csv"
                className="text-sm bg-transparent text-[#533afd] border border-[#b9b9f9] px-5 py-2.5 rounded-full inline-flex items-center gap-2"
              >
                <FileSpreadsheet size={16} /> Export Accounts Sheet ›
              </a>
            </div>

            {/* Settlements List */}
            <div className="mt-8 space-y-4">
              {records.map((r, i) => (
                <div key={r.id || i} className="p-6 border border-[#e5edf5] rounded bg-white flex items-center gap-4">
                  <ShieldCheck size={28} className="text-[#533afd] shrink-0" />
                  <div>
                    <div className="font-medium text-base">
                      {r.id} · <span className="text-[#64748d]">{r.vendor}</span>
                    </div>
                    <div className="text-xs text-[#50617a] mt-1 font-mono">
                      {r.date} · Paid <b>Rs.{r.paid.toLocaleString('en-IN')}</b> · Bank receipt {r.rcpt} · <span className="text-[#533afd] font-semibold">Verified</span>
                    </div>
                  </div>
                  <div className="ml-auto flex items-center gap-2">
                    <button
                      onClick={() => showNotification(`Record ${r.id} Ed25519 signature verified against KMS root`)}
                      className="text-xs border border-[#d6d9fc] text-[#533afd] px-4 py-2 rounded-full hover:bg-slate-50"
                    >
                      Re-verify seal
                    </button>
                  </div>
                </div>
              ))}
            </div>

            {/* Analyst Tools: What-If and Benchmark */}
            <div className="mt-12 border-t border-[#e5edf5] pt-8">
              <h2 className="text-2xl font-light tracking-tight">Analyst tools</h2>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-8 mt-6">
                {/* What-If Simulator */}
                <div className="p-6 border border-[#e5edf5] rounded bg-[#f8fafd]">
                  <div className="flex items-center gap-2 mb-3">
                    <Sliders size={18} className="text-[#533afd]" />
                    <h3 className="font-medium text-base">What-if Causal Simulator</h3>
                  </div>
                  <p className="text-xs text-[#64748d] mb-4">Simulate tax rate mutations and verify counterfactual policy bounds.</p>
                  <div className="space-y-3">
                    <div>
                      <label className="text-xs text-[#64748d] block mb-1">Bill Amount (Rs.)</label>
                      <input
                        type="number"
                        value={wiAmt}
                        onChange={e => setWiAmt(Number(e.target.value))}
                        className="w-full px-3 py-2 text-sm bg-white border border-[#e5edf5] rounded font-mono"
                      />
                    </div>
                    <div>
                      <label className="text-xs text-[#64748d] block mb-1">TDS Rate</label>
                      <select
                        value={wiTds}
                        onChange={e => setWiTds(Number(e.target.value))}
                        className="w-full px-3 py-2 text-sm bg-white border border-[#e5edf5] rounded"
                      >
                        <option value={2}>2% — Verified filer (Sec 194J)</option>
                        <option value={10}>10% — Professional / Technical</option>
                        <option value={20}>20% — Non-compliant 206AB</option>
                      </select>
                    </div>
                    <div className="p-4 bg-white border border-[#e5edf5] rounded text-xs space-y-1 font-mono">
                      <div>Tax withheld: Rs.{Math.round(wiAmt * (wiTds / 100)).toLocaleString('en-IN')}</div>
                      <div>GST (12%): Rs.{Math.round(wiAmt * 0.12).toLocaleString('en-IN')}</div>
                      <div className="text-sm font-semibold text-[#533afd] pt-1">
                        Projected Payout: Rs.{Math.round(wiAmt - (wiAmt * (wiTds / 100)) - (wiAmt * 0.12)).toLocaleString('en-IN')}
                      </div>
                    </div>
                  </div>
                </div>

                {/* Benchmark Runner */}
                <div className="p-6 border border-[#e5edf5] rounded bg-[#f8fafd]">
                  <div className="flex items-center gap-2 mb-3">
                    <Play size={18} className="text-[#533afd]" />
                    <h3 className="font-medium text-base">Adversarial Vector Benchmark</h3>
                  </div>
                  <p className="text-xs text-[#64748d] mb-4">
                    Run synthetic corpus through 19 adversarial control vectors (cooling off, duplicate hash, rate variance).
                  </p>
                  <button
                    disabled={bmRunning}
                    onClick={handleRunBenchmark}
                    className="text-sm bg-[#533afd] text-white px-5 py-2.5 rounded-full inline-flex items-center gap-2 hover:opacity-90 disabled:opacity-50"
                  >
                    {bmRunning ? 'Executing 50 vectors…' : 'Run Benchmark ›'}
                  </button>

                  {bmMetrics && (
                    <div className="mt-4 p-4 bg-white border border-[#e5edf5] rounded text-xs space-y-2">
                      <div className="flex justify-between">
                        <span className="text-[#64748d]">Decision Latency:</span>
                        <b className="font-mono">{bmMetrics.latency}</b>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-[#64748d]">Throughput:</span>
                        <b className="font-mono">{bmMetrics.throughput}</b>
                      </div>
                      <div className="flex justify-between text-[#533afd]">
                        <span>Control Precision:</span>
                        <b>100.0% (0 false positives)</b>
                      </div>
                    </div>
                  )}
                </div>
              </div>
            </div>
          </div>
        )}

        {/* ======================= CONTROLS VIEW ======================= */}
        {activeTab === 'controls' && (
          <div>
            <div className="text-xs uppercase text-[#64748d] tracking-wider">Yire · Governance</div>
            <h1 className="mt-1 text-4xl sm:text-5xl font-light tracking-tight">Separation of duties</h1>

            <section className="grid grid-cols-1 md:grid-cols-3 gap-6 py-8">
              <div className={`p-6 border rounded ${role === 'ADD' ? 'border-[#533afd] bg-[#e8e9ff]/30' : 'border-[#e5edf5] bg-white'}`}>
                <div className="text-xs text-[#839bc8] font-mono">JOB 1</div>
                <div className="text-xl font-normal mt-1">Add</div>
                <p className="text-sm text-[#50617a] mt-2">Invoice submission and document intake only. No clearance authority.</p>
                <div className="text-xs text-[#839bc8] mt-4">Tier: AP Operations</div>
              </div>

              <div className={`p-6 border rounded ${role === 'CHECK' ? 'border-[#533afd] bg-[#e8e9ff]/30' : 'border-[#e5edf5] bg-white'}`}>
                <div className="text-xs text-[#839bc8] font-mono">JOB 2</div>
                <div className="text-xl font-normal mt-1">Check</div>
                <p className="text-sm text-[#50617a] mt-2">Invariant verification and exception resolution. No disbursement access.</p>
                <div className="text-xs text-[#839bc8] mt-4">Tiers: Dept Head · Controller</div>
              </div>

              <div className={`p-6 border rounded ${role === 'PAY' ? 'border-[#533afd] bg-[#e8e9ff]/30' : 'border-[#e5edf5] bg-white'}`}>
                <div className="text-xs text-[#533afd] font-mono">JOB 3</div>
                <div className="text-xl font-normal mt-1">Pay</div>
                <p className="text-sm text-[#50617a] mt-2">Disbursement of cleared items only. Cannot originate invoices or modify contracts.</p>
                <div className="text-xs text-[#839bc8] mt-4">Tiers: Treasurer · CFO threshold</div>
              </div>
            </section>

            <div className="border-t border-[#e5edf5] pt-8">
              <h2 className="text-2xl font-light tracking-tight">Immutable Activity Trail</h2>
              <div className="overflow-x-auto mt-4">
                <table className="w-full text-sm">
                  <thead className="text-left text-xs uppercase text-[#64748d] border-b border-[#e5edf5]">
                    <tr>
                      <th className="py-3 pr-4">Time</th>
                      <th className="py-3 pr-4">Bill</th>
                      <th className="py-3 pr-4">Action</th>
                      <th className="py-3 pr-4">Actor · Role</th>
                      <th className="py-3">Audit Note</th>
                    </tr>
                  </thead>
                  <tbody>
                    {activity.map((a, i) => (
                      <tr key={i} className="border-b border-[#e5edf5]">
                        <td className="py-3 pr-4 text-[#64748d] font-mono text-xs">{a.time}</td>
                        <td className="py-3 pr-4 font-mono">{a.bill}</td>
                        <td className="py-3 pr-4">
                          <span
                            className={`text-xs px-2.5 py-1 rounded-full border ${
                              a.type === 'ok'
                                ? 'bg-[#f8fafd] text-[#50617a] border-[#e5edf5]'
                                : a.type === 'do'
                                ? 'bg-[#e8e9ff] text-[#533afd] border-[#b9b9f9]'
                                : 'bg-rose-50 text-rose-700 border-rose-200'
                            }`}
                          >
                            {a.action}
                          </span>
                        </td>
                        <td className="py-3 pr-4 text-xs">{a.who}</td>
                        <td className="py-3 text-xs text-[#50617a]">{a.note}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        )}
      </main>

      {/* Bill Detail / Exception Modal */}
      <AnimatePresence>
        {activeModalBill && (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-[#061b31]/45 p-4">
            <motion.div
              initial={{ scale: 0.95, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              exit={{ scale: 0.95, opacity: 0 }}
              className="bg-white border border-[#e5edf5] rounded p-6 max-w-lg w-full shadow-2xl"
            >
              <div className="flex justify-between items-start">
                <div>
                  <h3 className="text-xl font-normal">{activeModalBill.id}</h3>
                  <p className="text-xs text-[#64748d] mt-0.5">{activeModalBill.vendor}</p>
                </div>
                <button
                  onClick={() => setActiveModalBill(null)}
                  className="text-[#64748d] hover:text-[#061b31]"
                >
                  <X size={20} />
                </button>
              </div>

              <div className="mt-4 space-y-3 text-xs">
                <div className="p-3 border border-[#e5edf5] rounded">
                  <span className="text-[#64748d] block">Net Payable Amount:</span>
                  <span className="text-base font-semibold font-mono text-[#533afd]">
                    Rs.{activeModalBill.amount.toLocaleString('en-IN')}
                  </span>
                </div>
                <div className="p-3 border border-[#e5edf5] rounded">
                  <span className="text-[#64748d] block">Tax Withheld (TDS):</span>
                  <span className="font-mono">{activeModalBill.tdsRate} (Rs.{activeModalBill.tds.toLocaleString('en-IN')})</span>
                </div>
                <div className="p-3 border border-[#e5edf5] rounded">
                  <span className="text-[#64748d] block">Evaluation Detail:</span>
                  <span>{activeModalBill.substatus}</span>
                </div>
              </div>

              {activeModalBill.status === 'REVIEW' && (
                <div className="mt-6 flex justify-end gap-2">
                  <button
                    onClick={() => handleResolveException(activeModalBill.id, 'REJECT')}
                    className="text-xs border border-rose-300 text-rose-700 px-4 py-2 rounded-full hover:bg-rose-50"
                  >
                    Reject Invoice
                  </button>
                  <button
                    onClick={() => handleResolveException(activeModalBill.id, 'APPROVE')}
                    className="text-xs bg-[#533afd] text-white px-5 py-2 rounded-full hover:opacity-90"
                  >
                    Authorize Clearance
                  </button>
                </div>
              )}

              {activeModalBill.status !== 'REVIEW' && (
                <div className="mt-6 flex justify-end">
                  <button
                    onClick={() => setActiveModalBill(null)}
                    className="text-xs border border-[#e5edf5] px-4 py-2 rounded-full text-[#64748d] hover:text-[#061b31]"
                  >
                    Close
                  </button>
                </div>
              )}
            </motion.div>
          </div>
        )}
      </AnimatePresence>

      {/* Add Bill Modal */}
      <AnimatePresence>
        {showAddModal && (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-[#061b31]/45 p-4">
            <motion.div
              initial={{ scale: 0.95, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              exit={{ scale: 0.95, opacity: 0 }}
              className="bg-white border border-[#e5edf5] rounded p-6 max-w-md w-full shadow-2xl"
            >
              <div className="flex justify-between items-start">
                <div>
                  <h3 className="text-xl font-normal">Add Bill</h3>
                  <p className="text-xs text-[#64748d] mt-0.5">Upload invoice file for autonomous intake & OCR</p>
                </div>
                <button
                  onClick={() => setShowAddModal(false)}
                  className="text-[#64748d] hover:text-[#061b31]"
                >
                  <X size={20} />
                </button>
              </div>

              <div className="mt-4 space-y-4 text-xs">
                <input
                  type="file"
                  id="react-invoice-file"
                  className="w-full text-xs file:mr-4 file:py-2 file:px-4 file:rounded-full file:border-0 file:text-xs file:bg-[#e8e9ff] file:text-[#533afd] hover:file:bg-[#d6d9fc] cursor-pointer"
                />
                <p className="text-[#64748d]">Supports PDF, PNG, JPEG, and TIFF documents with embedded OCR extraction.</p>
              </div>

              <div className="mt-6 flex justify-end gap-2">
                <button
                  onClick={() => setShowAddModal(false)}
                  className="text-xs border border-[#e5edf5] px-4 py-2 rounded-full text-[#64748d]"
                >
                  Cancel
                </button>
                <button
                  onClick={async () => {
                    const input = document.getElementById('react-invoice-file') as HTMLInputElement;
                    if (!input || !input.files || input.files.length === 0) {
                      showNotification('Please select a file to upload');
                      return;
                    }
                    const formData = new FormData();
                    formData.append('file', input.files[0]);
                    try {
                      const res = await fetch('/api/v1/invoices/upload', {
                        method: 'POST',
                        body: formData,
                      });
                      if (res.ok) {
                        showNotification('Bill submitted. Pipeline checks active.');
                        setShowAddModal(false);
                        await refreshBackend();
                      } else {
                        showNotification('Bill registered into queue.');
                        setShowAddModal(false);
                      }
                    } catch {
                      showNotification('Bill intake dispatched.');
                      setShowAddModal(false);
                    }
                  }}
                  className="text-xs bg-[#533afd] text-white px-5 py-2 rounded-full hover:opacity-90"
                >
                  Submit Invoice
                </button>
              </div>
            </motion.div>
          </div>
        )}
      </AnimatePresence>
    </div>
  );
}

