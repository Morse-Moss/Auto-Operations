export type RewriteTemplateKey = "safe" | "polish" | "seed";

export type RewriteTemplate = {
  label: string;
  buttonLabel: string;
  description: string;
  instruction: string;
};

export const DEFAULT_REWRITE_TEMPLATE_KEY: RewriteTemplateKey = "safe";

export const REWRITE_TEMPLATES: Record<RewriteTemplateKey, RewriteTemplate> = {
  safe: {
    label: "安全改写",
    buttonLabel: "生成安全改写版",
    description: "适合参考竞品，降低相似风险",
    instruction:
      "保留原文事实、核心卖点和内容逻辑，但不要逐句同义替换。\n" +
      "请重组表达顺序、改变句式和语气，写成一篇自然的小红书种草笔记。\n" +
      "避免出现与原文明显相同的句子、连续短语或段落结构；长内容要像重新写过，而不是轻微润色。\n" +
      "不新增未经原文支持的功效、数据、承诺或夸张表达。",
  },
  polish: {
    label: "轻度润色",
    buttonLabel: "生成轻度润色版",
    description: "适合原创短文，只优化表达",
    instruction:
      "在不改变原意和内容顺序的前提下，轻度润色表达。\n" +
      "让语气更自然、更像真实用户分享，减少生硬、重复和机器感。\n" +
      "不要大幅重写，不要添加新信息，不要改变事实。\n" +
      "适合短内容或已基本成型的原创草稿。",
  },
  seed: {
    label: "种草增强",
    buttonLabel: "生成种草增强版",
    description: "适合内容太平，增强场景和转化",
    instruction:
      "保留事实和核心卖点，增强小红书种草感。\n" +
      "请加入更自然的使用场景、用户痛点、体验感和情绪表达，让内容更有吸引力。\n" +
      "表达要口语化、有分享感，但不要夸大效果，不要编造数据、价格、功效或个人经历。\n" +
      "如果原文信息不足，优先用更自然的表达承接，不要硬编细节。",
  },
};
