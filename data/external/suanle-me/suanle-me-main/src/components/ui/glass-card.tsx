"use client";

import { motion } from "framer-motion";
import type { HTMLMotionProps } from "framer-motion";
import { cn } from "@/lib/utils";

type GlassCardProps = HTMLMotionProps<"div"> & {
  interactive?: boolean;
};

export function GlassCard({ className, interactive = true, children, ...props }: GlassCardProps) {
  return (
    <motion.div
      whileHover={interactive ? { y: -6, scale: 1.01 } : undefined}
      transition={{ type: "spring", stiffness: 240, damping: 24 }}
      className={cn(
        "glass-card rounded-[24px] border border-white/10 p-5 shadow-glass backdrop-blur-2xl",
        interactive && "hover:border-primary/35 hover:shadow-gold",
        className,
      )}
      {...props}
    >
      {children}
    </motion.div>
  );
}
