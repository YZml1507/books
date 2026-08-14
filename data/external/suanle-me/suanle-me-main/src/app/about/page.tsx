import type { Metadata } from "next";
import Link from "next/link";
import { Github, HeartHandshake, Lock, Sparkles } from "lucide-react";
import { Button } from "@/components/ui/button";
import { GlassCard } from "@/components/ui/glass-card";
import { SectionHeading } from "@/components/ui/section-heading";
import { siteConfig } from "@/lib/site";

export const metadata: Metadata = {
  title: "关于",
  description: "了解免费开源东方命理工具箱算了么。",
};

const values = [
  { title: "不收费", body: "核心体验免费开放，不做付费墙。", icon: Sparkles },
  { title: "不开会员", body: "不制造等级体系，也不诱导续费。", icon: HeartHandshake },
  { title: "不开广告", body: "界面保持干净，把注意力还给工具本身。", icon: Lock },
];

export default function AboutPage() {
  return (
    <main className="px-4 py-12 sm:px-6 sm:py-16 lg:px-8">
      <div className="mx-auto w-full max-w-7xl">
        <SectionHeading
          eyebrow="关于算了么"
          title="免费、开源、克制的东方命理工具集合"
          description="旨在以现代设计重新呈现传统文化，让复杂工具变得安静、清晰、可使用。"
        />

        <div className="grid gap-5 lg:grid-cols-[0.85fr_1.15fr]">
          <GlassCard interactive={false} className="grid min-h-[360px] place-items-center p-8">
            <div className="text-center">
              <div className="mx-auto grid size-40 place-items-center rounded-full border border-primary/30 bg-primary/10 font-serif text-8xl text-primary">
                ☯
              </div>
              <p className="mt-6 text-sm leading-7 text-muted-foreground">
                东方玄学不是焦虑生意。它可以是一种观察时间、关系与选择的文化语言。
              </p>
            </div>
          </GlassCard>
          <GlassCard interactive={false} className="p-7 sm:p-10">
            <div className="space-y-5 text-base leading-8 text-muted-foreground">
              <p>「算了么」是一个免费的东方命理工具集合。</p>
              <p>
                它不做论坛，不做博客，也不把传统文化包装成高压销售。我们希望它更像 Apple、Notion
                和小宇宙式的现代应用：打开即用，视觉克制，信息清楚。
              </p>
              <p>不收费。不卖课。不开会员。不开广告。所有输入默认留在本地。</p>
            </div>
            <Button asChild className="mt-8">
              <Link href={siteConfig.github} target="_blank" rel="noreferrer">
                <Github className="size-4" />
                查看源码
              </Link>
            </Button>
          </GlassCard>
        </div>

        <div className="mt-5 grid gap-5 md:grid-cols-3">
          {values.map((value) => {
            const Icon = value.icon;
            return (
              <GlassCard key={value.title} className="p-6">
                <div className="mb-5 grid size-11 place-items-center rounded-2xl bg-primary/10 text-primary">
                  <Icon className="size-5" />
                </div>
                <h2 className="text-lg font-semibold text-foreground">{value.title}</h2>
                <p className="mt-3 text-sm leading-7 text-muted-foreground">{value.body}</p>
              </GlassCard>
            );
          })}
        </div>
      </div>
    </main>
  );
}
