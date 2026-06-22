import { useEffect, useMemo, useState } from "react";
import { Alert, Button, Card, Collapse, Empty, Input, Space, Tag, Typography, message as antMessage } from "antd";
import { EditOutlined, LinkOutlined, ReloadOutlined, SaveOutlined } from "@ant-design/icons";

import { DraftWorkbenchShell, useDraftWorkbench } from "../../../components/draft-workbench";
import {
  fetchDraftAssets,
  fetchSavedNote,
  generateTagOptions,
  generateTitleOptions,
  rewriteDraftWithAi,
  sendDraftToPublish,
  updateDraft,
} from "../../../lib/api";
import type { DraftAsset } from "../../../lib/api";
import type { SavedNote } from "../../../types";

import { createXhsDraftWorkbenchAdapter } from "./xhs-draft-workbench-adapter";
import type { RewriteTemplateKey } from "./rewrite-templates";
import { DEFAULT_REWRITE_TEMPLATE_KEY, REWRITE_TEMPLATES } from "./rewrite-templates";
import {
  clearRewriteCandidate,
  getRewriteCandidate,
  setRewriteCandidate,
  toRewriteCandidate,
} from "./xhs-rewrite-candidates";
import type { RewriteCandidateMap } from "./xhs-rewrite-candidates";

const { Paragraph, Text } = Typography;
const { TextArea } = Input;

function getNoteUrl(note: SavedNote): string {
  const raw = note.raw_json ?? {};
  for (const key of ["note_url", "url", "share_url"]) {
    const value = raw[key];
    if (typeof value === "string" && value.startsWith("http")) return value;
  }
  return `https://www.xiaohongshu.com/explore/${note.note_id}`;
}

export function XhsDraftsPage() {
  const adapter = useMemo(() => createXhsDraftWorkbenchAdapter(), []);
  const controller = useDraftWorkbench(adapter);
  const [sourceNote, setSourceNote] = useState<SavedNote | null>(null);
  const [sourceAssets, setSourceAssets] = useState<DraftAsset[]>([]);
  const [rewriteTemplate, setRewriteTemplate] = useState<RewriteTemplateKey>(DEFAULT_REWRITE_TEMPLATE_KEY);
  const [instruction, setInstruction] = useState(REWRITE_TEMPLATES[DEFAULT_REWRITE_TEMPLATE_KEY].instruction);
  const [systemPrompt, setSystemPrompt] = useState("你是小红书内容创作助手，擅长写吸引人的标题和正文。");
  const [titleOptions, setTitleOptions] = useState<string[]>([]);
  const [tagOptions, setTagOptions] = useState<string[]>([]);
  const [isRewriting, setIsRewriting] = useState(false);
  const [isSendingPublish, setIsSendingPublish] = useState(false);
  const [rewriteCandidates, setRewriteCandidates] = useState<RewriteCandidateMap>({});

  const selectedDraft = controller.selectedDraft;
  const hasSourceNote = Boolean(selectedDraft?.source_note_id);
  const activeRewriteTemplate = REWRITE_TEMPLATES[rewriteTemplate];
  const activeRewriteCandidate = getRewriteCandidate(rewriteCandidates, rewriteTemplate);

  useEffect(() => {
    if (!selectedDraft?.source_note_id) {
      setSourceNote(null);
      setSourceAssets([]);
      return;
    }
    let cancelled = false;
    (async () => {
      try {
        const [note, assets] = await Promise.all([
          fetchSavedNote(selectedDraft.source_note_id!),
          fetchDraftAssets(selectedDraft.id),
        ]);
        if (!cancelled) {
          setSourceNote(note);
          setSourceAssets(assets.items);
        }
      } catch {
        if (!cancelled) {
          setSourceNote(null);
          setSourceAssets([]);
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [selectedDraft?.id, selectedDraft?.source_note_id]);

  useEffect(() => {
    setRewriteCandidates({});
  }, [selectedDraft?.id]);

  async function handleRewrite() {
    if (!selectedDraft) return;
    setIsRewriting(true);
    try {
      await updateDraft(selectedDraft.id, { title: controller.title, body: controller.body, tags: controller.tags });
      const rewritten = await rewriteDraftWithAi({ draft_id: selectedDraft.id, instruction: `${systemPrompt}\n${instruction}` });
      const candidate = toRewriteCandidate(rewritten, Date.now());
      setRewriteCandidates((current) => setRewriteCandidate(current, rewriteTemplate, candidate));
      antMessage.success("AI 改写候选已生成，点击采纳后才会覆盖中间草稿。");
    } catch (error) {
      antMessage.error(error instanceof Error ? error.message : "AI 改写失败");
    } finally {
      setIsRewriting(false);
    }
  }

  function handleAdoptRewriteCandidate() {
    if (!activeRewriteCandidate) return;
    controller.setTitle(activeRewriteCandidate.title);
    controller.setBody(activeRewriteCandidate.body);
    controller.setTags(activeRewriteCandidate.tags);
    antMessage.success("已采纳到中间编辑区，请检查后保存。");
  }

  function handleDiscardRewriteCandidate() {
    setRewriteCandidates((current) => clearRewriteCandidate(current, rewriteTemplate));
    antMessage.success("已放弃当前模式候选。");
  }

  async function handleGenerateTitles() {
    if (!controller.body.trim()) {
      antMessage.warning("请先填写正文。");
      return;
    }
    try {
      const result = await generateTitleOptions({ title: controller.title, body: controller.body, count: 5 });
      setTitleOptions(result.items);
      antMessage.success("标题候选已生成。");
    } catch (error) {
      antMessage.error(error instanceof Error ? error.message : "标题生成失败");
    }
  }

  async function handleGenerateTags() {
    if (!controller.body.trim()) {
      antMessage.warning("请先填写正文。");
      return;
    }
    try {
      const result = await generateTagOptions({ title: controller.title, body: controller.body, count: 8 });
      setTagOptions(result.items);
      antMessage.success("标签候选已生成。");
    } catch (error) {
      antMessage.error(error instanceof Error ? error.message : "标签生成失败");
    }
  }

  async function handleSendToPublish() {
    if (!selectedDraft) return;
    setIsSendingPublish(true);
    try {
      await updateDraft(selectedDraft.id, { title: controller.title, body: controller.body, tags: controller.tags });
      const job = await sendDraftToPublish(selectedDraft.id, { publish_mode: "immediate" });
      antMessage.success(`已送入发布中心，发布任务 #${job.id}。`);
    } catch (error) {
      antMessage.error(error instanceof Error ? error.message : "送发布中心失败");
    } finally {
      setIsSendingPublish(false);
    }
  }

  return (
    <DraftWorkbenchShell
      adapter={adapter}
      controller={controller}
      renderEditorExtras={() => (
        <Space direction="vertical" size={16} style={{ width: "100%" }}>
          {hasSourceNote && sourceNote ? (
            <Card size="small" title="草稿内容" extra={<a href={getNoteUrl(sourceNote)} target="_blank" rel="noreferrer"><Button type="link" size="small" icon={<LinkOutlined />}>查看原文</Button></a>}>
              <Text strong style={{ display: "block", marginBottom: 4 }}>{sourceNote.title}</Text>
              <Paragraph ellipsis={{ rows: 3, expandable: true, symbol: "展开" }} type="secondary" style={{ marginBottom: 8 }}>
                {sourceNote.content}
              </Paragraph>
              <Space size={4} wrap>
                <Tag color="blue">来源草稿已独立化</Tag>
                <Tag color={sourceAssets.some((asset) => asset.asset_type === "video") ? "purple" : "green"}>
                  {sourceAssets.some((asset) => asset.asset_type === "video") ? "视频" : "图文"}
                </Tag>
                <Text type="secondary">素材 {sourceAssets.length} 项</Text>
              </Space>
            </Card>
          ) : null}

          {titleOptions.length > 0 ? (
            <Card size="small" title="标题候选">
              <Space wrap>
                {titleOptions.map((option) => (
                  <Button key={option} size="small" onClick={() => controller.setTitle(option)}>{option}</Button>
                ))}
              </Space>
            </Card>
          ) : null}

          {tagOptions.length > 0 ? (
            <Card size="small" title="标签候选">
              <Space wrap>
                {tagOptions.map((option) => (
                  <Tag key={option} color="blue">{option}</Tag>
                ))}
              </Space>
            </Card>
          ) : null}
        </Space>
      )}
      renderAssistantExtras={() => (
        <Space direction="vertical" size={12} style={{ width: "100%" }}>
          <Collapse
            size="small"
            items={[
              {
                key: "system-prompt",
                label: "高级设置：角色提示词",
                children: (
                  <TextArea rows={4} value={systemPrompt} onChange={(event) => setSystemPrompt(event.target.value)} />
                ),
              },
            ]}
          />

          <div>
            <Text type="secondary" style={{ display: "block", marginBottom: 6 }}>改写模式</Text>
            <Space direction="vertical" size={8} style={{ width: "100%" }}>
              <Input value={instruction} onChange={(event) => setInstruction(event.target.value)} placeholder="填写 AI 改写指令" />
              <Space wrap>
                {Object.entries(REWRITE_TEMPLATES).map(([key, template]) => (
                  <Button key={key} size="small" type={rewriteTemplate === key ? "primary" : "default"} icon={<EditOutlined />} onClick={() => {
                    setRewriteTemplate(key as RewriteTemplateKey);
                    setInstruction(template.instruction);
                  }}>
                    {template.label}
                  </Button>
                ))}
              </Space>
            </Space>
          </div>

          <Space wrap>
            <Button onClick={() => void handleRewrite()} loading={isRewriting} icon={<ReloadOutlined />}>
              {activeRewriteTemplate.buttonLabel}
            </Button>
            <Button onClick={() => void handleGenerateTitles()}>生成标题</Button>
            <Button onClick={() => void handleGenerateTags()}>生成标签</Button>
            <Button type="primary" onClick={() => void handleSendToPublish()} loading={isSendingPublish} icon={<SaveOutlined />}>
              送发布中心
            </Button>
          </Space>

          {activeRewriteCandidate ? (
            <Card
              size="small"
              title={`改写结果 · ${activeRewriteTemplate.label}`}
              styles={{ body: { maxHeight: 420, overflow: "auto" } }}
            >
              <Space direction="vertical" size={12} style={{ width: "100%" }}>
                <Alert
                  type="info"
                  showIcon
                  message="候选结果尚未覆盖中间草稿"
                  description="你可以和中间编辑区原文对比，确认后再点击采纳。"
                />
                <div>
                  <Text type="secondary" style={{ display: "block", marginBottom: 4 }}>
                    标题
                  </Text>
                  <Text strong>{activeRewriteCandidate.title || "未命名候选"}</Text>
                </div>
                <div>
                  <Text type="secondary" style={{ display: "block", marginBottom: 4 }}>
                    正文
                  </Text>
                  <Paragraph style={{ whiteSpace: "pre-wrap", marginBottom: 0 }}>
                    {activeRewriteCandidate.body || "暂无正文"}
                  </Paragraph>
                </div>
                {activeRewriteCandidate.tags.length > 0 ? (
                  <Space size={[4, 8]} wrap>
                    {activeRewriteCandidate.tags.map((tag) => (
                      <Tag key={tag.id || tag.name} color="blue">
                        #{tag.name}
                      </Tag>
                    ))}
                  </Space>
                ) : null}
                <Space wrap>
                  <Button type="primary" aria-label="adopt rewrite candidate" onClick={handleAdoptRewriteCandidate}>
                    采纳
                  </Button>
                  <Button aria-label="discard rewrite candidate" onClick={handleDiscardRewriteCandidate}>放弃</Button>
                </Space>
              </Space>
            </Card>
          ) : (
            <Empty
              image={Empty.PRESENTED_IMAGE_SIMPLE}
              description={`当前模式还没有候选，生成${activeRewriteTemplate.label}后可和中间草稿对比。`}
            />
          )}
        </Space>
      )}
    />
  );
}
