"use client";

import { RefreshCcw } from "lucide-react";
import { AnimatePresence, motion } from "framer-motion";
import { useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
import { GlassCard } from "@/components/ui/glass-card";
import { quotes } from "@/lib/constants";

export function QuoteCard() {
  const initial = useMemo(() => Math.floor(new Date().getHours() / 6) % quotes.length, []);
  const [index, setIndex] = useState(initial);

  return (
    <section className="px-4 py-16 sm:px-6 sm:py-24 lg:px-8">
      <div className="mx-auto w-full max-w-4xl">
        <GlassCard interactive={false} className="relative overflow-hidden p-8 text-center sm:p-12">
          <div className="absolute inset-x-10 top-0 h-px bg-gradient-to-r from-transparent via-primary/50 to-transparent" />
          <p className="mb-4 text-sm text-primary">时间签文</p>
          <AnimatePresence mode="wait">
            <motion.blockquote
              key={quotes[index].text}
              initial={{ opacity: 0, y: 12, filter: "blur(4px)" }}
              animate={{ opacity: 1, y: 0, filter: "blur(0px)" }}
              exit={{ opacity: 0, y: -12, filter: "blur(4px)" }}
              transition={{ duration: 0.32 }}
              className="text-balance font-serif text-3xl font-semibold text-foreground sm:text-5xl"
            >
              {quotes[index].text}
            </motion.blockquote>
          </AnimatePresence>
          <Button
            className="mt-8"
            variant="outline"
            onClick={() => setIndex((value) => (value + 1) % quotes.length)}
          >
            <RefreshCcw className="size-4" />
            换一句
          </Button>
        </GlassCard>
      </div>
    </section>
  );
}
