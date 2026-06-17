import {
  CheckCircleOutlined,
  CloseCircleOutlined,
  CloudDownloadOutlined,
  CommentOutlined,
  FileExcelOutlined,
  LinkOutlined,
  LoadingOutlined,
  ReloadOutlined,
  SearchOutlined,
  SettingOutlined,
} from "@ant-design/icons";
import { Alert, Button, Card, Checkbox, Col, Collapse, Empty, Form, Input, InputNumber, Radio, Row, Select, Space, Spin, Table, Tag, Typography } from "antd";
import type { ColumnsType } from "antd/es/table";
import { FormEvent, useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { crawlXhsDataStream, crawlXhsKeywordGroupStream, fetchAccounts, fetchKeywordGroups } from "../../../lib/api";
import type { KeywordGroup, PlatformAccount, XhsDataCrawlItem, XhsDataCrawlMode, XhsKeywordGroupCrawlSummary } from "../../../types";

const { Title, Text } = Typography;

const sortOptions = [
  { value: 0, label: "综合排序" },
  { value: 1, label: "最新" },
  { value: 2, label: "最多点赞" },
  { value: 3, label: "最多评论" },
  { value: 4, label: "最多收藏" },
];
const noteTypeOptions = [
  { value: 0, label: "不限类型" },
  { value: 1, label: "视频笔记" },
  { value: 2, label: "普通笔记" },
];
const noteTimeOptions = [
  { value: 0, label: "不限时间" },
  { value: 1, label: "一天内" },
  { value: 2, label: "一周内" },
  { value: 3, label: "半年内" },
];
const noteRangeOptions = [
  { value: 0, label: "不限范围" },
  { value: 1, label: "已看过" },
  { value: 2, label: "未看过" },
  { value: 3, label: "已关注" },
];
const distanceOptions = [
  { value: 0, label: "不限距离" },
  { value: 1, label: "同城" },
  { value: 2, label: "附近" },
];

type CrawlChannel = "keyword_group" | "manual_keyword";

function splitUrls(value: string): string[] {
  return value.split(/\r?\n|,/).map((url) => url.trim()).filter(Boolean);
}

function escapeHtml(value: unknown): string {
  return String(value ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

const noteExcelHeaders = [
  "笔记id", "笔记url", "笔记类型", "用户id", "用户主页url", "昵称", "头像url", "标题", "描述",
  "点赞数量", "收藏数量", "评论数量", "分享数量", "视频封面url", "视频地址url", "图片地址url列表",
  "标签", "上传时间", "ip归属地",
];

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : {};
}
function firstRecord(value: unknown): Record<string, unknown> {
  return Array.isArray(value) && value.length > 0 ? asRecord(value[0]) : {};
}
function textValue(...values: unknown[]): string {
  for (const value of values) {
    if (value !== undefined && value !== null && String(value).trim() !== "") return String(value);
  }
  return "";
}
function listValue(value: unknown): string {
  if (Array.isArray(value)) return value.map((item) => String(item ?? "")).filter(Boolean).join("\n");
  return textValue(value);
}
function dateText(value: unknown): string {
  const numberValue = typeof value === "number" ? value : Number(value);
  if (!Number.isFinite(numberValue) || numberValue <= 0) return textValue(value);
  const date = new Date(numberValue > 10_000_000_000 ? numberValue : numberValue * 1000);
  return Number.isNaN(date.getTime()) ? "" : date.toLocaleString();
}
function rawNoteItem(note: XhsDataCrawlItem["note"]): Record<string, unknown> {
  const raw = asRecord(note?.raw);
  const data = asRecord(raw.data);
  const firstItem = firstRecord(data.items);
  return Object.keys(firstItem).length > 0 ? firstItem : raw;
}
function rawNoteCard(note: XhsDataCrawlItem["note"]): Record<string, unknown> {
  const item = rawNoteItem(note);
  const noteCard = asRecord(item.note_card);
  const notePayload = asRecord(item.note);
  if (Object.keys(noteCard).length > 0) return noteCard;
  if (Object.keys(notePayload).length > 0) return notePayload;
  return item;
}
function noteTypeText(value: unknown): string {
  const text = textValue(value);
  if (text === "normal") return "图集";
  if (text === "video") return "视频";
  return text;
}

function spiderStyleNoteRow(item: XhsDataCrawlItem): string[] {
  const note = item.note;
  if (!note) return noteExcelHeaders.map(() => "");
  const rawItem = rawNoteItem(note);
  const card = rawNoteCard(note);
  const cardUser = asRecord(card.user);
  const cardAuthor = asRecord(card.author);
  const author = Object.keys(cardUser).length > 0 ? cardUser : cardAuthor;
  const cardInteract = asRecord(card.interact_info);
  const cardInteraction = asRecord(card.interaction);
  const interact = Object.keys(cardInteract).length > 0 ? cardInteract : cardInteraction;
  const video = asRecord(card.video);
  const videoMedia = asRecord(video.media);
  const stream = asRecord(videoMedia.stream);
  const h264 = firstRecord(stream.h264);
  const user_id = textValue(note.author_id, author.user_id, author.id);
  const note_url = textValue(note.note_url, card.note_url, card.url, rawItem.note_url, rawItem.url, item.source.startsWith("http") ? item.source : "");
  const upload_time = dateText(textValue(card.time, card.create_time, rawItem.time, rawItem.create_time));
  const originVideoKey = textValue(asRecord(video.consumer).origin_video_key);
  const video_addr = textValue(h264.master_url, h264.url, originVideoKey ? `https://sns-video-bd.xhscdn.com/${originVideoKey}` : "");
  return [
    textValue(note.note_id, card.note_id, card.id, rawItem.id), note_url,
    noteTypeText(textValue(note.type, card.type, rawItem.model_type)),
    user_id, user_id ? `https://www.xiaohongshu.com/user/profile/${user_id}` : "",
    textValue(note.author_name, author.nickname, author.name),
    textValue(note.author_avatar, author.avatar, author.avatar_url),
    textValue(note.title, card.title, card.display_title),
    textValue(note.content, card.desc, card.content),
    textValue(note.likes, interact.liked_count, interact.likes),
    textValue(note.collects, interact.collected_count, interact.collects),
    textValue(note.comments, interact.comment_count, interact.comments),
    textValue(note.shares, interact.share_count, interact.shares),
    textValue(note.cover_url, video.cover_url), video_addr,
    listValue(note.image_urls?.length ? note.image_urls : note.cover_url ? [note.cover_url] : []),
    listValue(note.tags), upload_time, textValue(card.ip_location, rawItem.ip_location),
  ];
}

function commentStatusLabel(status?: string): string {
  if (status === "success") return "成功";
  if (status === "failed") return "失败";
  if (status === "rate_limited") return "限流";
  if (status === "skipped_rate_limited") return "限流跳过";
  return "未抓取";
}

function commentStatusTag(item: XhsDataCrawlItem) {
  const label = commentStatusLabel(item.comment_status);
  if (item.comment_status === "success") return <Tag color="success">{label}</Tag>;
  if (item.comment_status === "rate_limited" || item.comment_status === "skipped_rate_limited") return <Tag color="warning">{label}</Tag>;
  if (item.comment_status === "failed") return <Tag color="error">{label}</Tag>;
  return <Text type="secondary">{label}</Text>;
}

function crawlStatusTag(status: string) {
  if (status === "success") return <Tag icon={<CheckCircleOutlined />} color="success">成功</Tag>;
  if (status === "partial") return <Tag color="warning">部分</Tag>;
  if (status === "skipped") return <Tag color="default">跳过</Tag>;
  if (status === "failed") return <Tag icon={<CloseCircleOutlined />} color="error">失败</Tag>;
  return <Tag>{status || "未知"}</Tag>;
}

function qualityStatusLabel(status?: string): string {
  if (status === "valid_detail") return "详情有效";
  if (status === "search_card_only") return "仅搜索卡片";
  if (status === "invalid_source_url") return "链接缺参数";
  if (status === "empty_detail_payload") return "详情为空";
  if (status === "rate_limited") return "访问频繁";
  if (status === "account_expired") return "登录过期";
  return status || "待确认";
}

function qualityStatusTag(item: XhsDataCrawlItem) {
  const label = qualityStatusLabel(item.quality_status);
  if (item.quality_status === "valid_detail") return <Tag color="success">{label}</Tag>;
  if (item.quality_status === "search_card_only") return <Tag color="warning">{label}</Tag>;
  if (item.quality_status === "rate_limited" || item.quality_status === "account_expired") return <Tag color="error">{label}</Tag>;
  if (item.quality_status === "invalid_source_url" || item.quality_status === "empty_detail_payload") return <Tag color="warning">{label}</Tag>;
  return <Text type="secondary">{label}</Text>;
}

function diagnosticKindLabel(kind?: string | null): string {
  if (kind === "missing_xsec_token_short_explore") return "缺 xsec_token";
  if (kind === "xhs_rate_limited") return "访问频繁";
  if (kind === "xhs_account_expired") return "登录过期";
  if (kind === "search_api_failed") return "搜索接口失败";
  if (kind === "empty_detail_payload") return "详情为空";
  if (kind === "detail_api_failed") return "详情接口失败";
  if (kind === "invalid_note_identity") return "笔记 ID 异常";
  return kind || "-";
}

function diagnosticKindTag(item: XhsDataCrawlItem) {
  const kind = item.diagnostic_kind || item.save_diagnostic_kind;
  if (!kind) return <Text type="secondary">-</Text>;
  if (kind === "missing_xsec_token_short_explore" || kind === "xhs_account_expired" || kind === "search_api_failed") return <Tag color="error">{diagnosticKindLabel(kind)}</Tag>;
  if (kind === "xhs_rate_limited") return <Tag color="warning">{diagnosticKindLabel(kind)}</Tag>;
  return <Tag color="default">{diagnosticKindLabel(kind)}</Tag>;
}

function savedStatusTag(item: XhsDataCrawlItem) {
  if (item.saved) return <Tag color="success">已入库</Tag>;
  if (item.quality_status && item.quality_status !== "valid_detail") return <Tag color="warning">未入库</Tag>;
  return <Text type="secondary">-</Text>;
}

function exportRowsToExcel(items: XhsDataCrawlItem[]) {
  const rows = items.map((item) => [
    item.status,
    item.source,
    item.error,
    item.comment_status || "",
    item.comment_error || "",
    item.quality_status || "",
    item.diagnostic_kind || "",
    item.save_diagnostic_kind || "",
    item.user_message || "",
    item.recoverable ? "是" : "否",
    item.saved ? "是" : "否",
    ...spiderStyleNoteRow(item),
    item.comment_count,
    (item.comments ?? []).map((c) => c.content).join("\n"),
  ]);
  const headers = [
    "抓取状态",
    "来源",
    "错误",
    "评论状态",
    "评论错误",
    "质量状态",
    "诊断类型",
    "保存诊断",
    "用户提示",
    "是否可恢复",
    "是否已入库",
    ...noteExcelHeaders,
    "抓取评论数",
    "评论内容",
  ];
  const table = [headers, ...rows].map((row) => `<tr>${row.map((cell) => `<td>${escapeHtml(cell)}</td>`).join("")}</tr>`).join("");
  const html = `<html><head><meta charset="UTF-8"></head><body><table>${table}</table></body></html>`;
  const blob = new Blob([html], { type: "application/vnd.ms-excel;charset=utf-8" });
  const url = window.URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `xhs-crawl-${Date.now()}.xls`;
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.URL.revokeObjectURL(url);
}

export function XhsCrawlerPage() {
  const [searchParams] = useSearchParams();
  const parsedKeywordGroupId = Number(searchParams.get("keyword_group_id") || 0);
  const queryKeywordGroupId = Number.isFinite(parsedKeywordGroupId) && parsedKeywordGroupId > 0 ? parsedKeywordGroupId : null;
  const parsedKeywordLimit = Number(searchParams.get("keyword_limit") || 0);
  const queryKeywordLimit = Number.isFinite(parsedKeywordLimit) && parsedKeywordLimit > 0 ? Math.min(20, Math.max(1, parsedKeywordLimit)) : null;
  const parsedMaxNotesPerKeyword = Number(searchParams.get("max_notes_per_keyword") || 0);
  const queryMaxNotesPerKeyword = Number.isFinite(parsedMaxNotesPerKeyword) && parsedMaxNotesPerKeyword > 0 ? Math.min(50, Math.max(1, parsedMaxNotesPerKeyword)) : null;
  const queryFetchComments = searchParams.get("fetch_comments") === "1";
  const fromAnalysisRecheck = searchParams.get("analysis_recheck") === "1";
  const [accounts, setAccounts] = useState<PlatformAccount[]>([]);
  const [keywordGroups, setKeywordGroups] = useState<KeywordGroup[]>([]);
  const [selectedAccountId, setSelectedAccountId] = useState<number | null>(null);
  const [selectedKeywordGroupId, setSelectedKeywordGroupId] = useState<number | null>(queryKeywordGroupId);
  const [crawlChannel, setCrawlChannel] = useState<CrawlChannel>(queryKeywordGroupId ? "keyword_group" : "manual_keyword");
  const [keywordLimit, setKeywordLimit] = useState(queryKeywordLimit ?? 5);
  const [maxNotesPerKeyword, setMaxNotesPerKeyword] = useState(queryMaxNotesPerKeyword ?? 5);
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [summaryMessage, setSummaryMessage] = useState<string | null>(null);
  const [keywordGroupSummary, setKeywordGroupSummary] = useState<XhsKeywordGroupCrawlSummary | null>(null);
  const [mode, setMode] = useState<XhsDataCrawlMode>("search");
  const [urls, setUrls] = useState("");
  const [keyword, setKeyword] = useState("");
  const [pages, setPages] = useState(1);
  const [maxNotes, setMaxNotes] = useState(20);
  const [timeSleep, setTimeSleep] = useState(1);
  const [commentSleep, setCommentSleep] = useState(5);
  const [fetchCommentsChecked, setFetchCommentsChecked] = useState(queryFetchComments);
  const [filters, setFilters] = useState({ sort_type_choice: 0, note_type: 0, note_time: 0, note_range: 0, pos_distance: 0, geo: "" });
  const [items, setItems] = useState<XhsDataCrawlItem[]>([]);
  const [successCount, setSuccessCount] = useState(0);
  const [failedCount, setFailedCount] = useState(0);
  const [progressMsg, setProgressMsg] = useState<string | null>(null);
  const [isLoadingAccounts, setIsLoadingAccounts] = useState(true);
  const [isRunning, setIsRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const pcAccounts = useMemo(() => accounts.filter((a) => a.platform === "xhs" && a.sub_type === "pc"), [accounts]);
  const activePcAccounts = useMemo(() => pcAccounts.filter((a) => a.status === "active"), [pcAccounts]);
  const selectedAccount = useMemo(() => pcAccounts.find((account) => account.id === selectedAccountId) || null, [pcAccounts, selectedAccountId]);
  const selectedKeywordGroup = useMemo(() => keywordGroups.find((group) => group.id === selectedKeywordGroupId) || null, [keywordGroups, selectedKeywordGroupId]);
  const isKeywordGroupMode = crawlChannel === "keyword_group";
  const commentRateLimitedCount = useMemo(() => items.filter((item) => item.comment_status === "rate_limited").length, [items]);
  const commentSkippedCount = useMemo(() => items.filter((item) => item.comment_status === "skipped_rate_limited").length, [items]);
  const lowQualityCount = useMemo(() => items.filter((item) => item.quality_status && item.quality_status !== "valid_detail").length, [items]);
  const savedCount = useMemo(() => items.filter((item) => item.saved).length, [items]);

  async function loadAccounts() {
    setIsLoadingAccounts(true);
    setError(null);
    try {
      const loaded = await fetchAccounts("xhs");
      setAccounts(loaded);
      const pc = loaded.filter((a) => a.sub_type === "pc");
      const active = pc.filter((a) => a.status === "active");
      setSelectedAccountId((current) => {
        if (current && active.some((account) => account.id === current)) return current;
        return active[0]?.id ?? pc[0]?.id ?? null;
      });
    } catch { setError("账号列表加载失败。"); }
    finally { setIsLoadingAccounts(false); }
  }

  async function loadKeywordGroups() {
    try {
      const result = await fetchKeywordGroups("xhs");
      setKeywordGroups(result.items);
      setSelectedKeywordGroupId((current) => {
        if (current && result.items.some((group) => group.id === current)) return current;
        return null;
      });
    } catch { setError("关键词组加载失败。"); }
  }

  function handleChannelChange(nextChannel: CrawlChannel) {
    setCrawlChannel(nextChannel);
    if (nextChannel === "manual_keyword") {
      setMode("search");
    }
  }

  async function handleSimpleRun() {
    setError(null);
    setSummaryMessage(null);
    setKeywordGroupSummary(null);
    if (!selectedAccountId) { setError("请先选择一个可用的 PC 账号。"); return; }
    if (selectedAccount?.status === "expired") { setError("当前 PC 账号已过期，请切换到 active 账号或重新登录。"); return; }
    if (!selectedKeywordGroupId) { setError("请先选择一个关键词组。"); return; }
    setIsRunning(true);
    setItems([]);
    setSuccessCount(0);
    setFailedCount(0);
    setProgressMsg(null);
    try {
      const summary = await crawlXhsKeywordGroupStream(
        {
          account_id: selectedAccountId,
          keyword_group_id: selectedKeywordGroupId,
          keyword_limit: keywordLimit,
          max_notes_per_keyword: maxNotesPerKeyword,
          time_sleep: timeSleep,
          comment_sleep: commentSleep,
          fetch_comments: fetchCommentsChecked,
          sort_type_choice: filters.sort_type_choice,
          note_type: filters.note_type,
          note_time: filters.note_time,
        },
        (_index, item) => { setItems((prev) => [...prev, item]); },
        (msg) => { setProgressMsg(msg); },
        (msg) => { setError(msg); },
      );
      setKeywordGroupSummary(summary);
      setSuccessCount(summary.success_count);
      setFailedCount(summary.failed_count);
      setSummaryMessage(summary.summary_message || `采集完成：保存 ${summary.saved_count} 条，跳过 ${summary.skipped_count} 条。`);
      setProgressMsg(null);
    } catch (err: unknown) {
      const axiosErr = err as { message?: string };
      setError(axiosErr?.message || "关键词组采集失败");
    }
    finally { setIsRunning(false); }
  }

  async function handleRun(e?: FormEvent) {
    e?.preventDefault();
    setError(null);
    setSummaryMessage(null);
    setKeywordGroupSummary(null);
    if (isKeywordGroupMode) { await handleSimpleRun(); return; }
    if (!selectedAccountId) { setError("请先选择一个可用的 PC 账号。"); return; }
    if (selectedAccount?.status === "expired") { setError("当前 PC 账号已过期，请切换到 active 账号或重新登录。"); return; }
    const parsedUrls = splitUrls(urls);
    if (mode !== "search" && parsedUrls.length === 0) { setError("请至少输入一个笔记链接。"); return; }
    if (mode === "search" && !keyword.trim()) { setError("请填写搜索关键词。"); return; }
    setIsRunning(true);
    setItems([]);
    setSuccessCount(0);
    setFailedCount(0);
    setProgressMsg(null);
    try {
      const summary = await crawlXhsDataStream(
        { account_id: selectedAccountId, mode, urls: parsedUrls, keyword: keyword.trim(), pages, max_notes: maxNotes, time_sleep: timeSleep, comment_sleep: commentSleep, fetch_comments: mode === "comments" ? false : fetchCommentsChecked, ...filters, geo: filters.geo.trim() },
        (index, item) => { setItems((prev) => [...prev, item]); },
        (msg) => { setProgressMsg(msg); },
        (msg) => { setError(msg); },
      );
      setSuccessCount(summary.success_count);
      setFailedCount(summary.failed_count);
      setProgressMsg(null);
    } catch (err: unknown) {
      const axiosErr = err as { message?: string };
      setError(axiosErr?.message || "抓取失败");
    }
    finally { setIsRunning(false); }
  }

  useEffect(() => {
    if (queryKeywordGroupId) {
      setSelectedKeywordGroupId(queryKeywordGroupId);
      setCrawlChannel("keyword_group");
      return;
    }
    setSelectedKeywordGroupId(null);
    setCrawlChannel("manual_keyword");
    setMode("search");
  }, [queryKeywordGroupId]);

  useEffect(() => { void loadAccounts(); void loadKeywordGroups(); }, []);

  const noPcAccount = !isLoadingAccounts && pcAccounts.length === 0;

  const columns: ColumnsType<XhsDataCrawlItem> = [
    { title: "状态", dataIndex: "status", width: 80, render: (status: string) => crawlStatusTag(status) },
    { title: "质量", key: "quality_status", width: 120, render: (_, item) => qualityStatusTag(item) },
    { title: "诊断", key: "diagnostic_kind", width: 130, render: (_, item) => diagnosticKindTag(item) },
    { title: "提示", key: "user_message", width: 220, ellipsis: true, render: (_, item) => item.user_message ? <Text type="secondary" style={{ fontSize: 12 }}>{item.user_message}</Text> : "-" },
    { title: "入库", key: "saved", width: 90, render: (_, item) => savedStatusTag(item) },
    { title: "关键词", dataIndex: "keyword", width: 110, render: (value: string) => value || "-" },
    { title: "来源", dataIndex: "source", width: 200, ellipsis: true },
    { title: "标题", key: "title", width: 200, ellipsis: true, render: (_, item) => item.note?.title || "-" },
    { title: "作者", key: "author", width: 100, render: (_, item) => item.note?.author_name || "-" },
    { title: "互动", key: "engagement", width: 180, render: (_, item) => item.note ? <Text type="secondary" style={{ fontSize: 12 }}>赞{item.note.likes} 藏{item.note.collects} 评{item.note.comments}</Text> : "-" },
    { title: "评论", key: "comments", width: 80, render: (_, item) => <Space size={4}><CommentOutlined />{item.comment_count}</Space> },
    { title: "评论状态", key: "comment_status", width: 110, render: (_, item) => commentStatusTag(item) },
    { title: "错误", key: "error", ellipsis: true, render: (_, item) => {
      const message = item.error || item.comment_error || "";
      return message ? <Text type="danger" style={{ fontSize: 12 }}>{message}</Text> : "-";
    } },
  ];

  return (
    <div>
      <Row justify="space-between" align="middle" style={{ marginBottom: 24 }}>
        <Col>
          <Title level={4} style={{ margin: 0 }}>数据抓取</Title>
          <Text type="secondary">搜索结果、笔记详情和评论抓取，失败项单独标注并可导出 Excel</Text>
        </Col>
        <Col>
          <Button icon={<ReloadOutlined />} onClick={() => { void loadAccounts(); void loadKeywordGroups(); }} loading={isLoadingAccounts}>刷新账号和关键词组</Button>
        </Col>
      </Row>

      <Card style={{ marginBottom: 24 }}>
        <Form layout="vertical" onFinish={() => void handleRun()}>
          <Alert
            type="info"
            showIcon
            message="选择采集通道"
            description="关键词组适合计划内批量采集；手动关键词适合临时验证选题。系统会低频搜索、获取详情，只保存有效内容，并在结束后汇总保存和跳过原因。"
            style={{ marginBottom: 16 }}
          />

          <Row gutter={16}>
            <Col xs={24} md={8}>
              <Form.Item label="PC 账号">
                <Select
                  value={selectedAccountId}
                  onChange={setSelectedAccountId}
                  placeholder="选择 PC 账号"
                  status={selectedAccount?.status === "expired" ? "error" : undefined}
                  options={[...activePcAccounts, ...pcAccounts.filter((a) => a.status !== "active")].map((a) => ({
                    value: a.id,
                    label: `${a.nickname || `PC 账号 ${a.id}`} · ${a.status}`,
                    disabled: a.status === "expired",
                  }))}
                />
              </Form.Item>
            </Col>
            <Col xs={24} md={16}>
              <Form.Item label="采集通道">
                <Radio.Group value={crawlChannel} onChange={(e) => handleChannelChange(e.target.value as CrawlChannel)}>
                  <Radio.Button value="keyword_group">关键词组采集</Radio.Button>
                  <Radio.Button value="manual_keyword">手动关键词</Radio.Button>
                </Radio.Group>
              </Form.Item>
            </Col>
          </Row>

          {fromAnalysisRecheck && (
            <Alert
              type="info"
              showIcon
              message="正在补齐分析中心缺失数据"
              description={`已按分析中心建议预填关键词组${queryMaxNotesPerKeyword ? `、每词 ${queryMaxNotesPerKeyword} 条` : ""}${queryFetchComments ? "，并开启评论采集" : ""}。请确认 PC 账号后点击下方按钮开始补采，采集完成后回到分析中心重新检查。`}
              action={<Link to={selectedKeywordGroupId ? `/platforms/xhs/analytics?keyword_group_id=${selectedKeywordGroupId}` : "/platforms/xhs/analytics"}>回到分析中心</Link>}
              style={{ marginBottom: 16 }}
            />
          )}

          {isKeywordGroupMode ? (
            <>
              <Row gutter={16}>
                <Col xs={24} md={8}>
                  <Form.Item label="关键词组">
                    <Select
                      allowClear
                      value={selectedKeywordGroupId ?? undefined}
                      onChange={(value) => setSelectedKeywordGroupId(value ?? null)}
                      placeholder="选择关键词组一键采集"
                      options={keywordGroups.map((group) => ({ value: group.id, label: `${group.name} · ${group.keywords.length} 词` }))}
                    />
                  </Form.Item>
                </Col>
                <Col xs={12} md={4}>
                  <Form.Item label="关键词数">
                    <InputNumber min={1} max={20} value={keywordLimit} onChange={(v) => setKeywordLimit(v ?? 5)} style={{ width: "100%" }} />
                  </Form.Item>
                </Col>
                <Col xs={12} md={4}>
                  <Form.Item label="每词最多">
                    <InputNumber min={1} max={50} value={maxNotesPerKeyword} onChange={(v) => setMaxNotesPerKeyword(v ?? 5)} style={{ width: "100%" }} />
                  </Form.Item>
                </Col>
              </Row>
              {selectedKeywordGroup ? (
                <Alert
                  type="success"
                  showIcon
                  message={`将采集「${selectedKeywordGroup.name}」前 ${Math.min(keywordLimit, selectedKeywordGroup.keywords.length)} 个关键词，每个关键词最多 ${maxNotesPerKeyword} 条。`}
                  style={{ marginBottom: 16 }}
                />
              ) : null}
            </>
          ) : (
            <>
              {mode === "search" ? (
                <>
                  <Alert
                    type="success"
                    showIcon
                    message="手动关键词采集"
                    description="输入一个关键词后，系统会按搜索结果抓取详情。适合临时验证选题、探索新关键词。"
                    style={{ marginBottom: 16 }}
                  />
                  <Row gutter={16}>
                    <Col xs={24} md={8}>
                      <Form.Item label="搜索关键词">
                        <Input value={keyword} onChange={(e) => setKeyword(e.target.value)} placeholder="低卡早餐、通勤穿搭" />
                      </Form.Item>
                    </Col>
                    <Col xs={12} md={4}>
                      <Form.Item label="爬取数量">
                        <InputNumber min={1} max={200} value={maxNotes} onChange={(v) => { const n = v ?? 20; setMaxNotes(n); setPages(Math.max(1, Math.ceil(n / 20))); }} style={{ width: "100%" }} />
                      </Form.Item>
                    </Col>
                    <Col xs={12} md={4}>
                      <Form.Item label="排序">
                        <Select value={filters.sort_type_choice} onChange={(v) => setFilters((c) => ({ ...c, sort_type_choice: v }))} options={sortOptions} />
                      </Form.Item>
                    </Col>
                    <Col xs={12} md={4}>
                      <Form.Item label="类型">
                        <Select value={filters.note_type} onChange={(v) => setFilters((c) => ({ ...c, note_type: v }))} options={noteTypeOptions} />
                      </Form.Item>
                    </Col>
                    <Col xs={12} md={4}>
                      <Form.Item label="时间范围">
                        <Select value={filters.note_time} onChange={(v) => setFilters((c) => ({ ...c, note_time: v }))} options={noteTimeOptions} />
                      </Form.Item>
                    </Col>
                    <Col xs={12} md={4}>
                      <Form.Item label="距离">
                        <Select value={filters.pos_distance} onChange={(v) => setFilters((c) => ({ ...c, pos_distance: v }))} options={distanceOptions} />
                      </Form.Item>
                    </Col>
                    <Col xs={12} md={4}>
                      <Form.Item label="Geo">
                        <Input value={filters.geo} onChange={(e) => setFilters((c) => ({ ...c, geo: e.target.value }))} placeholder="经纬度" />
                      </Form.Item>
                    </Col>
                  </Row>
                </>
              ) : (
                <Form.Item label="笔记链接">
                  <Input.TextArea value={urls} onChange={(e) => setUrls(e.target.value)} placeholder="每行一个链接，也可以用英文逗号分隔" rows={4} />
                </Form.Item>
              )}

              <Collapse
                ghost
                items={[{
                  key: "secondary-crawl-modes",
                  label: <Space><CloudDownloadOutlined />更多抓取方式（笔记链接 / 评论）</Space>,
                  children: (
                    <Row gutter={16}>
                      <Col xs={24} md={8}>
                        <Form.Item label="辅助抓取方式">
                          <Select
                            value={mode}
                            onChange={(value) => setMode(value)}
                            options={[
                              { value: "search", label: "通过搜索爬取详情" },
                              { value: "note_urls", label: "直接爬取笔记链接" },
                              { value: "comments", label: "只爬取评论" },
                            ]}
                          />
                        </Form.Item>
                      </Col>
                    </Row>
                  ),
                }]}
                style={{ marginBottom: 8 }}
              />
            </>
          )}

          <Row gutter={16}>
            <Col span={8} style={{ display: "flex", alignItems: "center", paddingTop: 8 }}>
              <Checkbox checked={fetchCommentsChecked} onChange={(e) => setFetchCommentsChecked(e.target.checked)} disabled={!isKeywordGroupMode && mode === "comments"}>同时抓取评论</Checkbox>
            </Col>
          </Row>

          {isKeywordGroupMode ? (
            <Collapse
              ghost
              activeKey={showAdvanced ? ["advanced"] : []}
              onChange={(keys) => setShowAdvanced(Array.isArray(keys) ? keys.includes("advanced") : keys === "advanced")}
              items={[{
                key: "advanced",
                label: <Space><SettingOutlined />高级设置</Space>,
                children: <Row gutter={16}>
                  <Col span={4}><Form.Item label="Time Sleep"><InputNumber min={0} max={60} step={0.5} value={timeSleep} onChange={(v) => setTimeSleep(v ?? 1)} style={{ width: "100%" }} /></Form.Item></Col>
                  <Col span={4}><Form.Item label="Comment Sleep"><InputNumber min={0} max={120} step={0.5} value={commentSleep} onChange={(v) => setCommentSleep(v ?? 5)} style={{ width: "100%" }} /></Form.Item></Col>
                  <Col span={4}><Form.Item label="排序"><Select value={filters.sort_type_choice} onChange={(v) => setFilters((c) => ({ ...c, sort_type_choice: v }))} options={sortOptions} /></Form.Item></Col>
                  <Col span={4}><Form.Item label="类型"><Select value={filters.note_type} onChange={(v) => setFilters((c) => ({ ...c, note_type: v }))} options={noteTypeOptions} /></Form.Item></Col>
                  <Col span={4}><Form.Item label="时间范围"><Select value={filters.note_time} onChange={(v) => setFilters((c) => ({ ...c, note_time: v }))} options={noteTimeOptions} /></Form.Item></Col>
                </Row>,
              }]}
            />
          ) : null}

          <Space>
            <Button type="primary" htmlType="submit" loading={isRunning} disabled={noPcAccount} icon={isKeywordGroupMode || mode === "search" ? <SearchOutlined /> : <CloudDownloadOutlined />}>
              {isRunning ? "抓取中..." : isKeywordGroupMode ? "开始采集" : mode === "search" ? "开始抓取关键词" : "开始抓取"}
            </Button>
            <Button icon={<FileExcelOutlined />} onClick={() => items.length && exportRowsToExcel(items)} disabled={!items.length}>导出 Excel</Button>
          </Space>
        </Form>

        {summaryMessage && <Alert message={summaryMessage} type="success" showIcon style={{ marginTop: 16 }} />}
        {keywordGroupSummary && <Text type="secondary" style={{ display: "block", marginTop: 8 }}>保存 {keywordGroupSummary.saved_count} 条 · 跳过 {keywordGroupSummary.skipped_count} 条 · 访问频繁 {keywordGroupSummary.rate_limited_count} 条 · 详情缺失 {keywordGroupSummary.missing_detail_count} 条</Text>}
        {error && <Alert message={error} type="error" showIcon style={{ marginTop: 16 }} />}
        {noPcAccount && (
          <Empty description="还没有可用的 PC 账号" style={{ marginTop: 24 }}>
            <Link to="/platforms/xhs/accounts"><Button type="primary" icon={<LinkOutlined />}>去绑定账号</Button></Link>
          </Empty>
        )}
      </Card>

      <Card title={<Space><Title level={5} style={{ margin: 0 }}>抓取结果</Title><Text type="secondary">成功 {successCount} · 失败 {failedCount}{commentRateLimitedCount ? ` · 评论限流 ${commentRateLimitedCount}` : ""}{commentSkippedCount ? ` · 评论跳过 ${commentSkippedCount}` : ""}{isRunning && progressMsg ? ` · ${progressMsg}` : ""}{isRunning ? " · 抓取中..." : ""}</Text></Space>}>
        {items.length === 0 && !isRunning ? (
          <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="执行抓取后，结果会显示在这里" />
        ) : (
          <Table<XhsDataCrawlItem>
            columns={columns}
            dataSource={items}
            rowKey={(_, index) => `${index}`}
            size="small"
            pagination={{ pageSize: 50 }}
            scroll={{ x: 900 }}
            rowClassName={(item) => item.status === "failed" ? "ant-table-row-error" : ""}
          />
        )}
      </Card>
    </div>
  );
}
