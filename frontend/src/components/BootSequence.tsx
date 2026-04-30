"use client";

import { useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";

export function BootSequence({ children }: { children: React.ReactNode }) {
  const [phase, setPhase] = useState<"booting" | "done">("booting");
  const [text, setText] = useState("");
  const target = "ZEUS";

  useEffect(() => {
    let i = 0;
    const tick = () => {
      i++;
      setText(target.slice(0, i));
      if (i < target.length) {
        setTimeout(tick, 100);
      } else {
        setTimeout(() => setPhase("done"), 700);
      }
    };
    setTimeout(tick, 200);
  }, []);

  return (
    <>
      <AnimatePresence>
        {phase === "booting" && (
          <motion.div
            key="boot"
            className="fixed inset-0 z-[200] bg-black flex flex-col items-center justify-center"
            initial={{ opacity: 1 }}
            exit={{ opacity: 0, transition: { duration: 0.4 } }}
          >
            <motion.div
              initial={{ scale: 0.95 }}
              animate={{ scale: 1 }}
              transition={{ duration: 0.6, ease: [0, 0, 0.2, 1] }}
              className="flex flex-col items-center"
            >
              <svg width="64" height="64" viewBox="0 0 32 32" fill="none">
                <defs>
                  <linearGradient id="bootGrad" x1="0" y1="0" x2="32" y2="32">
                    <stop offset="0%" stopColor="#10B981" />
                    <stop offset="100%" stopColor="#059669" />
                  </linearGradient>
                </defs>
                <motion.rect
                  x="3"
                  y="3"
                  width="26"
                  height="26"
                  rx="4"
                  stroke="url(#bootGrad)"
                  strokeWidth="1.5"
                  fill="none"
                  initial={{ pathLength: 0, opacity: 0 }}
                  animate={{ pathLength: 1, opacity: 1 }}
                  transition={{ duration: 0.6 }}
                />
                <motion.path
                  d="M9 9 L23 9 L9 23 L23 23"
                  stroke="url(#bootGrad)"
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  fill="none"
                  initial={{ pathLength: 0 }}
                  animate={{ pathLength: 1 }}
                  transition={{ duration: 0.8, delay: 0.3 }}
                />
                <motion.circle
                  cx="16"
                  cy="16"
                  r="2"
                  fill="#F97316"
                  initial={{ scale: 0 }}
                  animate={{ scale: [0, 1.4, 1] }}
                  transition={{ delay: 1.0, duration: 0.5 }}
                />
              </svg>
              <div className="mt-5 font-mono text-h1 tracking-[0.4em] text-text-primary">
                {text}
                <span className="inline-block w-[2px] h-6 bg-brand-emerald-bright ml-1 animate-heartbeat" />
              </div>
              <div className="mt-3 text-caption text-text-muted tracking-wider">
                FUTURES INTELLIGENCE PLATFORM
              </div>
              <motion.div
                className="mt-6 text-sm italic text-brand-emerald-bright tracking-wide"
                initial={{ opacity: 0, y: 6 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.9, duration: 0.6 }}
              >
                Trades are won before they begin
              </motion.div>
              <motion.div
                className="mt-8 w-48 h-px bg-border-subtle relative overflow-hidden"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                transition={{ delay: 0.4 }}
              >
                <motion.div
                  className="absolute h-full bg-brand-emerald"
                  initial={{ width: "0%" }}
                  animate={{ width: "100%" }}
                  transition={{ duration: 1.0, delay: 0.4 }}
                />
              </motion.div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
      <div style={{ opacity: phase === "done" ? 1 : 0, transition: "opacity 400ms" }}>
        {children}
      </div>
    </>
  );
}
