import {
  ArrowDownOutlined,
  ArrowUpOutlined,
  DeleteOutlined,
  FileImageOutlined,
  InboxOutlined,
  LinkOutlined,
  SendOutlined,
  PictureOutlined,
  PlusOutlined,
  ReloadOutlined,
  RobotOutlined,
  StarOutlined,
  UploadOutlined,
} from "@ant-design/icons";
import {
  Alert,
  Button,
  Card,
  Checkbox,
  Col,
  Empty,
  Image,
  Input,
  Modal,
  Row,
  Select,
  Space,
  Spin,
  Tabs,
  Tag,
  Typography,
  Upload,
} from "antd";
import { useEffect, useMemo, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";

import { PageHeader } from "../../../components/layout/app-shell";
import {
  deleteGeneratedImageAsset,
  deleteUserImage,
  describeImageWithAi,
  fetchGeneratedImageAssets,
  fetchTask,
  addDraftAsset,
  fetchUserImages,
  sendDraftToPublish,
  startImageGenerationTask,
  uploadAssetFile,
} from "../../../lib/api";
import { formatShanghaiTime } from "../../../lib/time";
import type { GeneratedImageAsset, GenerateImageResult, TaskRecord, UserImageFile } from "../../../types";
import {
  clearImageStudioDraftContext,
  loadImageStudioDraftContext,
  type XhsImageStudioDraftContext,
} from "./xhs-image-studio-context";
import {
  clearWechatOfficialImageStudioDraftContext,
  loadWechatOfficialImageStudioDraftContext,
  type WechatOfficialImageStudioDraftContext,
} from "../../wechat-official/wechat-official-image-studio-context";

const { Text, Paragraph } = Typography;
const { TextArea } = Input;
const RUNNINGHUB_CURRENT_REFERENCE_IMAGE_LIMIT = 2;
const IMAGE_GENERATION_POLL_INTERVAL_MS = 3000;
const IMAGE_GENERATION_MAX_POLLS = 220;
type ImageAspectRatio = "auto" | "1:1" | "3:4" | "4:3" | "9:16" | "16:9";
type ImageStudioDraftContext = XhsImageStudioDraftContext | WechatOfficialImageStudioDraftContext;

type FinalPublishImage = {
  key: string;
  url: string;
  publishPath: string;
  source: "draft_asset" | "source_note" | "manual" | "generated" | "asset";
  label: string;
};

function isRenderableImage(value: string): boolean {
  return (
    value.startsWith("http://") ||
    value.startsWith("https://") ||
    value.startsWith("data:image/") ||
    value.startsWith("/api/")
  );
}

function isServerManagedMediaPath(value: unknown): value is string {
  return typeof value === "string" && value.startsWith("/api/files/media/");
}

function isPublishableFinalImagePath(value: string): boolean {
  return (
    value.startsWith("/api/files/media/") ||
    value.startsWith("http://") ||
    value.startsWith("https://")
  );
}

function generatedPublishMediaPath(result: GenerateImageResult): string | null {
  return isServerManagedMediaPath(result.asset?.file_path) ? result.asset.file_path : null;
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

function imageResultFromTask(task: TaskRecord): GenerateImageResult | null {
  const result = task.payload.result;
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

function buildDraftImagePrompt(context: ImageStudioDraftContext): string {
  const title = context.title.trim();
  const body = context.body.replace(/\s+/g, " ").trim();
  const bodyExcerpt = body.length > 180 ? `${body.slice(0, 180)}...` : body;
  const tags = context.tags.map((tag) => tag.name.trim()).filter(Boolean).slice(0, 6);
  const isWechatOfficial = "platform" in context && context.platform === "wechat_official";
  return [
    isWechatOfficial ? "为这篇公众号草稿生成一张封面/正文配图候选。" : "为这篇小红书草稿生成一张可直接发布的封面/首图。",
    title ? `标题：${title}` : "",
    bodyExcerpt ? `正文要点：${bodyExcerpt}` : "",
    tags.length > 0 ? `标签：${tags.map((tag) => `#${tag}`).join(" ")}` : "",
    isWechatOfficial ? "风格要求：信息清晰、可信、有公众号封面感；只生成/整理图片，不上传公众号素材。" : "风格要求：真实、有生活感、构图干净，适合小红书图文笔记。",
  ].filter(Boolean).join("\n");
}

function candidateImageSourceLabel(source: ImageStudioDraftContext["candidate_images"][number]["source"]): string {
  if (source === "draft_asset") return "草稿素材";
  if (source === "source_note") return "原笔记案例图";
  if (source === "article_cover") return "文章封面";
  if (source === "snapshot_image") return "正文配图";
  return "手动添加";
}

function isWechatOfficialDraftContext(context: ImageStudioDraftContext | null): context is WechatOfficialImageStudioDraftContext {
  return Boolean(context && "platform" in context && context.platform === "wechat_official");
}

export function XhsImageStudioPage() {
  const location = useLocation();
  const navigate = useNavigate();
  const [assets, setAssets] = useState<GeneratedImageAsset[]>([]);
  const [userImages, setUserImages] = useState<UserImageFile[]>([]);
  const [prompt, setPrompt] = useState("");
  const [referenceImages, setReferenceImages] = useState<string[]>([]);
  const [aspectRatio, setAspectRatio] = useState<ImageAspectRatio>("auto");
  const [imageUrl, setImageUrl] = useState("");
  const [description, setDescription] = useState("");
  const [isLoading, setIsLoading] = useState(true);
  const [isGenerating, setIsGenerating] = useState(false);
  const [isDescribing, setIsDescribing] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [refPickerOpen, setRefPickerOpen] = useState(false);
  const [saveToAssets, setSaveToAssets] = useState(true);
  const [generatedPreview, setGeneratedPreview] = useState<string | null>(null);
  const [generatedMediaPath, setGeneratedMediaPath] = useState<string | null>(null);
  const [draftContext, setDraftContext] = useState<ImageStudioDraftContext | null>(null);
  const [finalPublishImages, setFinalPublishImages] = useState<FinalPublishImage[]>([]);
  const [isSendingPublish, setIsSendingPublish] = useState(false);
  const [isAttachingDraftAsset, setIsAttachingDraftAsset] = useState(false);

  const draftReferenceUrls = useMemo(
    () => (draftContext?.candidate_images ?? [])
      .map((image) => image.url)
      .filter((url, index, urls) => urls.indexOf(url) === index)
      .slice(0, RUNNINGHUB_CURRENT_REFERENCE_IMAGE_LIMIT),
    [draftContext],
  );
  const referenceLimitReached = referenceImages.length >= RUNNINGHUB_CURRENT_REFERENCE_IMAGE_LIMIT;

  function addFinalPublishImage(image: Omit<FinalPublishImage, "key">) {
    setFinalPublishImages((prev) => {
      if (prev.some((item) => item.publishPath === image.publishPath)) return prev;
      return [...prev, { ...image, key: image.publishPath }];
    });
  }

  function removeFinalPublishImage(publishPath: string) {
    setFinalPublishImages((prev) => prev.filter((image) => image.publishPath !== publishPath));
  }

  function moveFinalPublishImage(index: number, direction: -1 | 1) {
    setFinalPublishImages((prev) => {
      const nextIndex = index + direction;
      if (nextIndex < 0 || nextIndex >= prev.length) return prev;
      const next = [...prev];
      [next[index], next[nextIndex]] = [next[nextIndex], next[index]];
      return next;
    });
  }

  function isFinalPublishImageSelected(publishPath: string) {
    return finalPublishImages.some((image) => image.publishPath === publishPath);
  }

  function candidateToFinalImage(
    image: ImageStudioDraftContext["candidate_images"][number],
    index: number,
  ): FinalPublishImage | null {
    if (!image.url) return null;
    if (image.source === "article_cover" || image.source === "snapshot_image") return null;
    return {
      key: image.url,
      url: image.url,
      publishPath: image.url,
      source: image.source,
      label: `${candidateImageSourceLabel(image.source)} ${index + 1}`,
    };
  }

  // For the reference picker modal: which callback mode
  const [pickerMode, setPickerMode] = useState<"reference" | "describe">(
    "reference",
  );
  const [pickerUrlInput, setPickerUrlInput] = useState("");

  async function loadAssets() {
    setIsLoading(true);
    setError(null);
    try {
      const [aiResult, userResult] = await Promise.all([
        fetchGeneratedImageAssets(),
        fetchUserImages(),
      ]);
      setAssets(aiResult.items);
      setUserImages(userResult.items);
    } catch {
      setError("图片资产加载失败。");
    } finally {
      setIsLoading(false);
    }
  }

  async function handleGenerate() {
    if (!prompt.trim()) {
      setError("请填写提示词。");
      return;
    }
    setIsGenerating(true);
    setError(null);
    setMessage(null);
    setGeneratedPreview(null);
    setGeneratedMediaPath(null);
    try {
      const startedTask = await startImageGenerationTask({
        prompt: prompt.trim(),
        reference_images:
          referenceImages.length > 0 ? referenceImages : undefined,
        save_to_assets: saveToAssets,
        aspect_ratio: aspectRatio,
      });
      setMessage(`图片生成任务已提交（#${startedTask.task_id}），正在后台生成...`);

      for (let index = 0; index < IMAGE_GENERATION_MAX_POLLS; index += 1) {
        await sleep(IMAGE_GENERATION_POLL_INTERVAL_MS);
        const task = await fetchTask(startedTask.task_id);
        if (task.status === "completed") {
          const result = imageResultFromTask(task);
          if (!result) {
            throw new Error("图片任务已完成，但结果为空。请到任务中心查看详情。");
          }
          const mediaPath = generatedPublishMediaPath(result);
          const publishPath = mediaPath ?? result.url;
          setGeneratedPreview(publishPath);
          setGeneratedMediaPath(mediaPath);
          if (isPublishableFinalImagePath(publishPath)) {
            addFinalPublishImage({
              url: publishPath,
              publishPath,
              source: "generated",
              label: "AI 生成图",
            });
          }
          if (result.asset) {
            setAssets((prev) => [result.asset!, ...prev]);
          } else {
            void loadAssets();
          }
          setMessage("图片生成成功。");
          return;
        }
        if (["failed", "cancelled", "exhausted"].includes(task.status)) {
          throw new Error(taskErrorMessage(task));
        }
        setMessage(`图片生成中（#${startedTask.task_id}，${task.progress}%），可稍后刷新资产查看结果。`);
      }
      setMessage(`图片生成任务仍在运行（#${startedTask.task_id}）。你可以稍后点击“刷新资产”查看结果。`);
    } catch (err) {
      const responseDetail =
        typeof err === "object" &&
        err !== null &&
        "response" in err &&
        typeof err.response === "object" &&
        err.response !== null &&
        "data" in err.response &&
        typeof err.response.data === "object" &&
        err.response.data !== null &&
        "detail" in err.response.data &&
        typeof err.response.data.detail === "string"
          ? err.response.data.detail
          : "";
      const detail = responseDetail || (err instanceof Error ? err.message : "");
      setError(detail || "AI 图片生成失败，请确认已配置图片生成模型。");
    } finally {
      setIsGenerating(false);
    }
  }

  async function handleDescribeImage() {
    if (!imageUrl.trim()) {
      setError("请先填写图片 URL。");
      return;
    }
    setIsDescribing(true);
    setError(null);
    setMessage(null);
    try {
      const result = await describeImageWithAi({
        image_url: imageUrl.trim(),
        instruction: "提炼这张图片适合小红书发布的卖点、风格和标题方向。",
      });
      setDescription(result.text);
      setMessage("图片描述已生成。");
    } catch {
      setError("图片描述失败，请确认已配置支持视觉理解的图片模型。");
    } finally {
      setIsDescribing(false);
    }
  }

  function openRefPicker(mode: "reference" | "describe") {
    setPickerMode(mode);
    setPickerUrlInput("");
    setRefPickerOpen(true);
  }

  function handlePickerSelect(url: string) {
    if (pickerMode === "reference") {
      setReferenceImages((prev) => {
        if (prev.includes(url)) return prev;
        if (prev.length >= RUNNINGHUB_CURRENT_REFERENCE_IMAGE_LIMIT) {
          setError(
            `当前 RunningHub 图生图工作流最多支持 ${RUNNINGHUB_CURRENT_REFERENCE_IMAGE_LIMIT} 张参考图。`,
          );
          return prev;
        }
        return [...prev, url];
      });
    } else {
      setImageUrl(url);
    }
    setRefPickerOpen(false);
  }

  function handlePickerUrlAdd() {
    const trimmed = pickerUrlInput.trim();
    if (!trimmed) return;
    handlePickerSelect(trimmed);
  }

  async function handleUploadFile(file: File) {
    try {
      const uploaded = await uploadAssetFile(file);
      const newItem: UserImageFile = {
        file_name: uploaded.file_name,
        url: uploaded.download_url,
        size: uploaded.size,
      };
      setUserImages((prev) => [newItem, ...prev]);
      addFinalPublishImage({
        url: uploaded.download_url,
        publishPath: uploaded.download_url,
        source: "manual",
        label: uploaded.file_name,
      });
    } catch {
      setError("文件上传失败。");
    }
    return false; // prevent antd auto-upload
  }

  function handleClearDraftContext() {
    if (draftContext && isWechatOfficialDraftContext(draftContext)) {
      clearWechatOfficialImageStudioDraftContext();
    } else {
      clearImageStudioDraftContext();
    }
    setDraftContext(null);
    setFinalPublishImages([]);
    setMessage("已清除草稿上下文，当前图片工坊内容不会再自动关联草稿。");
  }

  async function handleAttachGeneratedToWechatDraft() {
    if (!draftContext || !isWechatOfficialDraftContext(draftContext) || !generatedPreview) return;
    setIsAttachingDraftAsset(true);
    setError(null);
    try {
      await addDraftAsset(draftContext.draft_id, { asset_type: "image", url: generatedPreview });
      setMessage("已挂到草稿本地资产；material_upload_blocked：不上传公众号素材。");
    } catch (err) {
      setError(err instanceof Error ? err.message : "回挂到公众号草稿失败，请稍后重试。");
    } finally {
      setIsAttachingDraftAsset(false);
    }
  }

  async function handleSendFinalImagesToPublish() {
    if (!draftContext) return;
    if (isWechatOfficialDraftContext(draftContext)) {
      setMessage("公众号图片工坊第一版只做生成/整理/下载和本地资产回挂，material_upload_blocked：不上传公众号素材，也不送发布中心。");
      return;
    }
    if (finalPublishImages.length === 0) {
      setError("请先选择至少 1 张最终发布图片。可以使用原图、上传图或 AI 生成图。");
      return;
    }
    setIsSendingPublish(true);
    setError(null);
    setMessage(null);
    try {
      const job = await sendDraftToPublish(draftContext.draft_id, {
        publish_mode: "immediate",
        asset_file_paths: finalPublishImages.map((image) => image.publishPath),
      });
      clearImageStudioDraftContext();
      setDraftContext(null);
      setFinalPublishImages([]);
      setMessage(`已创建发布中心待发布任务 #${job.id}，不会自动发布。`);
      navigate(`/platforms/xhs/publish?jobId=${job.id}`);
    } catch (err) {
      const detail = err instanceof Error ? err.message : "送发布中心失败，请稍后重试。";
      setError(detail);
    } finally {
      setIsSendingPublish(false);
    }
  }

  useEffect(() => {
    const searchParams = new URLSearchParams(location.search);
    const shouldLoadDraftContext = searchParams.get("from") === "draft";
    if (!shouldLoadDraftContext) return;
    const isWechatOfficialRoute = location.pathname.startsWith("/platforms/wechat-official/");
    const context: ImageStudioDraftContext | null = isWechatOfficialRoute
      ? loadWechatOfficialImageStudioDraftContext({ requireFresh: true })
      : loadImageStudioDraftContext({ requireFresh: true });
    if (isWechatOfficialRoute) {
      navigate("/platforms/wechat-official/image-studio", { replace: true });
    } else {
      navigate("/platforms/xhs/image-studio", { replace: true });
    }
    if (!context) {
      setMessage("草稿上下文已过期，请从草稿工坊重新进入图片工坊。");
      return;
    }
    setDraftContext(context);
    if (isWechatOfficialDraftContext(context)) {
      setFinalPublishImages([]);
    } else {
      const firstCandidate = context.candidate_images
        .map((image, index) => candidateToFinalImage(image, index))
        .find((image): image is FinalPublishImage => Boolean(image));
      setFinalPublishImages(firstCandidate ? [firstCandidate] : []);
    }
    setPrompt((current) => (current.trim() ? current : buildDraftImagePrompt(context)));
    setReferenceImages((current) => {
      if (current.length > 0) return current;
      return context.candidate_images
        .map((image) => image.url)
        .filter((url, index, urls) => urls.indexOf(url) === index)
        .slice(0, RUNNINGHUB_CURRENT_REFERENCE_IMAGE_LIMIT);
    });
  }, [location.pathname, location.search, navigate]);

  useEffect(() => {
    void loadAssets();
  }, []);

  const generatedFinalPublishPath = generatedPreview ? (generatedMediaPath ?? generatedPreview) : "";
  const isGeneratedFinalPublishPathValid = Boolean(
    generatedPreview && isPublishableFinalImagePath(generatedFinalPublishPath),
  );
  const isGeneratedFinalPublishSelected = Boolean(
    generatedPreview && isFinalPublishImageSelected(generatedFinalPublishPath),
  );

  return (
    <div>
      <PageHeader
        eyebrow={isWechatOfficialDraftContext(draftContext) ? "WeChat Official Image Studio" : "XHS Image Studio"}
        title="图片工坊"
        description={isWechatOfficialDraftContext(draftContext) ? "AI 图片生成、图片描述、整理公众号草稿候选图；material_upload_blocked：不上传公众号素材。" : "AI 图片生成、图片描述、沉淀图片资产，赋能小红书内容创作。"}
        action={
          <Button
            icon={<ReloadOutlined />}
            onClick={loadAssets}
            loading={isLoading}
          >
            刷新资产
          </Button>
        }
      />

      {error && (
        <Alert
          type="error"
          message={error}
          showIcon
          closable
          onClose={() => setError(null)}
          style={{ marginBottom: 16 }}
        />
      )}
      {message && (
        <Alert
          type="success"
          message={message}
          showIcon
          closable
          onClose={() => setMessage(null)}
          style={{ marginBottom: 16 }}
        />
      )}

      {draftContext && (
        <Card
          size="small"
          title={
            <Space>
              <InboxOutlined /> 来自草稿
            </Space>
          }
          extra={
            <Button size="small" type="link" onClick={handleClearDraftContext}>
              清除关联
            </Button>
          }
          style={{ marginBottom: 16, borderColor: "#7c4d12", background: "linear-gradient(135deg, rgba(124,77,18,0.18), rgba(20,20,20,0.72))" }}
        >
          <Row gutter={[16, 12]}>
            <Col xs={24} md={15}>
              <Space direction="vertical" size={6} style={{ width: "100%" }}>
                <Text type="secondary" style={{ fontSize: 12 }}>
                  草稿 #{draftContext.draft_id}{draftContext.draft_name ? ` · ${draftContext.draft_name}` : ""}
                </Text>
                <Text strong>{draftContext.title || "未命名草稿"}</Text>
                <Paragraph ellipsis={{ rows: 3, expandable: true, symbol: "展开" }} style={{ marginBottom: 0 }}>
                  {draftContext.body || "草稿正文为空。"}
                </Paragraph>
                {draftContext.tags.length > 0 && (
                  <Space size={4} wrap>
                    {draftContext.tags.map((tag) => (
                      <Tag key={`${tag.id ?? tag.name}-${tag.name}`} color="gold">#{tag.name}</Tag>
                    ))}
                  </Space>
                )}
              </Space>
            </Col>
            <Col xs={24} md={9}>
              <Space direction="vertical" size={8} style={{ width: "100%" }}>
                <Text type="secondary" style={{ fontSize: 12 }}>
                  候选图 {draftContext.candidate_images.length} 张；已带入 {draftReferenceUrls.length} 张参考图（上限 {RUNNINGHUB_CURRENT_REFERENCE_IMAGE_LIMIT} 张）
                </Text>
                <div style={{ maxHeight: 220, overflowY: "auto", paddingRight: 4 }}>
                  <Space size={8} wrap>
                    {draftContext.candidate_images.map((image, index) => {
                      const finalImage = candidateToFinalImage(image, index);
                      const isSelected = finalImage ? isFinalPublishImageSelected(finalImage.publishPath) : false;
                      return (
                        <div key={`${image.url}-${index}`} style={{ width: 72 }}>
                          <div style={{ height: 56, borderRadius: 6, overflow: "hidden", background: "#1a1a1a", border: "1px solid #3b2a12" }}>
                            {isRenderableImage(image.url) ? (
                              <img src={image.url} alt={`candidate-${index}`} style={{ width: "100%", height: "100%", objectFit: "cover" }} />
                            ) : (
                              <PictureOutlined style={{ fontSize: 20, color: "#666", margin: 18 }} />
                            )}
                          </div>
                          <Text type="secondary" ellipsis style={{ display: "block", fontSize: 10, marginTop: 2 }}>
                            {candidateImageSourceLabel(image.source)}
                          </Text>
                          {!isWechatOfficialDraftContext(draftContext) && finalImage && (
                            <Button
                              size="small"
                              type={isSelected ? "default" : "link"}
                              disabled={isSelected}
                              onClick={() => addFinalPublishImage(finalImage)}
                              style={{ width: "100%", padding: 0, fontSize: 11 }}
                            >
                              {isSelected ? "已加入" : "加入最终"}
                            </Button>
                          )}
                        </div>
                      );
                    })}
                  </Space>
                </div>
                {draftReferenceUrls.length > 0 && referenceImages.length === 0 && (
                  <Button size="small" onClick={() => setReferenceImages(draftReferenceUrls)}>
                    使用候选图作为参考图
                  </Button>
                )}
              </Space>
            </Col>
          </Row>
        </Card>
      )}

      {/* ---- Top Row: Two tool cards ---- */}
      <Row gutter={[16, 16]} style={{ marginBottom: 24 }}>
        {/* Left Card: AI Image Generation */}
        <Col xs={24} md={14}>
          <Card
            title={
              <Space>
                <StarOutlined /> AI 图片生成
              </Space>
            }
            extra={
              <Text type="secondary" style={{ fontSize: 11 }}>
                需配置图片生成模型（如 gpt-image-2、豆包 Seedream）
              </Text>
            }
          >
            <TextArea
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              placeholder="充满活力的特写编辑肖像，模特眼神犀利，头戴雕塑感帽子，色彩拼接丰富，具有 Vogue 杂志封面的美学风格..."
              rows={4}
              disabled={isGenerating}
              style={{ marginBottom: 12 }}
            />

            {/* Reference images */}
            <div style={{ marginBottom: 12 }}>
              <Text
                type="secondary"
                style={{ fontSize: 12, marginBottom: 6, display: "block" }}
              >
                参考图（当前 RunningHub 图生图工作流最多支持 2 张）
              </Text>
              <Space size={8} wrap>
                {referenceImages.map((url, idx) => (
                  <div
                    key={idx}
                    style={{
                      position: "relative",
                      width: 60,
                      height: 60,
                      borderRadius: 4,
                      overflow: "hidden",
                      border: "1px solid #333",
                    }}
                  >
                    {isRenderableImage(url) ? (
                      <img
                        src={url}
                        alt={`ref-${idx}`}
                        style={{
                          width: 60,
                          height: 60,
                          objectFit: "cover",
                        }}
                      />
                    ) : (
                      <div
                        style={{
                          width: 60,
                          height: 60,
                          display: "flex",
                          alignItems: "center",
                          justifyContent: "center",
                          background: "#1a1a1a",
                        }}
                      >
                        <PictureOutlined style={{ fontSize: 20, color: "#666" }} />
                      </div>
                    )}
                    <Button
                      type="text"
                      size="small"
                      danger
                      icon={<DeleteOutlined />}
                      onClick={() =>
                        setReferenceImages((prev) =>
                          prev.filter((_, i) => i !== idx),
                        )
                      }
                      style={{
                        position: "absolute",
                        top: 0,
                        right: 0,
                        width: 18,
                        height: 18,
                        padding: 0,
                        minWidth: 18,
                        borderRadius: "0 4px 0 4px",
                        background: "rgba(0,0,0,0.6)",
                      }}
                    />
                  </div>
                ))}
                {/* Add placeholder */}
                <div
                  onClick={() => {
                    if (!referenceLimitReached) openRefPicker("reference");
                  }}
                  aria-disabled={referenceLimitReached}
                  title={referenceLimitReached ? `已达上限：最多 ${RUNNINGHUB_CURRENT_REFERENCE_IMAGE_LIMIT} 张参考图` : "添加参考图"}
                  style={{
                    width: 60,
                    height: 60,
                    borderRadius: 4,
                    border: referenceLimitReached ? "1px dashed #5a3a1a" : "1px dashed #444",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    cursor: referenceLimitReached ? "not-allowed" : "pointer",
                    background: referenceLimitReached ? "rgba(90,58,26,0.18)" : "#1a1a1a",
                    color: referenceLimitReached ? "#b08a55" : "#666",
                    fontSize: referenceLimitReached ? 11 : 20,
                    textAlign: "center",
                    padding: referenceLimitReached ? 4 : 0,
                    lineHeight: 1.2,
                  }}
                >
                  {referenceLimitReached ? "已达上限" : <PlusOutlined style={{ fontSize: 20, color: "#666" }} />}
                </div>
              </Space>
            </div>

            <Row gutter={[8, 8]} align="middle" style={{ marginBottom: 12 }}>
              <Col>
                <Text type="secondary" style={{ fontSize: 12 }}>
                  画幅比例
                </Text>
              </Col>
              <Col flex="auto">
                <Select<ImageAspectRatio>
                  value={aspectRatio}
                  onChange={setAspectRatio}
                  disabled={isGenerating}
                  style={{ minWidth: 180 }}
                  options={[
                    { value: "auto", label: "跟随参考图" },
                    { value: "3:4", label: "小红书竖图 3:4" },
                    { value: "4:3", label: "横屏 4:3" },
                    { value: "1:1", label: "方图 1:1" },
                    { value: "16:9", label: "宽屏 16:9" },
                    { value: "9:16", label: "长竖屏 9:16" },
                  ]}
                />
              </Col>
            </Row>

            {/* Controls row */}
            <Row
              justify="space-between"
              align="middle"
              style={{ marginBottom: 12 }}
            >
              <Col>
                <Checkbox
                  checked={saveToAssets}
                  onChange={(e) => setSaveToAssets(e.target.checked)}
                >
                  保存到 AI 图片资产
                </Checkbox>
              </Col>
              <Col>
                <Space>
                  <Button
                    onClick={() => { setPrompt(""); setReferenceImages([]); setAspectRatio("auto"); setGeneratedPreview(null); setGeneratedMediaPath(null); setSaveToAssets(true); }}
                    disabled={isGenerating}
                  >
                    重置
                  </Button>
                  <Button
                    type="primary"
                    icon={<RobotOutlined />}
                    onClick={handleGenerate}
                    loading={isGenerating}
                  >
                    生成
                  </Button>
                </Space>
              </Col>
            </Row>

            {/* Generated result */}
            {generatedPreview && (
              <div style={{ marginTop: 8 }}>
                <Text
                  type="secondary"
                  style={{ fontSize: 12, marginBottom: 6, display: "block" }}
                >
                  生成结果
                </Text>
                <div
                  style={{
                    background: "#1a1a1a",
                    borderRadius: 6,
                    padding: 8,
                    textAlign: "center",
                  }}
                >
                  <Image
                    src={generatedPreview}
                    alt="generated"
                    style={{ maxHeight: 240, objectFit: "contain" }}
                  />
                  <Space style={{ marginTop: 8 }} wrap>
                    {draftContext && !isWechatOfficialDraftContext(draftContext) && (
                      <Button
                        type="primary"
                        icon={<PlusOutlined />}
                        onClick={() => {
                          if (!generatedPreview || !isGeneratedFinalPublishPathValid) return;
                          addFinalPublishImage({
                            url: generatedPreview,
                            publishPath: generatedFinalPublishPath,
                            source: "generated",
                            label: "AI 生成图",
                          });
                        }}
                        disabled={
                          isGenerating ||
                          !generatedPreview ||
                          !isGeneratedFinalPublishPathValid ||
                          isGeneratedFinalPublishSelected
                        }
                        title={!isGeneratedFinalPublishPathValid ? "生成图需要先保存为服务器媒体资产，或返回可访问图片 URL" : undefined}
                      >
                        {isGeneratedFinalPublishSelected ? "已加入最终发布" : "加入最终发布图片"}
                      </Button>
                    )}
                    {isWechatOfficialDraftContext(draftContext) && (
                      <>
                        <Button
                          type="primary"
                          icon={<InboxOutlined />}
                          onClick={handleAttachGeneratedToWechatDraft}
                          loading={isAttachingDraftAsset}
                          disabled={isGenerating || !generatedPreview}
                        >
                          回挂到公众号草稿
                        </Button>
                        <Tag color="red">material_upload_blocked · 不上传公众号素材</Tag>
                      </>
                    )}
                    {!saveToAssets && (
                      <Button
                        size="small"
                        type="link"
                        onClick={() => {
                          // Re-generate with save flag
                          setSaveToAssets(true);
                          setMessage("下次生成将自动保存到 AI 资产。");
                        }}
                      >
                        保存到 AI 资产
                      </Button>
                    )}
                  </Space>
                </div>
              </div>
            )}
          </Card>
        </Col>

        {/* Right Card: Image Description */}
        <Col xs={24} md={10}>
          <Card
            title={
              <Space>
                <FileImageOutlined /> 图片描述
              </Space>
            }
            extra={
              <Text type="secondary" style={{ fontSize: 11 }}>
                需配置多模态模型（如 GPT-4o）
              </Text>
            }
          >
            <Space.Compact style={{ width: "100%", marginBottom: 12 }}>
              <Input
                value={imageUrl}
                onChange={(e) => setImageUrl(e.target.value)}
                placeholder="图片 URL"
                disabled={isGenerating}
              />
              <Button
                icon={<PictureOutlined />}
                onClick={() => openRefPicker("describe")}
              >
                从资产选择
              </Button>
            </Space.Compact>
            <Button
              onClick={handleDescribeImage}
              loading={isDescribing}
              block
              style={{ marginBottom: 12 }}
            >
              生成描述
            </Button>
            {description && (
              <Paragraph
                style={{
                  background: "#262626",
                  padding: 12,
                  borderRadius: 6,
                  fontSize: 13,
                  margin: 0,
                }}
              >
                {description}
              </Paragraph>
            )}
          </Card>
        </Col>
      </Row>

      {draftContext && !isWechatOfficialDraftContext(draftContext) && (
        <Card
          title={
            <Space>
              <SendOutlined /> 最终发布图片
              <Tag color="gold">已选择 {finalPublishImages.length} 张</Tag>
            </Space>
          }
          style={{ marginBottom: 24 }}
          extra={
            <Space>
              <Button
                size="small"
                onClick={() => setFinalPublishImages([])}
                disabled={finalPublishImages.length === 0 || isSendingPublish}
              >
                清空选择
              </Button>
              <Button
                type="primary"
                icon={<SendOutlined />}
                onClick={handleSendFinalImagesToPublish}
                loading={isSendingPublish}
              >
                送入发布中心
              </Button>
            </Space>
          }
        >
          <Paragraph type="secondary" style={{ marginTop: 0 }}>
            发布中心将按当前顺序使用这些图片。可以从原图、上传图或 AI 生成图中选择。
          </Paragraph>
          {finalPublishImages.length === 0 ? (
            <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无最终发布图片。" />
          ) : (
            <Row gutter={[12, 12]}>
              {finalPublishImages.map((image, index) => (
                <Col xs={12} sm={8} md={6} lg={4} key={image.key}>
                  <Card size="small" styles={{ body: { padding: 8 } }}>
                    <div
                      style={{
                        position: "relative",
                        height: 120,
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "center",
                        marginBottom: 6,
                        overflow: "hidden",
                        borderRadius: 4,
                        background: "#1a1a1a",
                      }}
                    >
                      <Tag color="gold" style={{ position: "absolute", left: 6, top: 6, zIndex: 1 }}>
                        #{index + 1}
                      </Tag>
                      {isRenderableImage(image.url) ? (
                        <Image
                          alt={image.label}
                          src={image.url}
                          style={{ maxHeight: 120, objectFit: "contain" }}
                        />
                      ) : (
                        <PictureOutlined style={{ fontSize: 28, color: "#555" }} />
                      )}
                    </div>
                    <Text strong ellipsis style={{ display: "block", fontSize: 12 }}>
                      {image.label}
                    </Text>
                    <Space size={4} style={{ width: "100%", marginTop: 6 }}>
                      <Button
                        size="small"
                        icon={<ArrowUpOutlined />}
                        disabled={index === 0 || isSendingPublish}
                        onClick={() => moveFinalPublishImage(index, -1)}
                      />
                      <Button
                        size="small"
                        icon={<ArrowDownOutlined />}
                        disabled={index === finalPublishImages.length - 1 || isSendingPublish}
                        onClick={() => moveFinalPublishImage(index, 1)}
                      />
                      <Button
                        size="small"
                        danger
                        icon={<DeleteOutlined />}
                        disabled={isSendingPublish}
                        onClick={() => removeFinalPublishImage(image.publishPath)}
                      />
                    </Space>
                  </Card>
                </Col>
              ))}
            </Row>
          )}
        </Card>
      )}

      {/* ---- Bottom: Tabs ---- */}
      <Tabs
        defaultActiveKey="ai_assets"
        items={[
          {
            key: "ai_assets",
            label: (
              <Space>
                <StarOutlined /> AI 图片资产
              </Space>
            ),
            children: (
              <>
                {isLoading ? (
                  <div style={{ textAlign: "center", padding: 48 }}>
                    <Spin tip="正在加载 AI 图片资产..." />
                  </div>
                ) : assets.length === 0 ? (
                  <Empty
                    image={Empty.PRESENTED_IMAGE_SIMPLE}
                    description="暂无 AI 图片资产。"
                    style={{ padding: 32 }}
                  />
                ) : (
                  <Row gutter={[12, 12]}>
                    {assets.map((asset) => (
                      <Col xs={12} sm={8} md={6} key={asset.id}>
                        <Card
                          size="small"
                          hoverable
                          styles={{ body: { padding: 8 } }}
                        >
                          <div
                            style={{
                              height: 120,
                              display: "flex",
                              alignItems: "center",
                              justifyContent: "center",
                              marginBottom: 6,
                              overflow: "hidden",
                              borderRadius: 4,
                              background: "#1a1a1a",
                            }}
                          >
                            {isRenderableImage(asset.file_path) ? (
                              <Image
                                alt={asset.prompt}
                                src={asset.file_path}
                                style={{
                                  maxHeight: 120,
                                  objectFit: "contain",
                                }}
                              />
                            ) : (
                              <PictureOutlined
                                style={{ fontSize: 28, color: "#555" }}
                              />
                            )}
                          </div>
                          <Text
                            strong
                            ellipsis
                            style={{ fontSize: 12, display: "block" }}
                          >
                            {asset.prompt}
                          </Text>
                          <div style={{ marginTop: 4 }}>
                            <Tag
                              style={{
                                fontSize: 10,
                                padding: "0 4px",
                                margin: 0,
                              }}
                            >
                              {asset.model_name || "image model"}
                            </Tag>
                            <Text
                              type="secondary"
                              style={{ fontSize: 10, marginLeft: 4 }}
                            >
                              {formatShanghaiTime(asset.created_at)}
                            </Text>
                          </div>
                          {draftContext && !isWechatOfficialDraftContext(draftContext) && (
                            <Button
                              type="link"
                              size="small"
                              icon={<PlusOutlined />}
                              disabled={isFinalPublishImageSelected(asset.file_path)}
                              onClick={() => addFinalPublishImage({
                                url: asset.file_path,
                                publishPath: asset.file_path,
                                source: "asset",
                                label: "AI 图片资产",
                              })}
                              style={{ width: "100%", marginTop: 4 }}
                            >
                              {isFinalPublishImageSelected(asset.file_path) ? "已加入最终" : "加入最终"}
                            </Button>
                          )}
                          <Button
                            type="text" danger size="small" icon={<DeleteOutlined />}
                            onClick={async () => {
                              try {
                                await deleteGeneratedImageAsset(asset.id);
                                setAssets((prev) => prev.filter((a) => a.id !== asset.id));
                                removeFinalPublishImage(asset.file_path);
                              } catch { /* global interceptor shows error */ }
                            }}
                            style={{ width: "100%", marginTop: 4 }}
                          >
                            删除
                          </Button>
                        </Card>
                      </Col>
                    ))}
                  </Row>
                )}
              </>
            ),
          },
          {
            key: "user_images",
            label: (
              <Space>
                <PictureOutlined /> 普通图片资产
              </Space>
            ),
            children: (
              <>
                <div style={{ marginBottom: 16 }}>
                  <Upload
                    accept="image/*"
                    showUploadList={false}
                    beforeUpload={(file) => {
                      void handleUploadFile(file);
                      return false;
                    }}
                  >
                    <Button icon={<UploadOutlined />}>上传图片</Button>
                  </Upload>
                </div>
                {userImages.length === 0 ? (
                  <Empty
                    image={Empty.PRESENTED_IMAGE_SIMPLE}
                    description="暂无普通图片资产。上传图片后将显示在这里。"
                    style={{ padding: 32 }}
                  />
                ) : (
                  <Row gutter={[12, 12]}>
                    {userImages.map((img) => (
                      <Col xs={12} sm={8} md={6} key={img.file_name}>
                        <Card
                          size="small"
                          hoverable
                          styles={{ body: { padding: 8 } }}
                        >
                          <div
                            style={{
                              height: 120,
                              display: "flex",
                              alignItems: "center",
                              justifyContent: "center",
                              marginBottom: 6,
                              overflow: "hidden",
                              borderRadius: 4,
                              background: "#1a1a1a",
                            }}
                          >
                            <Image
                              alt={img.file_name}
                              src={img.url}
                              style={{
                                maxHeight: 120,
                                objectFit: "contain",
                              }}
                            />
                          </div>
                          <Text
                            strong
                            ellipsis
                            style={{ fontSize: 12, display: "block" }}
                          >
                            {img.file_name}
                          </Text>
                          <Text type="secondary" style={{ fontSize: 10 }}>
                            {(img.size / 1024).toFixed(1)} KB
                          </Text>
                          {draftContext && !isWechatOfficialDraftContext(draftContext) && (
                            <Button
                              type="link"
                              size="small"
                              icon={<PlusOutlined />}
                              disabled={isFinalPublishImageSelected(img.url)}
                              onClick={() => addFinalPublishImage({
                                url: img.url,
                                publishPath: img.url,
                                source: "manual",
                                label: img.file_name,
                              })}
                              style={{ width: "100%", marginTop: 4 }}
                            >
                              {isFinalPublishImageSelected(img.url) ? "已加入最终" : "加入最终"}
                            </Button>
                          )}
                          <Button
                            type="text" danger size="small" icon={<DeleteOutlined />}
                            onClick={async () => {
                              try {
                                await deleteUserImage(img.file_name);
                                setUserImages((prev) => prev.filter((i) => i.file_name !== img.file_name));
                                removeFinalPublishImage(img.url);
                              } catch { /* global interceptor shows error */ }
                            }}
                            style={{ width: "100%", marginTop: 4 }}
                          >
                            删除
                          </Button>
                        </Card>
                      </Col>
                    ))}
                  </Row>
                )}
              </>
            ),
          },
        ]}
      />

      {/* ---- Reference Image Picker Modal ---- */}
      <Modal
        title="选择图片"
        open={refPickerOpen}
        onCancel={() => setRefPickerOpen(false)}
        footer={null}
        width={640}
        destroyOnClose
      >
        <Tabs
          defaultActiveKey="user_images"
          items={[
            {
              key: "user_images",
              label: (
                <Space>
                  <PictureOutlined /> 普通图片资产
                </Space>
              ),
              children:
                userImages.length === 0 ? (
                  <Empty
                    image={Empty.PRESENTED_IMAGE_SIMPLE}
                    description="暂无普通图片资产。"
                    style={{ padding: 24 }}
                  />
                ) : (
                  <Row gutter={[8, 8]}>
                    {userImages.map((img) => (
                      <Col span={6} key={img.file_name}>
                        <div
                          onClick={() => handlePickerSelect(img.url)}
                          style={{
                            cursor: "pointer",
                            borderRadius: 4,
                            overflow: "hidden",
                            border: "1px solid #333",
                            height: 80,
                            display: "flex",
                            alignItems: "center",
                            justifyContent: "center",
                            background: "#1a1a1a",
                          }}
                        >
                          <img
                            src={img.url}
                            alt={img.file_name}
                            style={{
                              maxHeight: 80,
                              maxWidth: "100%",
                              objectFit: "contain",
                            }}
                          />
                        </div>
                      </Col>
                    ))}
                  </Row>
                ),
            },
            ...(pickerMode === "describe"
              ? [
                  {
                    key: "ai_assets",
                    label: (
                      <Space>
                        <StarOutlined /> AI 图片资产
                      </Space>
                    ),
                    children:
                      assets.length === 0 ? (
                        <Empty
                          image={Empty.PRESENTED_IMAGE_SIMPLE}
                          description="暂无 AI 图片资产。"
                          style={{ padding: 24 }}
                        />
                      ) : (
                        <Row gutter={[8, 8]}>
                          {assets.map((asset) => (
                            <Col span={6} key={asset.id}>
                              <div
                                onClick={() => handlePickerSelect(asset.file_path)}
                                style={{
                                  cursor: "pointer",
                                  borderRadius: 4,
                                  overflow: "hidden",
                                  border: "1px solid #333",
                                  height: 80,
                                  display: "flex",
                                  alignItems: "center",
                                  justifyContent: "center",
                                  background: "#1a1a1a",
                                }}
                              >
                                {isRenderableImage(asset.file_path) ? (
                                  <img
                                    src={asset.file_path}
                                    alt={asset.prompt}
                                    style={{
                                      maxHeight: 80,
                                      maxWidth: "100%",
                                      objectFit: "contain",
                                    }}
                                  />
                                ) : (
                                  <PictureOutlined
                                    style={{ fontSize: 24, color: "#555" }}
                                  />
                                )}
                              </div>
                            </Col>
                          ))}
                        </Row>
                      ),
                  },
                  {
                    key: "url",
                    label: (
                      <Space>
                        <LinkOutlined /> URL
                      </Space>
                    ),
                    children: (
                      <Space.Compact style={{ width: "100%" }}>
                        <Input
                          value={pickerUrlInput}
                          onChange={(e) => setPickerUrlInput(e.target.value)}
                          placeholder="输入图片 URL"
                          onPressEnter={handlePickerUrlAdd}
                        />
                        <Button type="primary" onClick={handlePickerUrlAdd}>
                          添加
                        </Button>
                      </Space.Compact>
                    ),
                  },
                ]
              : []),
          ]}
        />
      </Modal>
    </div>
  );
}
