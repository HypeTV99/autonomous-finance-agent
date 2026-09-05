import { motion } from 'motion/react';
import {
  ArrowRight,
  Landmark,
  Plus,
  ReceiptText,
  ShieldCheck,
  Wallet,
} from 'lucide-react';
import { MonoRoundedSankeyChart } from './components/amicro/MonoRoundedSankeyChart';
import { DownloadButton } from './components/amicro/DownloadButton';
import { PipelineSteps } from './components/PipelineSteps';

const STEPS = [
  { n: 'Step 1', t: 'Add bill', s: 'Single registration' },
  { n: 'Step 2', t: 'Check bill', s: 'Review and disposition' },
  { n: 'Step 3', t: 'Tax + hold', s: 'Automatic tax split' },
  { n: 'Step 4', t: 'Pay + record', s: 'Settlement and ledger entry' },
];

function App() {
  return (
    <div className="min-h-screen bg-white text-[#061b31]">
      <header
        className="sticky top-0 z-40 bg-white"
        style={{ borderBottom: '1px solid #e5edf5', height: 76 }}
      >
        <div
          className="mx-auto px-6 flex items-center gap-3"
          style={{ maxWidth: 1320, height: 76 }}
        >
          <span className="font-bold" style={{ fontSize: 18 }}>
            Yire
          </span>
          <span className="text-xs" style={{ color: '#64748d' }}>
            Bills flow
          </span>
        </div>
      </header>

      <main className="mx-auto px-6 py-10" style={{ maxWidth: 1320 }}>
        <div
          className="text-xs uppercase"
          style={{ color: '#64748d', letterSpacing: '.5px' }}
        >
          Yire · Bills
        </div>
        <h1
          className="mt-2"
          style={{
            fontSize: 40,
            lineHeight: 1.05,
            letterSpacing: '-0.8px',
            fontWeight: 300,
          }}
        >
          Bills payable
        </h1>

        <div className="mt-6 flex gap-2">
          <motion.button
            type="button"
            whileHover={{ scale: 1.02 }}
            whileTap={{ scale: 0.96 }}
            className="inline-flex items-center gap-2 text-sm"
            style={{
              background: '#533afd',
              color: '#fff',
              borderRadius: 9999,
              padding: '14.5px 24px',
            }}
          >
            <Plus size={16} /> Add bill <ArrowRight size={16} />
          </motion.button>
          <motion.button
            type="button"
            whileHover={{ scale: 1.02 }}
            whileTap={{ scale: 0.96 }}
            className="inline-flex items-center gap-2 text-sm"
            style={{
              background: 'transparent',
              color: '#533afd',
              border: '1px solid #b9b9f9',
              borderRadius: 9999,
              padding: '14.5px 24px',
            }}
          >
            <Wallet size={16} /> Pay all ready
          </motion.button>
          <DownloadButton label="Download tax slip" />
        </div>

        <div className="mt-10">
          <PipelineSteps steps={STEPS} />
        </div>

        <div
          className="grid grid-cols-2 gap-6 mt-10 p-8"
          style={{ background: '#f8fafd', borderRadius: 4 }}
        >
          <div>
            <MonoRoundedSankeyChart theme="light" />
            <p className="text-sm mt-3" style={{ color: '#50617a' }}>
              Full size
            </p>
          </div>
          <div>
            <MonoRoundedSankeyChart theme="light" compact />
            <p className="text-sm mt-3" style={{ color: '#50617a' }}>
              Compact
            </p>
          </div>
        </div>

        <div className="grid grid-cols-3 gap-6 mt-10">
          {[
            { icon: ShieldCheck, t: 'Safe bank only', s: 'Verified beneficiaries' },
            { icon: ReceiptText, t: 'Tax withheld', s: 'Statutory deduction applied' },
            { icon: Landmark, t: 'Proof retained', s: 'Immutable settlement record' },
          ].map(({ icon: Icon, t, s }) => (
            <div key={t} className="flex gap-2">
              <Icon size={20} color="#533afd" />
              <span>
                <b>{t}</b>
                <br />
                <span className="text-sm" style={{ color: '#50617a' }}>
                  {s}
                </span>
              </span>
            </div>
          ))}
        </div>
      </main>
    </div>
  );
}

export default App;
