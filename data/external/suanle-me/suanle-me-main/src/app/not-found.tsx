import Link from "next/link";
import { Button } from "@/components/ui/button";
import { GlassCard } from "@/components/ui/glass-card";

export default function NotFound() {
  return (
    <main className="grid min-h-[70vh] place-items-center px-4 py-16">
      <GlassCard interactive={false} className="max-w-xl p-8 text-center">
        <div className="mx-auto mb-5 grid size-16 place-items-center rounded-full bg-primary/10 text-3xl text-primary">☯</div>
        <h1 className="text-2xl font-semibold text-foreground">页面未找到</h1>
        <p className="mt-3 text-sm leading-7 text-muted-foreground">这条路径暂时没有对应的工具或页面。</p>
        <Button asChild className="mt-6">
          <Link href="/">回到首页</Link>
        </Button>
      </GlassCard>
    </main>
  );
}
