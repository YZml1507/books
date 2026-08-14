"use client";

import Link from "next/link";
import type { LucideIcon } from "lucide-react";
import {
  ArrowRight,
  BookOpen,
  Brain,
  CalendarDays,
  Coins,
  Compass,
  Flame,
  Layers3,
  Moon,
  Orbit,
  PenLine,
  Sparkles,
  SunMedium,
} from "lucide-react";
import { motion } from "framer-motion";
import { Button } from "@/components/ui/button";
import { GlassCard } from "@/components/ui/glass-card";
import { SectionHeading } from "@/components/ui/section-heading";
import { fortuneTools } from "@/lib/constants";
import type { IconName } from "@/types";

const iconMap: Record<IconName, LucideIcon> = {
  orbit: Orbit,
  calendar: CalendarDays,
  sparkles: Sparkles,
  compass: Compass,
  coins: Coins,
  cards: Layers3,
  moon: Moon,
  sun: SunMedium,
  book: BookOpen,
  signature: PenLine,
  flame: Flame,
  brain: Brain,
};

export function ToolIcon({ name, className }: { name: IconName; className?: string }) {
  const Icon = iconMap[name];
  return <Icon className={className} aria-hidden="true" />;
}

export function FeatureGrid() {
  return (
    <section id="features" className="px-4 py-16 sm:px-6 sm:py-24 lg:px-8">
      <div className="mx-auto w-full max-w-7xl">
        <SectionHeading
          eyebrow="命理工具"
          title="把传统文化装进现代界面"
          description="十二个常用工具覆盖排盘、卜筮、日用查询与结构化分析。每一次输入都只在你的设备里计算。"
        />
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {fortuneTools.map((tool, index) => (
            <GlassCard
              key={tool.slug}
              initial={{ opacity: 0, y: 16 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true, margin: "-60px" }}
              transition={{ duration: 0.45, delay: index * 0.03 }}
              className="group flex min-h-[260px] flex-col"
            >
              <div
                className="mb-6 grid size-12 place-items-center rounded-2xl border border-white/10 bg-secondary text-primary"
                style={{ color: tool.accent }}
              >
                <ToolIcon name={tool.icon} className="size-5" />
              </div>
              <div className="mb-5 flex-1">
                <div className="flex items-center gap-2">
                  <h3 className="text-xl font-semibold text-foreground">{tool.title}</h3>
                  <span className="rounded-full border border-border px-2 py-0.5 text-[11px] text-muted-foreground">
                    {tool.category}
                  </span>
                </div>
                <p className="mt-3 text-sm leading-7 text-muted-foreground">{tool.intro}</p>
                <p className="mt-3 text-sm leading-7 text-muted-foreground/90">{tool.description}</p>
              </div>
              <Button asChild variant="ghost" size="sm" className="w-fit px-0 text-primary hover:bg-transparent">
                <Link href={`/tools/${tool.slug}`}>
                  进入
                  <motion.span className="inline-flex" whileHover={{ x: 4 }}>
                    <ArrowRight className="size-4" />
                  </motion.span>
                </Link>
              </Button>
            </GlassCard>
          ))}
        </div>
      </div>
    </section>
  );
}
