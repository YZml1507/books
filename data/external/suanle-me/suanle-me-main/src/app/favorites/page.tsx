import type { Metadata } from "next";
import { FavoritesView } from "@/components/tool/favorites-view";
import { SectionHeading } from "@/components/ui/section-heading";

export const metadata: Metadata = {
  title: "收藏",
  description: "查看你在算了么收藏的本地命理工具。",
};

export default function FavoritesPage() {
  return (
    <main className="px-4 py-12 sm:px-6 sm:py-16 lg:px-8">
      <div className="mx-auto w-full max-w-7xl">
        <SectionHeading eyebrow="收藏" title="常用工具" description="收藏记录保存在你的浏览器本地。" />
        <FavoritesView />
      </div>
    </main>
  );
}
