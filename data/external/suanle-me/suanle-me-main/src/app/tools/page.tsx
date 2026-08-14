import type { Metadata } from "next";
import { ToolDirectory } from "@/components/tool/tool-directory";
import { SectionHeading } from "@/components/ui/section-heading";

export const metadata: Metadata = {
  title: "工具",
  description: "算了么工具箱，包含紫微斗数、八字排盘、梅花易数、奇门遁甲、六爻、塔罗牌、周公解梦、黄历等工具。",
};

export default function ToolsPage() {
  return (
    <main className="px-4 py-12 sm:px-6 sm:py-16 lg:px-8">
      <div className="mx-auto w-full max-w-7xl">
        <SectionHeading
          eyebrow="工具"
          title="选择一个工具开始"
          description="所有工具都在本地运行。你可以收藏常用工具，也可以在历史里回看最近的解读。"
        />
        <ToolDirectory />
      </div>
    </main>
  );
}
