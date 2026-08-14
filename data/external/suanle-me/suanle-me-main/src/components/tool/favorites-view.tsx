"use client";

import Link from "next/link";
import { ArrowRight, Heart } from "lucide-react";
import { Button } from "@/components/ui/button";
import { GlassCard } from "@/components/ui/glass-card";
import { ToolIcon } from "@/components/sections/feature-grid";
import { fortuneTools } from "@/lib/constants";
import { useAppStore } from "@/lib/store";

export function FavoritesView() {
  const favorites = useAppStore((state) => state.favorites);
  const tools = fortuneTools.filter((tool) => favorites.includes(tool.slug));

  if (tools.length === 0) {
    return (
      <GlassCard interactive={false} className="mx-auto max-w-2xl p-8 text-center">
        <Heart className="mx-auto mb-4 size-9 text-primary" />
        <h1 className="text-2xl font-semibold text-foreground">还没有收藏</h1>
        <p className="mt-3 text-sm leading-7 text-muted-foreground">在任意工具页点击心形按钮，即可把常用工具留在这里。</p>
        <Button asChild className="mt-6">
          <Link href="/tools">去工具箱</Link>
        </Button>
      </GlassCard>
    );
  }

  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
      {tools.map((tool) => (
        <GlassCard key={tool.slug} className="flex min-h-[220px] flex-col">
          <div className="mb-5 grid size-12 place-items-center rounded-2xl bg-primary/10 text-primary">
            <ToolIcon name={tool.icon} className="size-5" />
          </div>
          <div className="flex-1">
            <h2 className="text-xl font-semibold text-foreground">{tool.title}</h2>
            <p className="mt-3 text-sm leading-7 text-muted-foreground">{tool.description}</p>
          </div>
          <Button asChild variant="outline" className="mt-6">
            <Link href={`/tools/${tool.slug}`}>
              打开
              <ArrowRight className="size-4" />
            </Link>
          </Button>
        </GlassCard>
      ))}
    </div>
  );
}
