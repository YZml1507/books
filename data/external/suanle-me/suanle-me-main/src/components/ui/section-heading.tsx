import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

type SectionHeadingProps = {
  eyebrow: string;
  title: string;
  description?: string;
  className?: string;
};

export function SectionHeading({ eyebrow, title, description, className }: SectionHeadingProps) {
  return (
    <div className={cn("mx-auto mb-10 max-w-3xl text-center", className)}>
      <Badge className="mb-4 border-primary/25 text-primary">{eyebrow}</Badge>
      <h2 className="text-balance text-3xl font-semibold text-foreground sm:text-4xl">{title}</h2>
      {description ? (
        <p className="mx-auto mt-4 max-w-2xl text-pretty text-sm leading-7 text-muted-foreground sm:text-base">
          {description}
        </p>
      ) : null}
    </div>
  );
}
