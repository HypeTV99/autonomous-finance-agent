import { useState } from 'react';
import { AnimatePresence, motion } from 'motion/react';
import { Check, Download } from 'lucide-react';

interface DownloadButtonProps {
  label?: string;
  onClick?: () => void;
}

// Port of Amicro item 21 "Download" (morph interaction): Download icon morphs
// into a Check icon on hover. Styled to the Yire Stripe ledger theme.
export function DownloadButton({ label = 'Download', onClick }: DownloadButtonProps) {
  const [isHovered, setIsHovered] = useState(false);

  return (
    <motion.button
      type="button"
      onClick={onClick}
      onMouseEnter={() => setIsHovered(true)}
      onMouseLeave={() => setIsHovered(false)}
      onFocus={() => setIsHovered(true)}
      onBlur={() => setIsHovered(false)}
      whileHover={{ scale: 1.02 }}
      whileTap={{ scale: 0.96 }}
      className="inline-flex items-center text-sm"
      style={{
        background: 'transparent',
        color: '#533afd',
        border: '1px solid #b9b9f9',
        borderRadius: 9999,
        padding: '14.5px 24px',
        cursor: 'pointer',
      }}
    >
      <span
        className="relative inline-flex items-center justify-center shrink-0"
        style={{ width: 16, height: 16 }}
      >
        <AnimatePresence mode="popLayout" initial={false}>
          {!isHovered ? (
            <motion.span
              key="icon1"
              initial={{ scale: 0.5, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              exit={{ scale: 0.5, opacity: 0 }}
              transition={{ type: 'spring', stiffness: 600, damping: 25 }}
              className="absolute inset-0 inline-flex items-center justify-center"
            >
              <Download size={16} />
            </motion.span>
          ) : (
            <motion.span
              key="icon2"
              initial={{ scale: 0.5, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              exit={{ scale: 0.5, opacity: 0 }}
              transition={{ type: 'spring', stiffness: 600, damping: 25 }}
              className="absolute inset-0 inline-flex items-center justify-center"
            >
              <Check size={16} />
            </motion.span>
          )}
        </AnimatePresence>
      </span>
      <span className="ml-2.5 whitespace-nowrap">{label}</span>
    </motion.button>
  );
}
