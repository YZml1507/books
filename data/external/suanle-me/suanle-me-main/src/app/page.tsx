import { AboutPreview } from "@/components/sections/about-preview";
import { FeatureGrid } from "@/components/sections/feature-grid";
import { Hero } from "@/components/sections/hero";
import { Highlights } from "@/components/sections/highlights";
import { QuoteCard } from "@/components/sections/quote-card";

export default function HomePage() {
  return (
    <main>
      <Hero />
      <FeatureGrid />
      <Highlights />
      <QuoteCard />
      <AboutPreview />
    </main>
  );
}
