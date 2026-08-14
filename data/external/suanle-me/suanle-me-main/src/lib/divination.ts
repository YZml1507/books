import { dreamKeywords, hexagrams, tarotDeck } from "@/lib/constants";
import type { ToolInput, ToolReading, ToolSlug } from "@/types";

const heavenlyStems = ["甲", "乙", "丙", "丁", "戊", "己", "庚", "辛", "壬", "癸"];
const earthlyBranches = ["子", "丑", "寅", "卯", "辰", "巳", "午", "未", "申", "酉", "戌", "亥"];
const elements = ["木", "火", "土", "金", "水"];
const trigrams = ["乾", "兑", "离", "震", "巽", "坎", "艮", "坤"];
const qimenDoors = ["休门", "生门", "伤门", "杜门", "景门", "死门", "惊门", "开门"];
const qimenStars = ["天蓬", "天任", "天冲", "天辅", "天英", "天芮", "天柱", "天心"];
const almanacActions = ["祭祀", "会友", "修造", "出行", "纳财", "学习", "签约", "整理", "开市", "安床"];
const almanacAvoids = ["争执", "冲动投资", "熬夜", "搬动重物", "仓促承诺", "远行", "借贷", "口舌"];
const palaces = ["命宫", "兄弟", "夫妻", "子女", "财帛", "疾厄", "迁移", "仆役", "官禄", "田宅", "福德", "父母"];
const majorStars = ["紫微", "天机", "太阳", "武曲", "天同", "廉贞", "天府", "太阴", "贪狼", "巨门", "天相", "天梁", "七杀", "破军"];

function normalizeInput(input: ToolInput) {
  return `${input.name}|${input.birthDate}|${input.birthTime}|${input.question}|${input.numberA}|${input.numberB}`;
}

export function hashText(value: string) {
  let hash = 2166136261;
  for (let index = 0; index < value.length; index += 1) {
    hash ^= value.charCodeAt(index);
    hash = Math.imul(hash, 16777619);
  }
  return Math.abs(hash >>> 0);
}

function pick<T>(items: T[], seed: number, offset = 0) {
  return items[(seed + offset) % items.length];
}

function score(seed: number, offset = 0) {
  return 52 + ((seed >> (offset % 12)) % 43);
}

function safeDate(value: string) {
  if (!value) {
    return new Date();
  }
  const date = new Date(`${value}T00:00:00`);
  return Number.isNaN(date.getTime()) ? new Date() : date;
}

function dateKey(date: Date) {
  return `${date.getFullYear()}-${date.getMonth() + 1}-${date.getDate()}`;
}

function stemBranch(index: number) {
  return `${heavenlyStems[index % 10]}${earthlyBranches[index % 12]}`;
}

function elementFromStemBranch(value: string) {
  const stem = heavenlyStems.indexOf(value.slice(0, 1));
  return elements[Math.max(0, stem) % elements.length];
}

function dateToJulianDay(date: Date) {
  const year = date.getFullYear();
  const month = date.getMonth() + 1;
  const day = date.getDate();
  const a = Math.floor((14 - month) / 12);
  const y = year + 4800 - a;
  const m = month + 12 * a - 3;
  return day + Math.floor((153 * m + 2) / 5) + 365 * y + Math.floor(y / 4) - Math.floor(y / 100) + Math.floor(y / 400) - 32045;
}

function baziPillars(input: ToolInput) {
  const date = safeDate(input.birthDate);
  const hour = Number(input.birthTime.split(":")[0] ?? 0);
  const yearIndex = date.getFullYear() - 1984;
  const monthIndex = yearIndex * 12 + date.getMonth() + 2;
  const dayIndex = dateToJulianDay(date) - 2445733;
  const hourIndex = dayIndex * 12 + Math.floor((hour + 1) / 2);

  return {
    year: stemBranch((yearIndex % 60 + 60) % 60),
    month: stemBranch((monthIndex % 60 + 60) % 60),
    day: stemBranch((dayIndex % 60 + 60) % 60),
    hour: stemBranch((hourIndex % 60 + 60) % 60),
  };
}

function elementChart(seed: number, input: ToolInput) {
  const pillars = baziPillars(input);
  const base = elements.map((name, index) => ({
    name,
    value: 12 + ((seed >> index) % 18),
  }));

  Object.values(pillars).forEach((pillar, index) => {
    const element = elementFromStemBranch(pillar);
    const target = base.find((item) => item.name === element);
    if (target) {
      target.value += 12 + index * 2;
    }
  });

  return base;
}

function commonReading(slug: ToolSlug, input: ToolInput) {
  const seed = hashText(`${slug}|${normalizeInput(input)}|${dateKey(new Date())}`);
  return { seed, chart: elementChart(seed, input), score: score(seed) };
}

export function getToolReading(slug: ToolSlug, input: ToolInput): ToolReading {
  const { seed, chart, score: baseScore } = commonReading(slug, input);
  const name = input.name.trim() || "未署名";
  const question = input.question.trim() || "当下最重要的事";

  if (slug === "bazi") {
    const pillars = baziPillars(input);
    const strongest = [...chart].sort((a, b) => b.value - a.value)[0];
    const weakest = [...chart].sort((a, b) => a.value - b.value)[0];
    return {
      title: `${name}的八字简盘`,
      summary: `四柱为 ${pillars.year}、${pillars.month}、${pillars.day}、${pillars.hour}。五行以${strongest.name}偏旺，${weakest.name}可补。`,
      score: baseScore,
      tags: ["四柱", "五行", "本地计算"],
      sections: [
        { label: "年柱", value: pillars.year },
        { label: "月柱", value: pillars.month },
        { label: "日柱", value: pillars.day },
        { label: "时柱", value: pillars.hour },
        { label: "建议", value: `近期可用${weakest.name}的方式补足节律：慢下来、做整理、减少情绪化决策。` },
      ],
      chart,
    };
  }

  if (slug === "ziwei") {
    const palace = pick(palaces, seed);
    const star = pick(majorStars, seed, 7);
    const assistant = pick(majorStars, seed, 19);
    return {
      title: `${name}的紫微结构`,
      summary: `${star}入${palace}，辅以${assistant}，适合把长期目标拆成稳定、可复盘的行动。`,
      score: baseScore,
      tags: ["十二宫", "主星", "人生结构"],
      sections: [
        { label: "命宫提示", value: palace },
        { label: "主星", value: star },
        { label: "辅星", value: assistant },
        { label: "观察", value: `${question}更像是节奏问题，不宜只靠一次选择定胜负。` },
      ],
      chart,
    };
  }

  if (slug === "meihua") {
    const upper = pick(trigrams, seed + input.numberA);
    const lower = pick(trigrams, seed + input.numberB, 3);
    const hexagram = pick(hexagrams, seed + input.numberA * 8 + input.numberB);
    const changingLine = ((seed + input.numberA + input.numberB) % 6) + 1;
    return {
      title: `${question}的梅花卦`,
      summary: `本卦为${hexagram}，上${upper}下${lower}，第${changingLine}爻动。先辨方向，再做小规模验证。`,
      score: baseScore,
      tags: ["起卦", "动爻", "取象"],
      sections: [
        { label: "上卦", value: upper },
        { label: "下卦", value: lower },
        { label: "本卦", value: hexagram },
        { label: "动爻", value: `第${changingLine}爻` },
        { label: "断语", value: "眼前信息未必完整，适合先求证，再加码。" },
      ],
      chart,
    };
  }

  if (slug === "qimen") {
    const palace = ((seed % 9) + 1).toString();
    const door = pick(qimenDoors, seed);
    const star = pick(qimenStars, seed, 5);
    return {
      title: `${question}的奇门时局`,
      summary: `${door}临${palace}宫，${star}主事。当前宜稳中有进，避免被短期声量牵着走。`,
      score: baseScore,
      tags: ["九宫", "门星", "择时"],
      sections: [
        { label: "值使", value: door },
        { label: "值符", value: star },
        { label: "宫位", value: `${palace}宫` },
        { label: "行动", value: door.includes("开") || door.includes("生") ? "适合启动与沟通。" : "适合观察、归档和修正计划。" },
      ],
      chart,
    };
  }

  if (slug === "liuyao") {
    const lines = Array.from({ length: 6 }, (_, index) => {
      const value = (seed >> index) % 4;
      return value === 0 ? "老阴 -- x" : value === 1 ? "少阳 ----" : value === 2 ? "少阴 -- --" : "老阳 ---- o";
    });
    const hexagram = pick(hexagrams, seed);
    return {
      title: `${question}的六爻卦`,
      summary: `得${hexagram}，动静相杂。先看已有资源，再判断是否需要转换路径。`,
      score: baseScore,
      tags: ["六爻", "世应", "动爻"],
      sections: [
        { label: "本卦", value: hexagram },
        { label: "世爻", value: `第${(seed % 6) + 1}爻` },
        { label: "应爻", value: `第${((seed + 3) % 6) + 1}爻` },
        { label: "断语", value: "变化来自外部反馈，别把所有压力都归因给自己。" },
      ],
      chart,
      lines,
    };
  }

  if (slug === "tarot") {
    const cards = [pick(tarotDeck, seed), pick(tarotDeck, seed, 9), pick(tarotDeck, seed, 17)];
    return {
      title: `${question}的三牌阵`,
      summary: `${cards[0]}、${cards[1]}、${cards[2]}依次出现。主题是从直觉走向秩序，再走向更明确的选择。`,
      score: baseScore,
      tags: ["三牌阵", "直觉", "趋势"],
      sections: [
        { label: "过去", value: cards[0] },
        { label: "现在", value: cards[1] },
        { label: "趋势", value: cards[2] },
        { label: "提醒", value: "把问题写得更具体，答案就会更清楚。" },
      ],
      chart,
    };
  }

  if (slug === "dream") {
    const matched = dreamKeywords.find((item) => question.includes(item.key)) ?? pick(dreamKeywords, seed);
    return {
      title: `${name}的梦境提示`,
      summary: `关键词「${matched.key}」提示：${matched.meaning}`,
      score: baseScore,
      tags: ["梦境", "意象", "情绪"],
      sections: [
        { label: "匹配意象", value: matched.key },
        { label: "传统提示", value: matched.meaning },
        { label: "现代提醒", value: "梦不是预言，更像身心状态的隐喻。先记录，再观察重复主题。" },
      ],
      chart,
    };
  }

  if (slug === "daily-fortune") {
    const today = new Intl.DateTimeFormat("zh-CN", { dateStyle: "full" }).format(new Date());
    return {
      title: `${name}的今日运势`,
      summary: `今日综合指数 ${baseScore}。适合处理${pick(["沟通", "整理", "学习", "财务复盘", "长期计划"], seed)}相关事务。`,
      score: baseScore,
      tags: ["今日", "节律", "行动"],
      sections: [
        { label: "日期", value: today },
        { label: "宜", value: pick(almanacActions, seed) },
        { label: "忌", value: pick(almanacAvoids, seed, 4) },
        { label: "提醒", value: "先完成一件小事，会比等待状态更有效。" },
      ],
      chart: [
        { name: "行动", value: score(seed, 1) },
        { name: "关系", value: score(seed, 2) },
        { name: "财务", value: score(seed, 3) },
        { name: "身心", value: score(seed, 4) },
      ],
    };
  }

  if (slug === "almanac") {
    const date = safeDate(input.birthDate);
    const branch = pick(earthlyBranches, seed);
    return {
      title: `${dateKey(date)} 黄历`,
      summary: `今日值${branch}，宜${pick(almanacActions, seed)}，忌${pick(almanacAvoids, seed, 8)}。`,
      score: baseScore,
      tags: ["黄历", "宜忌", "民俗"],
      sections: [
        { label: "宜", value: `${pick(almanacActions, seed)}、${pick(almanacActions, seed, 3)}、${pick(almanacActions, seed, 6)}` },
        { label: "忌", value: `${pick(almanacAvoids, seed)}、${pick(almanacAvoids, seed, 5)}` },
        { label: "冲", value: `冲${branch}` },
        { label: "五行", value: pick(elements, seed) },
      ],
      chart,
    };
  }

  if (slug === "name") {
    const chars = Array.from(name);
    const total = chars.reduce((sum, char) => sum + char.codePointAt(0)!, 0);
    const dominant = pick(elements, total);
    return {
      title: `${name}的姓名分析`,
      summary: `名字整体偏${dominant}，节奏${chars.length <= 2 ? "简洁直接" : "层次较多"}，适合保持清晰、克制的表达。`,
      score: 60 + (total % 35),
      tags: ["姓名", "五行", "音形"],
      sections: [
        { label: "字符数", value: `${chars.length}` },
        { label: "主五行", value: dominant },
        { label: "气质", value: pick(["沉稳", "开阔", "敏锐", "温润", "果断"], total) },
        { label: "建议", value: "对外展示时保持统一写法，减少昵称和简称切换。" },
      ],
      chart: elementChart(total, input),
    };
  }

  if (slug === "wuxing") {
    const strongest = [...chart].sort((a, b) => b.value - a.value)[0];
    const weakest = [...chart].sort((a, b) => a.value - b.value)[0];
    return {
      title: `${name}的五行平衡`,
      summary: `${strongest.name}偏旺，${weakest.name}偏弱。保持作息、空间和目标的平衡，会比追求单点爆发更稳。`,
      score: baseScore,
      tags: ["五行", "平衡", "趋势"],
      sections: [
        { label: "偏旺", value: strongest.name },
        { label: "偏弱", value: weakest.name },
        { label: "调和", value: `用${weakest.name}的象意补足：环境、颜色、节奏或任务类型都可以调整。` },
      ],
      chart,
    };
  }

  return {
    title: `${name}的本地 AI 解读`,
    summary: `围绕「${question}」，系统综合命盘、节律与意象，建议你先定义边界，再选择最小行动。`,
    score: baseScore,
    tags: ["本地规则", "综合解读", "隐私友好"],
    sections: [
      { label: "核心问题", value: question },
      { label: "当下节律", value: baseScore > 75 ? "适合主动推进。" : "适合小步验证。" },
      { label: "关键动作", value: pick(["写下计划", "约一次沟通", "复盘现金流", "清理待办", "暂缓承诺"], seed) },
      { label: "隐私说明", value: "此解读不调用远程模型，也不会上传你的输入。" },
    ],
    chart,
  };
}
