import Link from "next/link";
import { Github } from "lucide-react";
import { siteConfig } from "@/lib/site";

const footerLinks = [
  { label: "Github", href: siteConfig.github, external: true },
  { label: "MIT License", href: "https://opensource.org/license/mit", external: true },
  { label: "免责声明", href: "/disclaimer" },
  { label: "隐私政策", href: "/privacy" },
  { label: "反馈建议", href: `${siteConfig.github}/issues`, external: true },
];

export function Footer() {
  return (
    <footer className="border-t border-border/70">
      <div className="mx-auto flex w-full max-w-7xl flex-col gap-8 px-4 py-10 sm:px-6 lg:px-8">
        <div className="flex flex-col justify-between gap-6 md:flex-row md:items-center">
          <div>
            <div className="flex items-center gap-2 text-base font-semibold">
              <span className="text-primary">☯</span>
              <span>算了么</span>
            </div>
            <p className="mt-2 max-w-xl text-sm leading-6 text-muted-foreground">
              免费、开源、现代化的东方命理工具箱。所有工具仅作传统文化体验与自我观察参考。
            </p>
          </div>
          <Link
            href={siteConfig.github}
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center gap-2 text-sm text-muted-foreground transition-colors hover:text-primary"
          >
            <Github className="size-4" />
            Open Source
          </Link>
        </div>
        <div className="flex flex-col justify-between gap-4 border-t border-border/70 pt-6 text-xs text-muted-foreground md:flex-row md:items-center">
          <p>Copyright © {new Date().getFullYear()} suanle.me. Released under the MIT License.</p>
          <div className="flex flex-wrap gap-x-5 gap-y-2">
            {footerLinks.map((link) => (
              <Link
                key={link.label}
                href={link.href}
                target={link.external ? "_blank" : undefined}
                rel={link.external ? "noreferrer" : undefined}
                className="hover:text-primary"
              >
                {link.label}
              </Link>
            ))}
          </div>
        </div>
      </div>
    </footer>
  );
}
