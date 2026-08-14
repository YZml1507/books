import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { ToolConsole } from "@/components/tool/tool-console";
import { fortuneTools, toolOrder } from "@/lib/constants";
import type { ToolSlug } from "@/types";

type PageProps = {
  params: Promise<{
    slug: string;
  }>;
};

function getTool(slug: string) {
  return fortuneTools.find((tool) => tool.slug === slug);
}

export function generateStaticParams() {
  return toolOrder.map((slug) => ({ slug }));
}

export async function generateMetadata({ params }: PageProps): Promise<Metadata> {
  const { slug } = await params;
  const tool = getTool(slug);

  if (!tool) {
    return {
      title: "工具不存在",
    };
  }

  return {
    title: tool.title,
    description: tool.description,
  };
}

export default async function ToolPage({ params }: PageProps) {
  const { slug } = await params;
  const tool = getTool(slug as ToolSlug);

  if (!tool) {
    notFound();
  }

  return (
    <main className="px-4 py-12 sm:px-6 sm:py-16 lg:px-8">
      <div className="mx-auto w-full max-w-7xl">
        <ToolConsole tool={tool} />
      </div>
    </main>
  );
}
