export const siteConfig = {
  name: "算了么",
  title: "算了么 - 免费开源东方命理工具箱",
  description:
    "支持紫微斗数、八字排盘、梅花易数、奇门遁甲、六爻、塔罗牌、周公解梦、黄历、每日运势等功能。",
  url: process.env.NEXT_PUBLIC_SITE_URL ?? "https://suanle.me",
  github: process.env.NEXT_PUBLIC_GITHUB_URL ?? "https://github.com/ssqz2zqp2m-del/suanle-me",
  author: "suanle.me",
};

type NavItem = {
  label: string;
  href: string;
  external?: boolean;
};

export const navItems: NavItem[] = [
  { label: "首页", href: "/" },
  { label: "工具", href: "/tools" },
  { label: "收藏", href: "/favorites" },
  { label: "历史", href: "/history" },
  { label: "关于", href: "/about" },
  { label: "Github", href: siteConfig.github, external: true },
];
