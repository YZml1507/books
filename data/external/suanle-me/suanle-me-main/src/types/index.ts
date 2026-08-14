export type ToolSlug =
  | "ziwei"
  | "bazi"
  | "meihua"
  | "qimen"
  | "liuyao"
  | "tarot"
  | "dream"
  | "daily-fortune"
  | "almanac"
  | "name"
  | "wuxing"
  | "ai-reading";

export type IconName =
  | "orbit"
  | "calendar"
  | "sparkles"
  | "compass"
  | "coins"
  | "cards"
  | "moon"
  | "sun"
  | "book"
  | "signature"
  | "flame"
  | "brain";

export type FortuneTool = {
  slug: ToolSlug;
  title: string;
  intro: string;
  description: string;
  icon: IconName;
  accent: string;
  category: "命盘" | "卜筮" | "日用" | "分析";
};

export type Quote = {
  text: string;
  source: string;
};

export type ToolInput = {
  name: string;
  birthDate: string;
  birthTime: string;
  question: string;
  numberA: number;
  numberB: number;
};

export type ChartDatum = {
  name: string;
  value: number;
};

export type ToolReading = {
  title: string;
  summary: string;
  score: number;
  tags: string[];
  sections: Array<{
    label: string;
    value: string;
  }>;
  chart: ChartDatum[];
  lines?: string[];
};

export type HistoryItem = {
  id: string;
  slug: ToolSlug;
  title: string;
  summary: string;
  createdAt: string;
};
