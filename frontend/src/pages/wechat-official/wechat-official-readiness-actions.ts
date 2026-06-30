import type { PlatformAction } from "../../platform-core/actions/platform-action-types";
import type { WechatOfficialReadiness } from "../../types";

export function buildWechatOfficialReadinessActions(readiness: WechatOfficialReadiness): PlatformAction[] {
  const checks = new Map(readiness.checks.map((check) => [check.key, check]));
  const actions: PlatformAction[] = [];
  const pushAction = (action: PlatformAction) => {
    if (!actions.some((item) => item.path === action.path && item.label === action.label)) actions.push(action);
  };

  if (checks.get("redfox.config")?.status !== "ready") {
    pushAction({ key: "redfox.config", label: "配置 Redfox", description: "先接通公众号爆文数据源", path: "/platforms/wechat-official/settings" });
  }
  if (readiness.content.total === 0) {
    pushAction({ key: "content.discovery", label: "去爆文发现", description: "采集公众号候选文章", path: "/platforms/wechat-official/discovery" });
  } else {
    pushAction({ key: "content.library", label: "查看内容库", description: "筛选、拆解、同步飞书分析", path: "/platforms/wechat-official/library" });
  }
  if (checks.get("feishu.analysis")?.status !== "ready" && readiness.content.total > 0) {
    pushAction({ key: "feishu.analysis", label: "处理飞书分析", description: "在内容库推送或回拉飞书标注", path: "/platforms/wechat-official/library" });
  }
  if (readiness.drafts.count === 0 && readiness.content.total > 0) {
    pushAction({ key: "drafts.workbench", label: "生成公众号草稿", description: "从已分析文章生成独立草稿", path: "/platforms/wechat-official/library" });
  }
  if (readiness.drafts.count > 0) {
    pushAction({ key: "image.studio", label: "整理封面/正文图", description: "从草稿进入图片工坊并回挂本地资产", path: "/platforms/wechat-official/drafts" });
  }
  if (!actions.length) {
    pushAction({ key: "dashboard.refresh", label: "刷新诊断", description: "重新读取当前工作区状态", path: "/platforms/wechat-official/dashboard" });
  }
  return actions.slice(0, 4);
}
