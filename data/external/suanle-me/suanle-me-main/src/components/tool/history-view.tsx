"use client";

import Link from "next/link";
import { Clock, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { GlassCard } from "@/components/ui/glass-card";
import { formatDateTime } from "@/lib/utils";
import { useAppStore } from "@/lib/store";

export function HistoryView() {
  const history = useAppStore((state) => state.history);
  const clearHistory = useAppStore((state) => state.clearHistory);

  if (history.length === 0) {
    return (
      <GlassCard interactive={false} className="mx-auto max-w-2xl p-8 text-center">
        <Clock className="mx-auto mb-4 size-9 text-primary" />
        <h1 className="text-2xl font-semibold text-foreground">暂无历史</h1>
        <p className="mt-3 text-sm leading-7 text-muted-foreground">生成过的解读会保存在本地设备，方便你回看。</p>
        <Button asChild className="mt-6">
          <Link href="/tools">开始使用</Link>
        </Button>
      </GlassCard>
    );
  }

  return (
    <div className="grid gap-4">
      <div className="flex justify-end">
        <Button variant="outline" onClick={clearHistory}>
          <Trash2 className="size-4" />
          清空历史
        </Button>
      </div>
      {history.map((item) => (
        <GlassCard key={item.id} className="p-5">
          <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
            <div>
              <p className="text-xs text-primary">{formatDateTime(item.createdAt)}</p>
              <h2 className="mt-2 text-xl font-semibold text-foreground">{item.title}</h2>
              <p className="mt-3 text-sm leading-7 text-muted-foreground">{item.summary}</p>
            </div>
            <Button asChild variant="outline" size="sm">
              <Link href={`/tools/${item.slug}`}>重开工具</Link>
            </Button>
          </div>
        </GlassCard>
      ))}
    </div>
  );
}
