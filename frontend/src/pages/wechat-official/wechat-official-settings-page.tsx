import { SyncOutlined } from "@ant-design/icons";
import { Button, Card, Form, Input, message, Space, Tag, Typography } from "antd";
import { useCallback, useEffect, useState } from "react";

import { PlatformSectionPage } from "../../platform-core/shell/platform-section-page";
import {
  fetchWechatOfficialRedfoxConfig,
  saveWechatOfficialRedfoxConfig,
  validateWechatOfficialRedfoxConfig,
} from "../../lib/api";

import type { WechatOfficialRedfoxConfig } from "../../types";

const { Paragraph } = Typography;

const cardStyle = { background: "#1f1f1f", borderColor: "#303030" };

type RedfoxConfigForm = {
  name: string;
  base_url: string;
  api_key?: string;
};

function statusColor(status?: string): string {
  if (!status) return "default";
  if (["blocked", "expired", "invalid", "failed", "rejected", "missing"].includes(status)) return "red";
  if (["planned", "partial", "pending", "unknown", "analyzing"].includes(status)) return "gold";
  if (["ready", "available", "valid", "active", "succeeded", "completed", "shortlisted"].includes(status)) return "green";
  return "default";
}

function apiErrorMessage(error: unknown, fallback: string): string {
  if (error && typeof error === "object" && "response" in error) {
    const response = (error as { response?: { data?: { detail?: unknown } } }).response;
    const detail = response?.data?.detail;
    if (typeof detail === "string" && detail.trim()) return detail;
  }
  return error instanceof Error ? error.message : fallback;
}

export function WechatOfficialSettingsPage() {
  const [redfoxConfig, setRedfoxConfig] = useState<WechatOfficialRedfoxConfig | null>(null);
  const [configured, setConfigured] = useState(false);
  const [busyAction, setBusyAction] = useState<string | null>(null);
  const [configForm] = Form.useForm<RedfoxConfigForm>();

  const configuredText = configured ? `已配置 ${redfoxConfig?.masked_api_key || "****"}` : "未配置";

  const refreshConfig = useCallback(async () => {
    setBusyAction("refresh-config");
    try {
      const response = await fetchWechatOfficialRedfoxConfig();
      setConfigured(response.configured);
      setRedfoxConfig(response.config);
      configForm.setFieldsValue({
        name: response.config?.name ?? "RedFoxHub",
        base_url: response.config?.base_url ?? "https://redfox.hk",
        api_key: "",
      });
    } catch (error) {
      message.error(apiErrorMessage(error, "Redfox 配置读取失败"));
    } finally {
      setBusyAction(null);
    }
  }, [configForm]);

  useEffect(() => {
    void refreshConfig();
  }, [refreshConfig]);

  async function runAction(actionKey: string, successText: string, action: () => Promise<void>): Promise<void> {
    setBusyAction(actionKey);
    try {
      await action();
      message.success(successText);
    } catch (error) {
      message.error(apiErrorMessage(error, "操作失败，请检查输入和后端状态。"));
    } finally {
      setBusyAction(null);
    }
  }

  const handleSaveConfig = () => runAction("save-config", "Redfox API Key 配置已保存", async () => {
    const values = await configForm.validateFields();
    const response = await saveWechatOfficialRedfoxConfig({
      name: values.name,
      base_url: values.base_url,
      api_key: String(values.api_key || "").trim() || undefined,
    });
    setConfigured(response.configured);
    setRedfoxConfig(response.config);
    configForm.setFieldValue("api_key", "");
  });

  const handleValidateConfig = () => runAction("validate-config", "Redfox 配置校验完成", async () => {
    const response = await validateWechatOfficialRedfoxConfig();
    setRedfoxConfig(response.config);
    setConfigured(Boolean(response.config?.has_api_key));
    if (!response.ok) throw new Error(response.message);
  });

  return (
    <PlatformSectionPage
      platformLabel="微信公众号"
      title="Redfox 设置"
      description="配置和校验 Redfox API Key；Redfox 只作为内容数据源。"
      safetyMessage="Redfox 只作为内容数据源"
      safetyDescription="配置 Redfox 不代表已开启公众号真实授权、素材上传、预览发送或群发发布。"
      action={<Button icon={<SyncOutlined />} loading={busyAction === "refresh-config"} onClick={() => void refreshConfig()}>刷新配置</Button>}
    >
      <Card title="Redfox API 配置" style={cardStyle}>
        <Form form={configForm} layout="vertical" initialValues={{ name: "RedFoxHub", base_url: "https://redfox.hk" }}>
          <Form.Item label="名称" name="name"><Input placeholder="RedFoxHub" /></Form.Item>
          <Form.Item label="Base URL" name="base_url"><Input placeholder="https://redfox.hk" /></Form.Item>
          <Form.Item label="API Key" name="api_key"><Input.Password placeholder="REDFOX_API_KEY；留空不会覆盖已保存 key" /></Form.Item>
        </Form>
        <Space wrap>
          <Button type="primary" loading={busyAction === "save-config"} onClick={handleSaveConfig}>保存 API Key</Button>
          <Button loading={busyAction === "validate-config"} onClick={handleValidateConfig}>校验连接</Button>
          <Tag color={statusColor(redfoxConfig?.status)}>{redfoxConfig?.status || "not_configured"}</Tag>
        </Space>
        <Paragraph type="secondary" style={{ marginTop: 12, marginBottom: 0 }}>
          API Key 仅加密保存在服务端，不返回明文；当前状态：{configuredText}{redfoxConfig?.last_error ? ` / ${redfoxConfig.last_error}` : ""}
        </Paragraph>
      </Card>
    </PlatformSectionPage>
  );
}
