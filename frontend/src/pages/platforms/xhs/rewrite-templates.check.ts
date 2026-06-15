import { DEFAULT_REWRITE_TEMPLATE_KEY, REWRITE_TEMPLATES } from "./rewrite-templates";

function assert(condition: boolean, message: string): void {
  if (!condition) {
    throw new Error(message);
  }
}

assert(DEFAULT_REWRITE_TEMPLATE_KEY === "safe", "safe rewrite should be the default template");
assert(REWRITE_TEMPLATES.safe.label === "安全改写", "safe template label should be operator-facing");
assert(REWRITE_TEMPLATES.safe.buttonLabel === "生成安全改写版", "safe template button label should match mode");
assert(REWRITE_TEMPLATES.safe.instruction.includes("不要逐句同义替换"), "safe template should prevent sentence-level synonym replacement");
assert(REWRITE_TEMPLATES.safe.instruction.includes("避免出现与原文明显相同"), "safe template should reduce source similarity");
assert(REWRITE_TEMPLATES.safe.instruction.includes("不新增未经原文支持"), "safe template should avoid unsupported claims");
assert(Object.keys(REWRITE_TEMPLATES).join(",") === "safe,polish,seed", "rewrite templates should expose exactly three modes");
assert(REWRITE_TEMPLATES.polish.description === "适合原创短文，只优化表达", "polish template description should explain usage");
assert(REWRITE_TEMPLATES.seed.description === "适合内容太平，增强场景和转化", "seed template description should explain usage");
