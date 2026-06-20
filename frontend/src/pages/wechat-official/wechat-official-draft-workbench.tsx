import { useMemo, useState } from "react";
import { Alert, Button, Descriptions, Space, Typography } from "antd";
import { SafetyCertificateOutlined } from "@ant-design/icons";

import { DraftWorkbenchShell, useDraftWorkbench } from "../../components/draft-workbench";
import type { DraftWorkbenchDryRunResult } from "../../components/draft-workbench";

import { createWechatOfficialDraftWorkbenchAdapter } from "./wechat-official-draft-workbench-adapter";

const { Paragraph } = Typography;

export function WechatOfficialDraftWorkbench() {
  const adapter = useMemo(() => createWechatOfficialDraftWorkbenchAdapter(), []);
  const controller = useDraftWorkbench(adapter);
  const [dryRunResult, setDryRunResult] = useState<DraftWorkbenchDryRunResult | null>(null);

  async function handleDryRun() {
    const result = await controller.dryRunSelectedDraft({});
    setDryRunResult(result);
  }

  return (
    <DraftWorkbenchShell
      adapter={adapter}
      controller={controller}
      renderAssistantExtras={() => (
        <Space direction="vertical" size={12} style={{ width: "100%" }}>
          <Alert
            type="warning"
            showIcon
            message="真实发布保持阻断"
            description="公众号草稿工坊当前只支持编辑和 dry-run 校验，不执行真实发布、预览发送或群发。"
          />
          <Button type="primary" icon={<SafetyCertificateOutlined />} onClick={() => void handleDryRun()} disabled={!controller.selectedDraft}>
            执行 dry-run 校验
          </Button>
          {dryRunResult ? (
            <Descriptions column={1} size="small" bordered>
              <Descriptions.Item label="标题">{dryRunResult.checks.title}</Descriptions.Item>
              <Descriptions.Item label="正文">{dryRunResult.checks.body}</Descriptions.Item>
              <Descriptions.Item label="外链图片">{dryRunResult.checks.external_images}</Descriptions.Item>
              <Descriptions.Item label="真实发布">{dryRunResult.publish_blocked ? "blocked" : "unexpected"}</Descriptions.Item>
              <Descriptions.Item label="群发">{dryRunResult.sendall_blocked ? "blocked" : "unexpected"}</Descriptions.Item>
            </Descriptions>
          ) : null}
          <Paragraph type="secondary" style={{ marginBottom: 0 }}>
            草稿来自内容库生成后的独立副本；这里不展示候选文章，也不依赖来源引用。
          </Paragraph>
        </Space>
      )}
    />
  );
}
