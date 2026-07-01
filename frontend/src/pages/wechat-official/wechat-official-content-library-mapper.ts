import type {
  ContentLibraryAsset,
  ContentLibraryComment,
  ContentLibraryItem,
} from "../../components/content-library";
import type {
  WechatOfficialArticleComment,
  WechatOfficialContentDetail,
  WechatOfficialContentImage,
  WechatOfficialContentLibraryItem,
} from "../../types";

export type WechatOfficialContentLibraryViewItem = ContentLibraryItem & {
  article: WechatOfficialContentLibraryItem;
  detail?: WechatOfficialContentDetail;
  read_count: number;
  pool_status: string;
  recommendation_status: string;
  cover_url: string;
};

export function wechatOfficialPoolStatus(article: WechatOfficialContentLibraryItem): string {
  return String(article.analysis?.pool_status || article.analysis?.recommendation_status || "candidate");
}

export function wechatOfficialDisplayTime(article: WechatOfficialContentLibraryItem): string {
  return article.publish_time_remote || article.updated_at || article.created_at || "";
}

export function wechatOfficialCurationTags(article: WechatOfficialContentLibraryItem) {
  const analysis = article.analysis || {};
  const tags: Array<{ id: number; name: string; color: string }> = [];
  if (analysis.category) tags.push({ id: 101, name: String(analysis.category), color: "cyan" });
  (analysis.tags || []).forEach((tag, index) => tags.push({ id: 200 + index, name: String(tag), color: "geekblue" }));
  if (analysis.is_favorite) tags.push({ id: 301, name: "收藏", color: "gold" });
  tags.push({ id: 302, name: wechatOfficialReadStatusLabel(analysis.read_status), color: analysis.read_status === "read" ? "green" : "default" });
  return tags;
}

export function wechatOfficialReadStatusLabel(value?: string): string {
  if (value === "read") return "已读";
  if (value === "reading") return "在读";
  return "未读";
}

export function mapWechatOfficialArticleToContentItem(
  article: WechatOfficialContentLibraryItem,
  detail?: WechatOfficialContentDetail,
): WechatOfficialContentLibraryViewItem {
  return {
    id: article.id,
    platform: "wechat_official",
    title: article.title || `公众号文章 #${article.id}`,
    content: detail?.latest_snapshot?.text || article.digest || article.article_url || "",
    author_name: article.author_name || "未知公众号",
    created_at: wechatOfficialDisplayTime(article),
    tags: wechatOfficialDerivedTags(article),
    article,
    detail,
    read_count: Number(article.latest_metric?.read_count ?? detail?.latest_metric?.read_count ?? 0),
    pool_status: wechatOfficialPoolStatus(article),
    recommendation_status: String(article.analysis?.recommendation_status || ""),
    cover_url: article.cover_url || detail?.images?.find((image) => image.type === "cover")?.url || detail?.images?.[0]?.url || "",
  };
}

export function mapWechatOfficialImageToContentAsset(itemId: number, image: WechatOfficialContentImage, index: number): ContentLibraryAsset {
  return {
    id: index + 1,
    note_id: itemId,
    asset_type: "image",
    url: image.url,
    local_path: "",
    download_url: image.url,
    sort_order: index,
  };
}

export function mapWechatOfficialCommentToContentComment(itemId: number, comment: WechatOfficialArticleComment, index: number): ContentLibraryComment {
  return {
    id: comment.db_id ?? index + 1,
    note_id: itemId,
    comment_id: comment.comment_id || String(index + 1),
    user_name: comment.user_name || "匿名读者",
    user_id: comment.user_id || null,
    content: comment.content || "",
    like_count: Number(comment.like_count ?? 0),
    parent_comment_id: null,
    created_at_remote: comment.created_at_remote || null,
    raw_json: undefined,
  };
}

function wechatOfficialDerivedTags(article: WechatOfficialContentLibraryItem) {
  const tags: Array<{ id: number; name: string; color: string }> = [
    { id: 1, name: wechatOfficialPoolStatusLabel(wechatOfficialPoolStatus(article)), color: wechatOfficialStatusColor(wechatOfficialPoolStatus(article)) },
    { id: 2, name: wechatOfficialLowFollowerLabel(article), color: "blue" },
    { id: 3, name: wechatOfficialMaterialLabel(article), color: "purple" },
    { id: 4, name: wechatOfficialCompletenessLabel(article), color: article.detail_status?.is_complete ? "green" : "gold" },
    ...wechatOfficialCurationTags(article),
  ];
  return tags.filter((tag, index, list) => list.findIndex((candidate) => candidate.name === tag.name) === index);
}

function wechatOfficialPoolStatusLabel(status?: string): string {
  const labels: Record<string, string> = {
    candidate: "候选",
    shortlisted: "已入库",
    analyzing: "拆解中",
    draft_ready: "草稿已生成",
    rejected: "已拒绝",
    archived: "已归档",
  };
  return labels[status || ""] || status || "候选";
}

function wechatOfficialStatusColor(status?: string): string {
  if (!status) return "default";
  if (["blocked", "expired", "invalid", "failed", "rejected"].includes(status)) return "red";
  if (["planned", "partial", "pending", "unknown", "analyzing"].includes(status)) return "gold";
  if (["available", "valid", "active", "succeeded", "completed", "shortlisted"].includes(status)) return "green";
  if (["draft_ready"].includes(status)) return "purple";
  return "default";
}

function wechatOfficialLowFollowerLabel(article: WechatOfficialContentLibraryItem): string {
  const value = article.analysis?.low_follower_evidence;
  if (value === "manual") return "人工确认";
  if (value === "inferred") return "Redfox 推断";
  if (value === true) return "已有证据";
  if (value === false) return "无证据";
  return "未知";
}

function wechatOfficialMaterialLabel(article: WechatOfficialContentLibraryItem): string {
  const analysis = article.analysis || {};
  if (analysis.pool_status === "draft_ready") return "草稿已生成";
  if (analysis.analysis_mode) return "已拆解";
  return "待补全";
}

function wechatOfficialCompletenessLabel(article: WechatOfficialContentLibraryItem): string {
  const completeness = article.detail_status?.completeness;
  if (completeness === "complete") return "正文/图片完整";
  if (completeness === "partial") return "部分补全";
  return "待补正文素材";
}
