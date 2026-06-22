import type { WechatOfficialCreateDraftPayload } from "../../types";

export type WechatOfficialDraftTemplate = Required<Pick<
  WechatOfficialCreateDraftPayload,
  "rewrite_style" | "target_audience" | "call_to_action" | "template_key" | "template_name" | "template_instruction" | "opening_angle"
>>;

export const WECHAT_DRAFT_TEMPLATES: WechatOfficialDraftTemplate[] = [
  {
    template_key: "case_rewrite",
    template_name: "案例拆解",
    rewrite_style: "保留爆文结构，提炼可复用案例价值",
    target_audience: "私域运营和内容负责人",
    call_to_action: "关注后续更新",
    template_instruction: "按 背景-冲突-方法-结果-启发 组织二创草稿。",
    opening_angle: "从爆文结构拆解可复用方法",
  },
  {
    template_key: "insight_commentary",
    template_name: "观点评论",
    rewrite_style: "提炼核心观点，加入克制评论",
    target_audience: "行业观察者和管理者",
    call_to_action: "欢迎留言交流",
    template_instruction: "按 现象-判断-原因-建议 组织公众号评论稿。",
    opening_angle: "用运营视角解释这篇文章为什么能传播",
  },
  {
    template_key: "practical_guide",
    template_name: "实操清单",
    rewrite_style: "转成可执行方法论",
    target_audience: "一线运营和创业者",
    call_to_action: "收藏并复盘自己的业务",
    template_instruction: "按 问题-步骤-注意事项-复盘清单 组织。",
    opening_angle: "把爆文观点转成可落地的操作步骤",
  },
];
