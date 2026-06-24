import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Alert, Button, Descriptions, Space, Tag, Typography, message as antMessage } from "antd";
import { PictureOutlined, SafetyCertificateOutlined } from "@ant-design/icons";

import { DraftWorkbenchShell, useDraftWorkbench } from "../../components/draft-workbench";
import type { DraftWorkbenchDryRunResult } from "../../components/draft-workbench";
import { fetchDraftAssets, fetchWechatOfficialContentDetail, updateDraft } from "../../lib/api";
import type { DraftAsset } from "../../lib/api";
import type { WechatOfficialContentDetail } from "../../types";

import { createWechatOfficialDraftWorkbenchAdapter } from "./wechat-official-draft-workbench-adapter";
import {
  extractWechatOfficialDraftImageCandidates,
  saveWechatOfficialImageStudioDraftContext,
  wechatOfficialDraftToImageStudioContext,
} from "./wechat-official-image-studio-context";

const { Paragraph } = Typography;

export function WechatOfficialDraftWorkbench() {
  const navigate = useNavigate();
  const adapter = useMemo(() => createWechatOfficialDraftWorkbenchAdapter(), []);
  const controller = useDraftWorkbench(adapter);
  const [dryRunResult, setDryRunResult] = useState<DraftWorkbenchDryRunResult | null>(null);
  const [sourceDetail, setSourceDetail] = useState<WechatOfficialContentDetail | null>(null);
  const [draftAssets, setDraftAssets] = useState<DraftAsset[]>([]);
  const [isSendingImageStudio, setIsSendingImageStudio] = useState(false);

  const selectedDraft = controller.selectedDraft;
  const sourceArticleId = selectedDraft?.source_article_id ?? null;

  useEffect(() => {
    setSourceDetail(null);
    setDraftAssets([]);
    if (!selectedDraft) return;
    let cancelled = false;
    (async () => {
      try {
        const [assets, detail] = await Promise.all([
          fetchDraftAssets(selectedDraft.id),
          sourceArticleId ? fetchWechatOfficialContentDetail(sourceArticleId) : Promise.resolve(null),
        ]);
        if (!cancelled) {
          setDraftAssets(assets.items);
          setSourceDetail(detail);
        }
      } catch {
        if (!cancelled) {
          setDraftAssets([]);
          setSourceDetail(null);
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [selectedDraft?.id, sourceArticleId]);

  async function handleDryRun() {
    const result = await controller.dryRunSelectedDraft({});
    setDryRunResult(result);
  }

  async function handleSendToImageStudio() {
    if (!controller.selectedDraft) {
      antMessage.warning("请先选择一个公众号草稿，再进入图片工坊。");
      return;
    }
    setIsSendingImageStudio(true);
    try {
      const saved = await updateDraft(controller.selectedDraft.id, {
        draft_name: controller.draftName,
        title: controller.title,
        body: controller.body,
        tags: controller.tags,
      });
      const sourceArticleId = saved.source_article_id ?? null;
      const [assets, detail] = await Promise.all([
        fetchDraftAssets(saved.id),
        sourceArticleId ? fetchWechatOfficialContentDetail(sourceArticleId) : Promise.resolve(null),
      ]);
      const candidateImages = extractWechatOfficialDraftImageCandidates(detail, assets.items);
      const contextSaved = saveWechatOfficialImageStudioDraftContext(
        wechatOfficialDraftToImageStudioContext({ ...saved, platform: "wechat_official" }, candidateImages, sourceArticleId),
      );
      if (!contextSaved) {
        antMessage.error("草稿已保存，但浏览器无法暂存图片工坊上下文。请检查隐私模式或浏览器存储权限后重试。");
        return;
      }
      antMessage.success(
        candidateImages.length > 0
          ? `已保存草稿并带入 ${candidateImages.length} 张候选图，正在进入图片工坊。`
          : "已保存草稿，正在进入图片工坊。这个公众号草稿暂无候选图，可在图片工坊手动上传参考图；不会上传公众号素材。",
      );
      navigate("/platforms/wechat-official/image-studio?from=draft");
    } catch (error) {
      antMessage.error(error instanceof Error ? error.message : "送入图片工坊失败，请先保存草稿后重试。");
    } finally {
      setIsSendingImageStudio(false);
    }
  }

  return (
    <DraftWorkbenchShell
      adapter={adapter}
      controller={controller}
      renderEditorExtras={() => (
        <Space direction="vertical" size={8} style={{ width: "100%" }}>
          <Alert
            type="info"
            showIcon
            message="来源文章 / 分析依据"
            description={sourceDetail ? `来源文章：${sourceDetail.article.title || "未命名文章"}` : sourceArticleId ? "正在读取来源文章。" : "这个草稿暂无来源文章记录。"}
          />
          {sourceDetail ? (
            <Descriptions column={1} size="small" bordered>
              <Descriptions.Item label="原文链接">{sourceDetail.article.article_url || sourceDetail.article.content_url || "无"}</Descriptions.Item>
              <Descriptions.Item label="核心洞察">{sourceDetail.analysis?.core_insight || "待补充"}</Descriptions.Item>
              <Descriptions.Item label="爆点因子">{Array.isArray(sourceDetail.analysis?.viral_factors) ? sourceDetail.analysis.viral_factors.join("、") : sourceDetail.analysis?.viral_factors || "待补充"}</Descriptions.Item>
              <Descriptions.Item label="本地图片资产">{draftAssets.length} 张</Descriptions.Item>
            </Descriptions>
          ) : (
            <Space wrap>
              <Tag color={sourceArticleId ? "gold" : "default"}>source_article_id: {sourceArticleId ?? "none"}</Tag>
              <Tag color="blue">本地图片资产 {draftAssets.length} 张</Tag>
            </Space>
          )}
        </Space>
      )}
      renderAssistantExtras={() => (
        <Space direction="vertical" size={12} style={{ width: "100%" }}>
          <Alert
            type="warning"
            showIcon
            message="真实发布保持阻断"
            description="公众号草稿工坊当前只支持编辑和 dry-run 校验，不执行真实发布、预览发送或群发。"
          />
          <Space wrap>
            <Button type="primary" icon={<SafetyCertificateOutlined />} onClick={() => void handleDryRun()} disabled={!controller.selectedDraft}>
              执行 dry-run 校验
            </Button>
            <Button icon={<PictureOutlined />} onClick={() => void handleSendToImageStudio()} loading={isSendingImageStudio} disabled={!controller.selectedDraft}>
              整理封面/正文图
            </Button>
          </Space>
          {dryRunResult ? (
            <Descriptions column={1} size="small" bordered>
              <Descriptions.Item label="标题">{dryRunResult.checks.title}</Descriptions.Item>
              <Descriptions.Item label="正文">{dryRunResult.checks.body}</Descriptions.Item>
              <Descriptions.Item label="外链图片">{dryRunResult.checks.external_images}</Descriptions.Item>
              <Descriptions.Item label="真实发布">{dryRunResult.publish_blocked ? "blocked" : "unexpected"}</Descriptions.Item>
              <Descriptions.Item label="预览发送">{dryRunResult.preview_blocked ? "blocked" : "unexpected"}</Descriptions.Item>
              <Descriptions.Item label="群发">{dryRunResult.sendall_blocked ? "blocked" : "unexpected"}</Descriptions.Item>
            </Descriptions>
          ) : null}
          <Paragraph type="secondary" style={{ marginBottom: 0 }}>
            草稿保留来源文章和分析依据，只做本地编辑、dry-run 校验与图片工坊整理，不上传公众号素材。
          </Paragraph>
        </Space>
      )}
    />
  );
}
