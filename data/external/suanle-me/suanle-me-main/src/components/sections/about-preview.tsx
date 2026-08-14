import Link from "next/link";
import { ArrowRight } from "lucide-react";
import { Button } from "@/components/ui/button";
import { GlassCard } from "@/components/ui/glass-card";
import { SectionHeading } from "@/components/ui/section-heading";

export function AboutPreview() {
  return (
    <section className="px-4 py-16 sm:px-6 sm:py-24 lg:px-8">
      <div className="mx-auto w-full max-w-7xl">
        <SectionHeading
          eyebrow="关于"
          title="以现代设计重新呈现传统文化"
          description="「算了么」是一个免费的东方命理工具集合。不收费，不卖课，不开会员，不开广告。"
        />
        <GlassCard interactive={false} className="mx-auto max-w-4xl p-7 sm:p-10">
          <div className="grid gap-8 md:grid-cols-[0.85fr_1.15fr] md:items-center">
            <div className="grid aspect-square place-items-center rounded-[24px] border border-primary/20 bg-primary/10 font-serif text-8xl text-primary">
              ☯
            </div>
            <div>
              <p className="text-pretty text-base leading-8 text-muted-foreground">
                我们把复杂的传统术数界面重新整理为清爽、克制、可扫描的现代工具。它更像一个安静的本地应用：
                打开、输入、得到结构化提示，然后离开。
              </p>
              <p className="mt-4 text-pretty text-base leading-8 text-muted-foreground">
                所有结果仅供传统文化体验与自我观察参考，不替代专业建议，也不制造焦虑。
              </p>
              <Button asChild variant="outline" className="mt-6">
                <Link href="/about">
                  了解更多
                  <ArrowRight className="size-4" />
                </Link>
              </Button>
            </div>
          </div>
        </GlassCard>
      </div>
    </section>
  );
}
