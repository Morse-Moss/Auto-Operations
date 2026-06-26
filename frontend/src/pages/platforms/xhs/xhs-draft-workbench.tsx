import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Alert, Button, Card, Collapse, Empty, Input, Modal, Select, Space, Tag, Typography, Upload, message as antMessage } from "antd";
import { DeleteOutlined, EditOutlined, LinkOutlined, PictureOutlined, ReloadOutlined, SaveOutlined, UploadOutlined } from "@ant-design/icons";

import { DraftWorkbenchShell, useDraftWorkbench } from "../../../components/draft-workbench";
import {
  addDraftAsset,
  deleteDraftAsset,
  fetchDraftAssets,
  fetchSavedNote,
  fetchTask,
  generateTagOptions,
  generateTitleOptions,
  localizeDraftAsset,
  rewriteDraftWithAi,
  sendDraftToPublish,
  startImageGenerationTask,
  updateDraft,
  uploadAssetFile,
} from "../../../lib/api";
import type { DraftAsset } from "../../../lib/api";
import type { GeneratedImageAsset, GenerateImageResult, SavedNote, TaskRecord } from "../../../types";

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
import { draftAssetImageUrl, draftAssetToCandidate, isUsableImageUrl, saveImageStudioDraftContext } from "./xhs-image-studio-context";
import type { XhsImageStudioCandidateImage } from "./xhs-image-studio-context";

const { Paragraph, Text } = Typography;
const { TextArea } = Input;
const IMAGE_GENERATION_POLL_INTERVAL_MS = 3000;
const IMAGE_GENERATION_MAX_POLLS = 220;
type ImageAspectRatio = "auto" | "1:1" | "3:4" | "4:3" | "9:16" | "16:9";

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

function imageResultFromTask(task: TaskRecord): GenerateImageResult | null {
  const taskRecord = task as TaskRecord & { result?: unknown };
  const result = taskRecord.result ?? task.payload.result ?? task.payload;
  if (!result || typeof result !== "object") return null;
  const record = result as Record<string, unknown>;
  return typeof record.url === "string" && record.url
    ? {
      url: record.url,
      raw: record.raw,
      asset: record.asset as GeneratedImageAsset | undefined,
    }
    : null;
}

function taskErrorMessage(task: TaskRecord): string {
  const error = task.payload.error;
  return typeof error === "string" && error ? error : "AI 图片生成失败，请检查任务详情。";
}

function fileNameFrom(filePath: string): string {
  return filePath.replace(/^\/api\/files\/media\//, "").split(/[\\/]/).pop() ?? filePath;
}

function getNoteUrl(note: SavedNote): string {
  const raw = note.raw_json ?? {};
  for (const key of ["note_url", "url", "share_url"]) {
    const value = raw[key];
    if (typeof value === "string" && value.startsWith("http")) return value;
  }
  return `https://www.xiaohongshu.com/explore/${note.note_id}`;
}

function normalizeTagName(value: string): string {
  return value.replace(/^[#\s]+/, "").trim();
}

function appendHashtag(body: string, tagName: string): string {
  const clean = normalizeTagName(tagName);
  if (!clean) return body;

  const hashtag = `#${clean}`;
  if (body.includes(hashtag)) return body;
  if (!body.trim()) return hashtag;
  return `${body.trimEnd()}\n\n${hashtag}`;
}

function collectImageUrls(value: unknown, urls: Set<string>): void {
  if (isUsableImageUrl(value)) {
    urls.add(value);
    return;
  }
  if (Array.isArray(value)) {
    value.forEach((item) => collectImageUrls(item, urls));
    return;
  }
  if (!value || typeof value !== "object") return;

  const record = value as Record<string, unknown>;
  for (const key of ["url", "image_url", "original_url", "master_url", "cover_url"]) {
    collectImageUrls(record[key], urls);
  }
}

function collectRawNoteImageUrls(raw: Record<string, unknown>, urls: Set<string>): void {
  for (const key of ["cover_url", "image_url", "image_urls", "images", "image_list"]) {
    collectImageUrls(raw[key], urls);
  }

  const noteCard = raw.note_card && typeof raw.note_card === "object" ? raw.note_card as Record<string, unknown> : null;
  if (noteCard) {
    for (const key of ["cover_url", "image_url", "image_urls", "image_list", "images"]) {
      collectImageUrls(noteCard[key], urls);
    }
  }

  const data = raw.data && typeof raw.data === "object" ? raw.data as Record<string, unknown> : null;
  const items = Array.isArray(data?.items) ? data.items : [];
  for (const item of items) {
    if (!item || typeof item !== "object") continue;
    const card = (item as Record<string, unknown>).note_card;
    if (card && typeof card === "object") {
      for (const key of ["cover_url", "image_url", "image_urls", "image_list", "images"]) {
        collectImageUrls((card as Record<string, unknown>)[key], urls);
      }
    }
  }
}

function sourceNoteImageCandidates(note: SavedNote | null, existingUrls = new Set<string>()): XhsImageStudioCandidateImage[] {
  const urls = new Set<string>();
  collectImageUrls(note?.cover_url, urls);
  collectRawNoteImageUrls(note?.raw_json ?? {}, urls);
  return Array.from(urls)
    .filter((url) => !existingUrls.has(url))
    .map((url) => ({ url, source: "source_note" }));
}

function renderDraftSourceAssetPreview(draftAssets: DraftAsset[]) {
  const imageAssets = draftAssets.filter((asset) => asset.asset_type === "image" && Boolean(draftAssetImageUrl(asset)));
  if (imageAssets.length === 0) {
    return (
      <Text type="secondary" style={{ fontSize: 12 }}>
        这个草稿暂无来源图片，可在图片工坊上传参考图继续。
      </Text>
    );
  }

  const visibleAssets = imageAssets.slice(0, 6);
  const hiddenCount = imageAssets.length - visibleAssets.length;
  return (
    <Space direction="vertical" size={6} style={{ width: "100%" }}>
      <Text type="secondary" style={{ fontSize: 12 }}>
        这些图片会随“送入图片工坊”一起带入，后续可选择最终发布图。
      </Text>
      <Space size={8} wrap>
        {visibleAssets.map((asset, index) => (
          <div key={asset.id} style={{ width: 56 }}>
            <div style={{ width: 56, height: 56, borderRadius: 6, overflow: "hidden", background: "#1a1a1a", border: "1px solid #303030" }}>
              <img src={draftAssetImageUrl(asset)} alt={`来源图片 ${index + 1}`} referrerPolicy="no-referrer" style={{ width: "100%", height: "100%", objectFit: "cover" }} />
            </div>
          </div>
        ))}
        {hiddenCount > 0 ? <Tag color="blue">+{hiddenCount}</Tag> : null}
      </Space>
    </Space>
  );
}

export function XhsDraftsPage() {
  const navigate = useNavigate();
  const adapter = useMemo(() => createXhsDraftWorkbenchAdapter(), []);
  const controller = useDraftWorkbench(adapter);
  const [sourceNote, setSourceNote] = useState<SavedNote | null>(null);
  const [draftAssets, setDraftAssets] = useState<DraftAsset[]>([]);
  const [draftAssetUrl, setDraftAssetUrl] = useState("");
  const [isUpdatingDraftAssets, setIsUpdatingDraftAssets] = useState(false);
  const [rewriteTemplate, setRewriteTemplate] = useState<RewriteTemplateKey>(DEFAULT_REWRITE_TEMPLATE_KEY);
  const [instruction, setInstruction] = useState(REWRITE_TEMPLATES[DEFAULT_REWRITE_TEMPLATE_KEY].instruction);
  const [systemPrompt, setSystemPrompt] = useState("你是小红书内容创作助手，擅长写吸引人的标题和正文。");
  const [titleOptions, setTitleOptions] = useState<string[]>([]);
  const [tagOptions, setTagOptions] = useState<string[]>([]);
  const [isRewriting, setIsRewriting] = useState(false);
  const [isSendingPublish, setIsSendingPublish] = useState(false);
  const [isSendingImageStudio, setIsSendingImageStudio] = useState(false);
  const [rewriteCandidates, setRewriteCandidates] = useState<RewriteCandidateMap>({});
  const [editingAsset, setEditingAsset] = useState<DraftAsset | null>(null);
  const [editImagePrompt, setEditImagePrompt] = useState("");
  const [editImageAspectRatio, setEditImageAspectRatio] = useState<ImageAspectRatio>("auto");
  const [isEditingImage, setIsEditingImage] = useState(false);

  const selectedDraft = controller.selectedDraft;
  const selectedSourceNoteId = selectedDraft?.source_note_id ?? null;
  const currentSourceNote = sourceNote && selectedSourceNoteId !== null && sourceNote.id === selectedSourceNoteId ? sourceNote : null;
  const hasSourceNote = Boolean(selectedSourceNoteId);
  const activeRewriteTemplate = REWRITE_TEMPLATES[rewriteTemplate];
  const activeRewriteCandidate = getRewriteCandidate(rewriteCandidates, rewriteTemplate);
  const draftImageAssets = draftAssets.filter((asset) => asset.asset_type === "image" && Boolean(draftAssetImageUrl(asset)));

  useEffect(() => {
    setSourceNote(null);
    setDraftAssets([]);
    if (!selectedDraft) {
      return;
    }
    let cancelled = false;
    (async () => {
      try {
        const assets = await fetchDraftAssets(selectedDraft.id);
        if (!cancelled) {
          setDraftAssets(assets.items);
        }
      } catch {
        if (!cancelled) {
          setDraftAssets([]);
        }
      }
    })();
    if (selectedDraft.source_note_id) {
      (async () => {
        try {
          const note = await fetchSavedNote(selectedDraft.source_note_id!);
          if (!cancelled) {
            setSourceNote(note);
          }
        } catch {
          if (!cancelled) {
            setSourceNote(null);
          }
        }
      })();
    }
    return () => {
      cancelled = true;
    };
  }, [selectedDraft?.id, selectedDraft?.source_note_id]);

  useEffect(() => {
    setRewriteCandidates({});
    setDraftAssetUrl("");
  }, [selectedDraft?.id]);

  async function refreshDraftAssets(draftId = selectedDraft?.id) {
    if (!draftId) {
      setDraftAssets([]);
      return;
    }
    const assets = await fetchDraftAssets(draftId);
    setDraftAssets(assets.items);
  }

  async function handleAddDraftAssetUrl() {
    if (!selectedDraft) return;
    const url = draftAssetUrl.trim();
    if (!isUsableImageUrl(url)) {
      antMessage.warning("请输入有效的图片 URL。");
      return;
    }
    setIsUpdatingDraftAssets(true);
    try {
      await addDraftAsset(selectedDraft.id, { asset_type: "image", url });
      setDraftAssetUrl("");
      await refreshDraftAssets(selectedDraft.id);
      antMessage.success("已添加草稿图片。");
    } catch (error) {
      antMessage.error(error instanceof Error ? error.message : "添加草稿图片失败");
    } finally {
      setIsUpdatingDraftAssets(false);
    }
  }

  async function handleUploadDraftAsset(file: File) {
    if (!selectedDraft) return false;
    setIsUpdatingDraftAssets(true);
    try {
      const uploaded = await uploadAssetFile(file);
      await addDraftAsset(selectedDraft.id, { asset_type: "image", local_path: uploaded.file_name });
      await refreshDraftAssets(selectedDraft.id);
      antMessage.success("已上传草稿图片。");
    } catch (error) {
      antMessage.error(error instanceof Error ? error.message : "上传草稿图片失败");
    } finally {
      setIsUpdatingDraftAssets(false);
    }
    return false;
  }

  async function handleDeleteDraftAsset(asset: DraftAsset) {
    if (!selectedDraft) return;
    setIsUpdatingDraftAssets(true);
    try {
      await deleteDraftAsset(selectedDraft.id, asset.id);
      await refreshDraftAssets(selectedDraft.id);
      antMessage.success("已删除草稿图片。");
    } catch (error) {
      antMessage.error(error instanceof Error ? error.message : "删除草稿图片失败");
    } finally {
      setIsUpdatingDraftAssets(false);
    }
  }

  function openImageEditModal(asset: DraftAsset) {
    setEditingAsset(asset);
    setEditImagePrompt("");
    setEditImageAspectRatio("auto");
  }

  async function handleEditDraftAssetImage() {
    if (!selectedDraft || !editingAsset) return;
    const prompt = editImagePrompt.trim();
    if (!prompt) {
      antMessage.warning("请填写 AI 编辑提示词。");
      return;
    }
    setIsEditingImage(true);
    try {
      const localizedAsset = await localizeDraftAsset(selectedDraft.id, editingAsset.id);
      const referenceUrl = draftAssetImageUrl(localizedAsset);
      if (!referenceUrl.startsWith("/api/files/media/")) {
        throw new Error("图片本地化失败，请先上传本地图或更换图片。");
      }
      const startedTask = await startImageGenerationTask({
        prompt,
        reference_images: [referenceUrl],
        save_to_assets: true,
        aspect_ratio: editImageAspectRatio,
      });
      for (let index = 0; index < IMAGE_GENERATION_MAX_POLLS; index += 1) {
        await sleep(IMAGE_GENERATION_POLL_INTERVAL_MS);
        const task = await fetchTask(startedTask.task_id);
        if (task.status === "completed") {
          const result = imageResultFromTask(task);
          if (!result?.asset?.file_path) {
            throw new Error("AI 图片任务已完成，但没有返回可新增的图片资产。");
          }
          await addDraftAsset(selectedDraft.id, {
            asset_type: "image",
            local_path: fileNameFrom(result.asset.file_path),
          });
          await refreshDraftAssets(selectedDraft.id);
          setEditingAsset(null);
          antMessage.success("AI 编辑图已新增。");
          return;
        }
        if (["failed", "cancelled", "exhausted"].includes(task.status)) {
          throw new Error(taskErrorMessage(task));
        }
      }
      throw new Error(`AI 图片生成任务仍在运行（#${startedTask.task_id}），请稍后到任务中心查看。`);
    } catch (error) {
      antMessage.error(error instanceof Error ? error.message : "AI 编辑图片失败");
    } finally {
      setIsEditingImage(false);
    }
  }

  async function handleRewrite() {
    if (!selectedDraft) return;
    setIsRewriting(true);
    try {
      await updateDraft(selectedDraft.id, {
        draft_name: controller.draftName,
        title: controller.title,
        body: controller.body,
        tags: controller.tags,
      });
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

  function handleAdoptTagOption(option: string) {
    const clean = normalizeTagName(option);
    if (!clean) return;

    if (!controller.tags.some((tag) => tag.name === clean)) {
      controller.setTags([...controller.tags, { id: clean, name: clean }]);
    }
    controller.setBody(appendHashtag(controller.body, clean));
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
      await updateDraft(selectedDraft.id, {
        draft_name: controller.draftName,
        title: controller.title,
        body: controller.body,
        tags: controller.tags,
      });
      const job = await sendDraftToPublish(selectedDraft.id, { publish_mode: "immediate" });
      antMessage.success(`已送入发布中心，发布任务 #${job.id}。`);
    } catch (error) {
      antMessage.error(error instanceof Error ? error.message : "送发布中心失败");
    } finally {
      setIsSendingPublish(false);
    }
  }

  async function handleSendToImageStudio() {
    if (!selectedDraft) {
      antMessage.warning("请先选择一个草稿，再进入图片工坊。");
      return;
    }
    setIsSendingImageStudio(true);
    try {
      const saved = await updateDraft(selectedDraft.id, {
        draft_name: controller.draftName,
        title: controller.title,
        body: controller.body,
        tags: controller.tags,
      });
      const assets = await fetchDraftAssets(saved.id);
      setDraftAssets(assets.items);
      const draftAssetCandidates = assets.items
        .map(draftAssetToCandidate)
        .filter((item): item is XhsImageStudioCandidateImage => Boolean(item));
      const usedUrls = new Set(draftAssetCandidates.map((item) => item.url));
      const matchingSourceNote = currentSourceNote && saved.source_note_id === currentSourceNote.id ? currentSourceNote : null;
      const candidateImages = [...draftAssetCandidates, ...sourceNoteImageCandidates(matchingSourceNote, usedUrls)];
      const contextSaved = saveImageStudioDraftContext({
        source: "draft",
        draft_id: saved.id,
        draft_name: saved.draft_name ?? null,
        title: saved.title,
        body: saved.body,
        tags: Array.isArray(saved.tags) ? saved.tags : [],
        source_note_id: saved.source_note_id ?? null,
        candidate_images: candidateImages,
      });
      if (!contextSaved) {
        antMessage.error("草稿已保存，但浏览器无法暂存图片工坊上下文。请检查隐私模式或浏览器存储权限后重试。");
        return;
      }
      antMessage.success(
        candidateImages.length > 0
          ? `已保存草稿并带入 ${candidateImages.length} 张候选图，正在进入图片工坊。`
          : "已保存草稿，正在进入图片工坊。这个草稿暂无候选图，可在图片工坊手动上传参考图。",
      );
      navigate("/platforms/xhs/image-studio?from=draft");
    } catch (error) {
      antMessage.error(error instanceof Error ? error.message : "送入图片工坊失败，请先保存草稿后重试。");
    } finally {
      setIsSendingImageStudio(false);
    }
  }

  return (
    <>
      <DraftWorkbenchShell
      adapter={adapter}
      controller={controller}
      renderSourcePanel={() => (
        hasSourceNote && currentSourceNote ? (
          <Card size="small" title="草稿内容" extra={<a href={getNoteUrl(currentSourceNote)} target="_blank" rel="noreferrer"><Button type="link" size="small" icon={<LinkOutlined />}>查看原文</Button></a>}>
            <Text strong style={{ display: "block", marginBottom: 4 }}>{currentSourceNote.title}</Text>
            <Paragraph ellipsis={{ rows: 3, expandable: true, symbol: "展开" }} type="secondary" style={{ marginBottom: 8 }}>
              {currentSourceNote.content}
            </Paragraph>
            <Space size={4} wrap>
              <Tag color="blue">来源草稿已独立化</Tag>
              <Tag color={draftAssets.some((asset) => asset.asset_type === "video") ? "purple" : "green"}>
                {draftAssets.some((asset) => asset.asset_type === "video") ? "视频" : "图文"}
              </Tag>
              <Text type="secondary">素材 {draftAssets.length} 项</Text>
            </Space>
            <div style={{ marginTop: 10 }}>
              {renderDraftSourceAssetPreview(draftAssets)}
            </div>
          </Card>
        ) : null
      )}
      renderEditorExtras={() => (
        <Card size="small" title="草稿图片素材">
          <Space direction="vertical" size={12} style={{ width: "100%" }}>
            <Space.Compact style={{ width: "100%" }}>
              <Input
                value={draftAssetUrl}
                onChange={(event) => setDraftAssetUrl(event.target.value)}
                onPressEnter={() => void handleAddDraftAssetUrl()}
                placeholder="粘贴图片 URL"
                disabled={isUpdatingDraftAssets}
              />
              <Button type="primary" onClick={() => void handleAddDraftAssetUrl()} loading={isUpdatingDraftAssets}>
                添加
              </Button>
            </Space.Compact>

            <Upload accept="image/*" showUploadList={false} beforeUpload={(file) => handleUploadDraftAsset(file)} disabled={isUpdatingDraftAssets || !selectedDraft}>
              <Button icon={<UploadOutlined />} loading={isUpdatingDraftAssets}>
                上传图片
              </Button>
            </Upload>

            {draftImageAssets.length > 0 ? (
              <Space size={[10, 10]} wrap>
                {draftImageAssets.map((asset, index) => (
                  <div key={asset.id} style={{ width: 112 }}>
                    <div style={{ position: "relative", width: 112, height: 112, borderRadius: 8, overflow: "hidden", background: "#1a1a1a", border: "1px solid #303030" }}>
                      <img src={draftAssetImageUrl(asset)} alt={`草稿图片 ${index + 1}`} referrerPolicy="no-referrer" style={{ width: "100%", height: "100%", objectFit: "cover" }} />
                      <Tag color="blue" style={{ position: "absolute", top: 6, left: 6, margin: 0 }}>#{index + 1}</Tag>
                    </div>
                    <Space direction="vertical" size={6} style={{ width: "100%", marginTop: 6 }}>
                      <Button
                        size="small"
                        block
                        icon={<EditOutlined />}
                        disabled={isUpdatingDraftAssets || isEditingImage}
                        onClick={() => openImageEditModal(asset)}
                      >
                        编辑
                      </Button>
                      <Button
                        danger
                        size="small"
                        block
                        icon={<DeleteOutlined />}
                        loading={isUpdatingDraftAssets}
                        disabled={isEditingImage}
                        onClick={() => void handleDeleteDraftAsset(asset)}
                      >
                        删除
                      </Button>
                    </Space>
                  </div>
                ))}
              </Space>
            ) : (
              <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="当前草稿暂无图片" />
            )}
          </Space>
        </Card>
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
            <Button onClick={() => void handleSendToImageStudio()} loading={isSendingImageStudio} icon={<PictureOutlined />}>
              送入图片工坊
            </Button>
            <Button type="primary" onClick={() => void handleSendToPublish()} loading={isSendingPublish} icon={<SaveOutlined />}>
              送发布中心
            </Button>
          </Space>

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
                  <Tag key={option} color="blue" onClick={() => handleAdoptTagOption(option)} style={{ cursor: "pointer" }}>{option}</Tag>
                ))}
              </Space>
            </Card>
          ) : null}

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
      <Modal
        title="AI 编辑图片"
        open={Boolean(editingAsset)}
        onCancel={() => {
          if (!isEditingImage) setEditingAsset(null);
        }}
        onOk={() => void handleEditDraftAssetImage()}
        okText="生成 AI 编辑图"
        cancelText="取消"
        confirmLoading={isEditingImage}
        okButtonProps={{ disabled: !editImagePrompt.trim() }}
        maskClosable={!isEditingImage}
      >
        <Space direction="vertical" size={12} style={{ width: "100%" }}>
          <Text type="secondary">
            原图会保留，生成成功后会把 AI 编辑图新增到当前草稿图片素材。
          </Text>
          {editingAsset ? (
            <div style={{ width: 160, height: 160, borderRadius: 10, overflow: "hidden", background: "#1a1a1a", border: "1px solid #303030" }}>
              <img src={draftAssetImageUrl(editingAsset)} alt="AI 编辑原图" referrerPolicy="no-referrer" style={{ width: "100%", height: "100%", objectFit: "cover" }} />
            </div>
          ) : null}
          <div>
            <Text type="secondary" style={{ display: "block", marginBottom: 6 }}>
              编辑提示词
            </Text>
            <TextArea
              rows={4}
              value={editImagePrompt}
              onChange={(event) => setEditImagePrompt(event.target.value)}
              placeholder="例如：保留主体和构图，改成暖色自然光、干净背景、小红书封面质感"
              disabled={isEditingImage}
            />
          </div>
          <div>
            <Text type="secondary" style={{ display: "block", marginBottom: 6 }}>
              图片比例
            </Text>
            <Select<ImageAspectRatio>
              value={editImageAspectRatio}
              onChange={setEditImageAspectRatio}
              disabled={isEditingImage}
              style={{ width: 180 }}
              options={[
                { value: "auto", label: "自动" },
                { value: "1:1", label: "1:1" },
                { value: "3:4", label: "3:4" },
                { value: "4:3", label: "4:3" },
                { value: "9:16", label: "9:16" },
                { value: "16:9", label: "16:9" },
              ]}
            />
          </div>
        </Space>
      </Modal>
    </>
  );
}
