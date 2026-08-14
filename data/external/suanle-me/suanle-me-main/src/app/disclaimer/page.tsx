import type { Metadata } from "next";
import { GlassCard } from "@/components/ui/glass-card";
import { SectionHeading } from "@/components/ui/section-heading";

export const metadata: Metadata = {
  title: "免责声明",
  description: "算了么免责声明。",
};

export default function DisclaimerPage() {
  return (
    <main className="px-4 py-12 sm:px-6 sm:py-16 lg:px-8">
      <div className="mx-auto w-full max-w-4xl">
        <SectionHeading eyebrow="免责声明" title="传统文化体验，不替代专业建议" />
        <GlassCard interactive={false} className="space-y-5 p-7 text-sm leading-7 text-muted-foreground sm:p-10">
          <p>算了么提供的命理、卜筮、梦境和运势内容仅供传统文化体验、娱乐和自我观察参考。</p>
          <p>任何结果都不构成医学、法律、投资、心理咨询或其他专业建议。重要事项请咨询具备资质的专业人士。</p>
          <p>请勿因为页面结果做出高风险决定，也不要将其作为评价他人的依据。</p>
        </GlassCard>
      </div>
    </main>
  );
}
