# 算了么（suanle.me）

免费、开源、现代化的东方命理工具箱。项目采用 Apple + Notion + 小宇宙式的极简审美，结合东方玄学、留白、毛玻璃、星空粒子与若隐若现的八卦视觉。

## 特性

- Next.js 15 App Router + TypeScript
- TailwindCSS v4 + Shadcn UI 风格组件
- Framer Motion 微动画
- Lucide Icons 图标系统
- Zustand 本地收藏与历史记录
- Recharts 本地结果可视化
- PWA manifest + service worker
- 支持 PC、手机、平板响应式布局
- 免费、开源、本地计算、无需登录

## 工具

- 紫微斗数
- 八字排盘
- 梅花易数
- 奇门遁甲
- 六爻
- 塔罗牌
- 周公解梦
- 每日运势
- 黄历
- 姓名分析
- 五行分析
- AI 解读（本地规则化解读，不调用远程模型）

## 本地运行

```bash
npm install
npm run dev
```

打开 `http://localhost:3000`。

## 质量检查

```bash
npm run typecheck
npm run lint
npm run build
```

## 部署

### Vercel

导入 GitHub 仓库后保持默认配置即可：

- Framework Preset: Next.js
- Build Command: `npm run build`
- Output: `.next`

### Cloudflare Pages

使用 Next.js Pages 配置：

- Build Command: `npm run build`
- Node.js version: 20 或更高

如需 Cloudflare Workers 适配，可在后续接入 `@cloudflare/next-on-pages`。

## 隐私

当前版本不要求登录，不接入广告，不上传用户输入。收藏和历史记录通过浏览器本地存储保存。

## 免责声明

本项目提供的命理、卜筮、梦境和运势内容仅供传统文化体验、娱乐和自我观察参考，不构成医学、法律、投资、心理咨询或其他专业建议。

## License

MIT
