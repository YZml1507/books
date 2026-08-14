"use client";

import Link from "next/link";
import { ArrowRight, Github, ShieldCheck } from "lucide-react";
import { motion } from "framer-motion";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { siteConfig } from "@/lib/site";
import { CountUp } from "@/components/sections/count-up";

const stats = [
  { label: "本地工具", value: 12, suffix: "" },
  { label: "登录门槛", value: 0, suffix: "" },
  { label: "开源透明", value: 100, suffix: "%" },
];

export function Hero() {
  return (
    <section className="relative overflow-hidden px-4 pb-16 pt-14 sm:px-6 sm:pb-24 sm:pt-20 lg:px-8">
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.7, ease: "easeOut" }}
        className="mx-auto grid w-full max-w-7xl items-center gap-10 lg:grid-cols-[1fr_0.78fr]"
      >
        <div className="max-w-3xl">
          <Badge className="mb-6 border-primary/30 bg-primary/10 text-primary">
            <ShieldCheck className="mr-2 size-3.5" />
            全部本地计算 · 无需登录 · 永久免费
          </Badge>
          <h1 className="text-balance font-serif text-6xl font-semibold leading-[0.95] text-foreground sm:text-7xl lg:text-8xl">
            算了么
          </h1>
          <p className="mt-6 text-xl text-primary sm:text-2xl">万事皆有迹可循。</p>
          <p className="mt-5 max-w-2xl text-pretty text-base leading-8 text-muted-foreground sm:text-lg">
            一个免费、开源、现代化的东方命理工具箱。全部本地计算，无需登录，永久免费。
          </p>
          <div className="mt-8 flex flex-col gap-3 sm:flex-row">
            <Button asChild size="default" className="group h-12 px-6">
              <Link href="/tools">
                开始探索
                <ArrowRight className="size-4 transition-transform group-hover:translate-x-1" />
              </Link>
            </Button>
            <Button asChild variant="outline" size="default" className="h-12 px-6">
              <Link href={siteConfig.github} target="_blank" rel="noreferrer">
                <Github className="size-4" />
                查看 Github
              </Link>
            </Button>
          </div>
          <div className="mt-10 grid max-w-xl grid-cols-3 gap-3">
            {stats.map((stat) => (
              <div key={stat.label} className="rounded-[20px] border border-border bg-secondary/35 p-4 backdrop-blur">
                <div className="text-2xl font-semibold text-foreground">
                  <CountUp value={stat.value} suffix={stat.suffix} />
                </div>
                <div className="mt-1 text-xs text-muted-foreground">{stat.label}</div>
              </div>
            ))}
          </div>
        </div>

        <motion.div
          initial={{ opacity: 0, scale: 0.96 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ duration: 0.8, delay: 0.12, ease: "easeOut" }}
          className="glass-card relative mx-auto aspect-square w-full max-w-[460px] overflow-hidden rounded-[24px] border border-white/10 p-8"
        >
          <div className="absolute inset-0 bg-[radial-gradient(circle_at_50%_28%,rgba(201,168,106,0.18),transparent_38%),linear-gradient(145deg,rgba(245,241,232,0.08),transparent)]" />
          <div className="relative grid h-full place-items-center">
            <div className="relative grid aspect-square w-72 max-w-full place-items-center rounded-full border border-primary/30">
              <div className="absolute inset-8 rounded-full border border-primary/20" />
              <div className="absolute inset-16 rounded-full border border-primary/15" />
              {["乾", "兑", "离", "震", "巽", "坎", "艮", "坤"].map((item, index) => (
                <span
                  key={item}
                  className="absolute font-serif text-lg text-primary/65"
                  style={{
                    transform: `rotate(${index * 45}deg) translateY(-132px) rotate(-${index * 45}deg)`,
                  }}
                >
                  {item}
                </span>
              ))}
              <motion.div
                animate={{ rotate: 360 }}
                transition={{ duration: 28, ease: "linear", repeat: Infinity }}
                className="grid size-32 place-items-center rounded-full border border-primary/35 bg-background/45 text-7xl text-primary shadow-gold backdrop-blur-xl"
              >
                ☯
              </motion.div>
            </div>
          </div>
        </motion.div>
      </motion.div>
    </section>
  );
}
