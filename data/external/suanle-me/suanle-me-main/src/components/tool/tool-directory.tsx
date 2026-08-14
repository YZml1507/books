"use client";

import Link from "next/link";
import { ArrowRight, Search } from "lucide-react";
import { useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { GlassCard } from "@/components/ui/glass-card";
import { ToolIcon } from "@/components/sections/feature-grid";
import { fortuneTools } from "@/lib/constants";

const categories = ["全部", "命盘", "卜筮", "日用", "分析"] as const;

export function ToolDirectory() {
  const [keyword, setKeyword] = useState("");
  const [category, setCategory] = useState<(typeof categories)[number]>("全部");

  const filtered = useMemo(() => {
    return fortuneTools.filter((tool) => {
      const matchesKeyword = `${tool.title}${tool.intro}${tool.description}`.includes(keyword.trim());
      const matchesCategory = category === "全部" || tool.category === category;
      return matchesKeyword && matchesCategory;
    });
  }, [category, keyword]);

  return (
    <div className="grid gap-6">
      <GlassCard interactive={false} className="p-4">
        <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
          <label className="relative flex-1">
            <Search className="pointer-events-none absolute left-4 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
            <input
              value={keyword}
              onChange={(event) => setKeyword(event.target.value)}
              placeholder="搜索工具"
              className="h-12 w-full rounded-full border border-border bg-background/35 pl-11 pr-4 text-sm text-foreground outline-none transition focus:border-primary"
            />
          </label>
          <div className="flex flex-wrap gap-2">
            {categories.map((item) => (
              <button
                key={item}
                onClick={() => setCategory(item)}
                className={`rounded-full border px-4 py-2 text-sm transition ${
                  category === item
                    ? "border-primary bg-primary text-primary-foreground"
                    : "border-border bg-secondary/50 text-muted-foreground hover:text-foreground"
                }`}
              >
                {item}
              </button>
            ))}
          </div>
        </div>
      </GlassCard>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {filtered.map((tool) => (
          <GlassCard key={tool.slug} className="flex min-h-[240px] flex-col">
            <div className="mb-5 flex items-start justify-between gap-4">
              <div className="grid size-12 place-items-center rounded-2xl bg-primary/10 text-primary">
                <ToolIcon name={tool.icon} className="size-5" />
              </div>
              <Badge>{tool.category}</Badge>
            </div>
            <div className="flex-1">
              <h2 className="text-xl font-semibold text-foreground">{tool.title}</h2>
              <p className="mt-3 text-sm leading-7 text-muted-foreground">{tool.description}</p>
            </div>
            <Button asChild variant="outline" className="mt-6 w-full">
              <Link href={`/tools/${tool.slug}`}>
                进入工具
                <ArrowRight className="size-4" />
              </Link>
            </Button>
          </GlassCard>
        ))}
      </div>
    </div>
  );
}
