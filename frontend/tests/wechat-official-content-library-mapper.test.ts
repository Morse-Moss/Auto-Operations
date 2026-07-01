import assert from "node:assert/strict";

import {
  mapWechatOfficialArticleToContentItem,
  mapWechatOfficialCommentToContentComment,
  mapWechatOfficialImageToContentAsset,
  wechatOfficialDisplayTime,
  wechatOfficialPoolStatus,
  wechatOfficialReadStatusLabel,
} from "../src/pages/wechat-official/wechat-official-content-library-mapper.ts";
import type {
  WechatOfficialArticleComment,
  WechatOfficialContentDetail,
  WechatOfficialContentImage,
  WechatOfficialContentLibraryItem,
} from "../src/types/index.ts";

function article(overrides: Partial<WechatOfficialContentLibraryItem> = {}): WechatOfficialContentLibraryItem {
  return {
    id: 101,
    article_url: "https://mp.weixin.qq.com/s/article-101",
    title: "Article title",
    digest: "Article digest",
    author_name: "Official account",
    cover_url: "https://images.example/article-cover.jpg",
    publish_time_remote: "2026-06-30 08:00",
    is_candidate: true,
    latest_metric: {
      id: 1,
      article_id: 101,
      read_count: 12000,
      like_count: 300,
      wow_count: 40,
      share_count: 20,
      comment_count: 5,
    },
    analysis: {
      recommendation_status: "shortlisted",
      pool_status: "shortlisted",
      category: "私域增长",
      tags: ["案例", "转化"],
      is_favorite: true,
      read_status: "read",
      low_follower_evidence: true,
    },
    detail_status: {
      has_cover: true,
      has_text: true,
      has_html: true,
      image_count: 2,
      comment_count: 5,
      has_metrics: true,
      is_complete: true,
      completeness: "complete",
      next_actions: [],
      can_refresh_from_redfox: false,
    },
    ...overrides,
  };
}

function detail(overrides: Partial<WechatOfficialContentDetail> = {}): WechatOfficialContentDetail {
  return {
    article: article(),
    latest_metric: {
      id: 2,
      article_id: 101,
      read_count: 15000,
      like_count: 500,
      wow_count: 80,
      share_count: 30,
      comment_count: 8,
    },
    analysis: {},
    latest_snapshot: {
      id: 10,
      article_id: 101,
      status: "captured",
      html: "<p>Snapshot text</p>",
      text: "Snapshot text",
      images_json: [],
    },
    images: [
      { url: "https://images.example/detail-cover.jpg", type: "cover", alt: "cover" },
      { url: "https://images.example/detail-body.jpg", type: "content", alt: "body" },
    ],
    comments: { items: [], total: 0, available: true, source: "stored" },
    detail_status: article().detail_status,
    ...overrides,
  };
}

const mapped = mapWechatOfficialArticleToContentItem(article(), detail());
assert.equal(mapped.id, 101);
assert.equal(mapped.platform, "wechat_official");
assert.equal(mapped.title, "Article title");
assert.equal(mapped.content, "Snapshot text");
assert.equal(mapped.author_name, "Official account");
assert.equal(mapped.created_at, "2026-06-30 08:00");
assert.equal(mapped.read_count, 12000, "article latest_metric should win over detail fallback for list stability");
assert.equal(mapped.pool_status, "shortlisted");
assert.equal(mapped.recommendation_status, "shortlisted");
assert.equal(mapped.cover_url, "https://images.example/article-cover.jpg");
assert.deepEqual(mapped.tags.map((tag) => tag.name), ["已入库", "已有证据", "待补全", "正文/图片完整", "私域增长", "案例", "转化", "收藏", "已读"]);

const fallbackMapped = mapWechatOfficialArticleToContentItem(
  article({
    title: "",
    digest: "",
    author_name: "",
    cover_url: "",
    publish_time_remote: null,
    updated_at: "2026-06-29 12:00",
    latest_metric: null,
    analysis: { recommendation_status: "candidate" },
  }),
  detail({
    latest_snapshot: undefined,
    latest_metric: {
      id: 3,
      article_id: 101,
      read_count: 321,
      like_count: 0,
      wow_count: 0,
      share_count: 0,
      comment_count: 0,
    },
  }),
);
assert.equal(fallbackMapped.title, "公众号文章 #101");
assert.equal(fallbackMapped.content, "https://mp.weixin.qq.com/s/article-101");
assert.equal(fallbackMapped.author_name, "未知公众号");
assert.equal(fallbackMapped.created_at, "2026-06-29 12:00");
assert.equal(fallbackMapped.read_count, 321);
assert.equal(fallbackMapped.cover_url, "https://images.example/detail-cover.jpg");

const image: WechatOfficialContentImage = { url: "https://images.example/a.jpg", type: "content", alt: "A" };
assert.deepEqual(mapWechatOfficialImageToContentAsset(101, image, 2), {
  id: 3,
  note_id: 101,
  asset_type: "image",
  url: "https://images.example/a.jpg",
  local_path: "",
  download_url: "https://images.example/a.jpg",
  sort_order: 2,
});

const comment: WechatOfficialArticleComment = {
  comment_id: "comment-1",
  db_id: 501,
  user_name: "Reader",
  user_id: "user-1",
  content: "Useful article",
  like_count: 9,
  created_at_remote: "2026-06-30 09:00",
};
assert.deepEqual(mapWechatOfficialCommentToContentComment(101, comment, 0), {
  id: 501,
  note_id: 101,
  comment_id: "comment-1",
  user_name: "Reader",
  user_id: "user-1",
  content: "Useful article",
  like_count: 9,
  parent_comment_id: null,
  created_at_remote: "2026-06-30 09:00",
  raw_json: undefined,
});
assert.equal(mapWechatOfficialCommentToContentComment(101, { comment_id: "", content: "" }, 4).content, "", "mapper must not fabricate comment content");

assert.equal(wechatOfficialPoolStatus(article({ analysis: { recommendation_status: "draft_ready" } })), "draft_ready");
assert.equal(wechatOfficialDisplayTime(article({ publish_time_remote: null, updated_at: undefined, created_at: "2026-06-28" })), "2026-06-28");
assert.equal(wechatOfficialReadStatusLabel("reading"), "在读");
assert.equal(wechatOfficialReadStatusLabel(undefined), "未读");

console.log("wechat-official-content-library-mapper tests passed");
