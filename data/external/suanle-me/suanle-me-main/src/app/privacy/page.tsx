import type { Metadata } from "next";
import { GlassCard } from "@/components/ui/glass-card";
import { SectionHeading } from "@/components/ui/section-heading";

export const metadata: Metadata = {
  title: "隐私政策",
  description: "算了么隐私政策。",
};

export default function PrivacyPage() {
  return (
    <main className="px-4 py-12 sm:px-6 sm:py-16 lg:px-8">
      <div className="mx-auto w-full max-w-4xl">
        <SectionHeading eyebrow="隐私政策" title="你的输入默认留在本地" />
        <GlassCard interactive={false} className="space-y-5 p-7 text-sm leading-7 text-muted-foreground sm:p-10">
          <p>算了么的工具计算在浏览器本地完成。收藏和历史记录通过浏览器本地存储保存。</p>
          <p>当前项目不要求登录，不上传你的姓名、日期、问题或梦境内容，也不接入广告追踪。</p>
          <p>如果你部署自己的版本，请根据实际接入的分析、登录或后端服务更新本政策。</p>
        </GlassCard>
      </div>
    </main>
  );
}
