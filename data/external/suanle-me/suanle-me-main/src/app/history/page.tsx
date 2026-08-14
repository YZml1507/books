import type { Metadata } from "next";
import { HistoryView } from "@/components/tool/history-view";
import { SectionHeading } from "@/components/ui/section-heading";

export const metadata: Metadata = {
  title: "历史",
  description: "查看算了么在本地保存的最近解读历史。",
};

export default function HistoryPage() {
  return (
    <main className="px-4 py-12 sm:px-6 sm:py-16 lg:px-8">
      <div className="mx-auto w-full max-w-4xl">
        <SectionHeading eyebrow="历史" title="最近解读" description="历史只保存在本机浏览器，不会上传到服务器。" />
        <HistoryView />
      </div>
    </main>
  );
}
