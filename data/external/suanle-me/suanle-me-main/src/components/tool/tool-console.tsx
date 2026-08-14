"use client";

import { useMemo, useState } from "react";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { CalendarDays, Heart, Play, RotateCcw, Sparkles } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { GlassCard } from "@/components/ui/glass-card";
import { getToolReading } from "@/lib/divination";
import { useAppStore } from "@/lib/store";
import type { FortuneTool, ToolInput, ToolReading } from "@/types";

const emptyInput: ToolInput = {
  name: "",
  birthDate: "",
  birthTime: "08:00",
  question: "",
  numberA: 3,
  numberB: 8,
};

function today() {
  return new Date().toISOString().slice(0, 10);
}

export function ToolConsole({ tool }: { tool: FortuneTool }) {
  const [input, setInput] = useState<ToolInput>(() => ({
    ...emptyInput,
    birthDate: today(),
    question: tool.slug === "dream" ? "梦见水和雨" : "我现在应该如何推进这件事？",
  }));
  const [reading, setReading] = useState<ToolReading>(() => getToolReading(tool.slug, input));
  const favorites = useAppStore((state) => state.favorites);
  const toggleFavorite = useAppStore((state) => state.toggleFavorite);
  const addHistory = useAppStore((state) => state.addHistory);
  const isFavorite = favorites.includes(tool.slug);

  const chartColor = useMemo(() => tool.accent, [tool.accent]);

  const updateInput = (key: keyof ToolInput, value: string | number) => {
    setInput((current) => ({ ...current, [key]: value }));
  };

  const run = () => {
    const result = getToolReading(tool.slug, input);
    setReading(result);
    addHistory({
      id: `${tool.slug}-${Date.now()}`,
      slug: tool.slug,
      title: result.title,
      summary: result.summary,
      createdAt: new Date().toISOString(),
    });
  };

  const reset = () => {
    const next = {
      ...emptyInput,
      birthDate: today(),
      question: tool.slug === "dream" ? "梦见水和雨" : "我现在应该如何推进这件事？",
    };
    setInput(next);
    setReading(getToolReading(tool.slug, next));
  };

  return (
    <div className="grid gap-5 lg:grid-cols-[0.86fr_1.14fr]">
      <GlassCard interactive={false} className="h-fit p-5 sm:p-6">
        <div className="mb-6 flex items-start justify-between gap-4">
          <div>
            <Badge className="mb-3 border-primary/25 text-primary">{tool.category}</Badge>
            <h1 className="text-3xl font-semibold text-foreground">{tool.title}</h1>
            <p className="mt-3 text-sm leading-7 text-muted-foreground">{tool.description}</p>
          </div>
          <Button
            variant={isFavorite ? "default" : "outline"}
            size="icon"
            onClick={() => toggleFavorite(tool.slug)}
            aria-label={isFavorite ? "取消收藏" : "收藏工具"}
            title={isFavorite ? "取消收藏" : "收藏工具"}
          >
            <Heart className="size-4" fill={isFavorite ? "currentColor" : "none"} />
          </Button>
        </div>

        <div className="grid gap-4">
          <label className="grid gap-2 text-sm text-muted-foreground">
            姓名
            <input
              value={input.name}
              onChange={(event) => updateInput("name", event.target.value)}
              placeholder="可留空"
              className="h-12 rounded-2xl border border-border bg-background/40 px-4 text-foreground outline-none transition focus:border-primary"
            />
          </label>

          <div className="grid gap-4 sm:grid-cols-2">
            <label className="grid gap-2 text-sm text-muted-foreground">
              日期
              <input
                type="date"
                value={input.birthDate}
                onChange={(event) => updateInput("birthDate", event.target.value)}
                className="h-12 rounded-2xl border border-border bg-background/40 px-4 text-foreground outline-none transition focus:border-primary"
              />
            </label>
            <label className="grid gap-2 text-sm text-muted-foreground">
              时间
              <input
                type="time"
                value={input.birthTime}
                onChange={(event) => updateInput("birthTime", event.target.value)}
                className="h-12 rounded-2xl border border-border bg-background/40 px-4 text-foreground outline-none transition focus:border-primary"
              />
            </label>
          </div>

          <label className="grid gap-2 text-sm text-muted-foreground">
            问题 / 梦境 / 关键词
            <textarea
              value={input.question}
              onChange={(event) => updateInput("question", event.target.value)}
              rows={4}
              placeholder="写下你正在关心的事"
              className="resize-none rounded-2xl border border-border bg-background/40 px-4 py-3 text-foreground outline-none transition focus:border-primary"
            />
          </label>

          <div className="grid gap-4 sm:grid-cols-2">
            <label className="grid gap-2 text-sm text-muted-foreground">
              起数一
              <input
                type="number"
                min={1}
                max={99}
                value={input.numberA}
                onChange={(event) => updateInput("numberA", Number(event.target.value))}
                className="h-12 rounded-2xl border border-border bg-background/40 px-4 text-foreground outline-none transition focus:border-primary"
              />
            </label>
            <label className="grid gap-2 text-sm text-muted-foreground">
              起数二
              <input
                type="number"
                min={1}
                max={99}
                value={input.numberB}
                onChange={(event) => updateInput("numberB", Number(event.target.value))}
                className="h-12 rounded-2xl border border-border bg-background/40 px-4 text-foreground outline-none transition focus:border-primary"
              />
            </label>
          </div>
        </div>

        <div className="mt-6 flex flex-col gap-3 sm:flex-row">
          <Button onClick={run} className="h-12 flex-1">
            <Play className="size-4" />
            生成解读
          </Button>
          <Button onClick={reset} variant="outline" className="h-12">
            <RotateCcw className="size-4" />
            重置
          </Button>
        </div>
      </GlassCard>

      <GlassCard interactive={false} className="overflow-hidden p-5 sm:p-6">
        <div className="mb-6 flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
          <div>
            <div className="mb-3 flex items-center gap-2 text-sm text-primary">
              <Sparkles className="size-4" />
              本地生成结果
            </div>
            <h2 className="text-balance text-2xl font-semibold text-foreground sm:text-3xl">{reading.title}</h2>
            <p className="mt-3 text-pretty text-sm leading-7 text-muted-foreground">{reading.summary}</p>
          </div>
          <div className="rounded-[24px] border border-primary/25 bg-primary/10 px-5 py-4 text-center">
            <div className="text-3xl font-semibold text-primary">{reading.score}</div>
            <div className="text-xs text-muted-foreground">综合指数</div>
          </div>
        </div>

        <div className="mb-6 flex flex-wrap gap-2">
          {reading.tags.map((tag) => (
            <Badge key={tag}>{tag}</Badge>
          ))}
        </div>

        <div className="grid gap-4 md:grid-cols-2">
          {reading.sections.map((section) => (
            <div key={section.label} className="rounded-[20px] border border-border bg-background/25 p-4">
              <div className="mb-2 flex items-center gap-2 text-xs text-primary">
                <CalendarDays className="size-3.5" />
                {section.label}
              </div>
              <p className="text-sm leading-7 text-foreground">{section.value}</p>
            </div>
          ))}
        </div>

        {reading.lines ? (
          <div className="mt-5 rounded-[20px] border border-border bg-background/25 p-4">
            <div className="mb-3 text-xs text-primary">六爻</div>
            <div className="grid gap-2 font-mono text-sm text-foreground">
              {[...reading.lines].reverse().map((line, index) => (
                <div key={`${line}-${index}`} className="rounded-xl bg-secondary/50 px-3 py-2">
                  {line}
                </div>
              ))}
            </div>
          </div>
        ) : null}

        <div className="mt-6 h-72 rounded-[20px] border border-border bg-background/25 p-4">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={reading.chart}>
              <CartesianGrid stroke="rgba(245,241,232,0.10)" vertical={false} />
              <XAxis dataKey="name" tick={{ fill: "currentColor", fontSize: 12 }} axisLine={false} tickLine={false} />
              <YAxis tick={{ fill: "currentColor", fontSize: 12 }} axisLine={false} tickLine={false} width={30} />
              <Tooltip
                cursor={{ fill: "rgba(201,168,106,0.08)" }}
                contentStyle={{
                  background: "rgba(11,11,11,0.88)",
                  border: "1px solid rgba(201,168,106,0.26)",
                  borderRadius: 16,
                  color: "#F5F1E8",
                }}
              />
              <Bar dataKey="value" radius={[10, 10, 4, 4]} fill={chartColor} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </GlassCard>
    </div>
  );
}
