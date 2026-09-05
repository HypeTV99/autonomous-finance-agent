import { useState } from 'react';
import { motion } from 'motion/react';

interface Step {
  t: string;
  s: string;
}

// Port of Amicro's SegmentedStepBar (discrete multi-segment indicator):
// clickable segments that fill up to the active step, spring-animated.
export function PipelineSteps({ steps }: { steps: Step[] }) {
  const [active, setActive] = useState(1);

  return (
    <div>
      <div className="flex items-center gap-1.5" aria-label="Pipeline position">
        {steps.map((s, i) => (
          <button
            key={s.t}
            onClick={() => setActive(i)}
            aria-label={s.t}
            className="flex-1 cursor-pointer border-0 bg-transparent p-0"
          >
            <motion.div
              animate={{
                backgroundColor: i <= active ? '#533afd' : '#e5edf5',
              }}
              transition={{ type: 'spring', bounce: 0.25, duration: 0.35 }}
              className="h-2 w-full rounded-full"
            />
          </button>
        ))}
      </div>
      <div
        className="grid mt-3 gap-6"
        style={{ gridTemplateColumns: `repeat(${steps.length}, 1fr)` }}
      >
        {steps.map((s, i) => (
          <button
            key={s.t}
            onClick={() => setActive(i)}
            className="text-left cursor-pointer border-0 bg-transparent p-0"
          >
            <div
              style={{
                fontSize: 15,
                color: i <= active ? '#061b31' : '#64748d',
              }}
            >
              {s.t}
            </div>
            <div className="text-xs" style={{ color: '#64748d' }}>
              {s.s}
            </div>
          </button>
        ))}
      </div>
      <div className="text-xs mt-2" style={{ color: '#64748d' }}>
        Step {active + 1} of {steps.length}
      </div>
    </div>
  );
}
