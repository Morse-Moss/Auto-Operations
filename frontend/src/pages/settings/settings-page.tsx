import { useEffect, useState } from "react";
import { ApiOutlined, SafetyCertificateOutlined } from "@ant-design/icons";
import { Alert, Button, Card, Col, Form, Input, message, Row, Select, Space, Switch, Typography } from "antd";

import { PageHeader } from "../../components/layout/app-shell";
import { createFeishuAnalysisBase, ensureFeishuFields, fetchFeishuConfig, grantFeishuPermission, saveFeishuConfig, testFeishuConnection } from "../../lib/api";
import type { FeishuIntegrationConfigPayload } from "../../types";

const { Paragraph } = Typography;

type FeishuConfigFormValues = FeishuIntegrationConfigPayload;

export function SettingsPage() {
  const [feishuForm] = Form.useForm<FeishuConfigFormValues>();
  const [isLoadingFeishu, setIsLoadingFeishu] = useState(false);
  const [isSavingFeishu, setIsSavingFeishu] = useState(false);
  const [isEnsuringFields, setIsEnsuringFields] = useState(false);
  const [isTestingFeishu, setIsTestingFeishu] = useState(false);
  const [isCreatingFeishuBase, setIsCreatingFeishuBase] = useState(false);
  const [isGrantingFeishuPermission, setIsGrantingFeishuPermission] = useState(false);

  useEffect(() => {
    setIsLoadingFeishu(true);
    fetchFeishuConfig()
      .then((config) => {
        feishuForm.setFieldsValue({
          app_id: config.app_id,
          app_secret: "",
          bitable_url: config.bitable_url,
          table_id: config.table_id,
          enabled: config.enabled,
          collaborator_member_type: config.collaborator_member_type || "openchat",
          collaborator_member_id: config.collaborator_member_id || "",
          collaborator_perm: config.collaborator_perm || "edit",
        });
      })
      .catch(() => message.error("飞书配置加载失败"))
      .finally(() => setIsLoadingFeishu(false));
  }, [feishuForm]);

  async function handleSaveFeishuConfig(values: FeishuConfigFormValues) {
    setIsSavingFeishu(true);
    try {
      await saveFeishuConfig(values);
      message.success("飞书配置已保存");
      feishuForm.setFieldValue("app_secret", "");
    } catch (error) {
      message.error(error instanceof Error ? error.message : "飞书配置保存失败");
    } finally {
      setIsSavingFeishu(false);
    }
  }

  async function handleCreateFeishuAnalysisBase() {
    setIsCreatingFeishuBase(true);
    try {
      const saved = await saveFeishuConfig({
        ...feishuForm.getFieldsValue(),
        enabled: true,
      });
      feishuForm.setFieldsValue({ ...saved, app_secret: "", enabled: true });
      const result = await createFeishuAnalysisBase({ base_name: "小红书内容分析总表", table_name: "小红书内容分析" });
      if (result.status === "success" && result.config) {
        feishuForm.setFieldsValue({
          app_id: result.config.app_id,
          app_secret: "",
          bitable_url: result.config.bitable_url,
          table_id: result.config.table_id,
          enabled: result.config.enabled,
          collaborator_member_type: result.config.collaborator_member_type || "openchat",
          collaborator_member_id: result.config.collaborator_member_id || "",
          collaborator_perm: result.config.collaborator_perm || "edit",
        });
        message.success(`飞书分析表已创建，已补齐 ${result.created_fields ?? 0} 个字段${result.grant_message || ""}`);
      } else {
        message.warning(result.message || "飞书分析表创建失败");
      }
    } catch (error) {
      message.error(error instanceof Error ? error.message : "飞书分析表创建失败");
    } finally {
      setIsCreatingFeishuBase(false);
    }
  }

  async function handleGrantFeishuPermission() {
    setIsGrantingFeishuPermission(true);
    try {
      const values = feishuForm.getFieldsValue();
      await saveFeishuConfig({ ...values, enabled: true });
      const result = await grantFeishuPermission({
        member_type: values.collaborator_member_type,
        member_id: values.collaborator_member_id,
        perm: values.collaborator_perm || "edit",
        notify_lark: false,
      });
      if (result.status === "success") {
        if (result.config) feishuForm.setFieldsValue({ ...result.config, app_secret: "" });
        message.success(result.message || "飞书分析表授权完成");
      } else {
        message.warning(result.message || "飞书分析表授权未完成");
      }
    } catch (error) {
      message.error(error instanceof Error ? error.message : "飞书分析表授权失败");
    } finally {
      setIsGrantingFeishuPermission(false);
    }
  }

  async function handleTestFeishuConnection() {
    setIsTestingFeishu(true);
    try {
      const result = await testFeishuConnection();
      if (result.status === "success") {
        message.success(result.message || "飞书连接成功");
      } else {
        message.warning(result.message || "飞书连接失败");
      }
    } catch (error) {
      message.error(error instanceof Error ? error.message : "飞书连接测试失败");
    } finally {
      setIsTestingFeishu(false);
    }
  }

  async function handleEnsureFeishuFields() {
    setIsEnsuringFields(true);
    try {
      const result = await ensureFeishuFields({ dry_run: false });
      if (result.status === "ok") {
        message.success(`自动补字段完成：新增 ${result.created_count ?? 0} 个，已存在 ${result.skipped_count ?? 0} 个`);
      } else {
        message.warning(result.message || "自动补字段未完成");
      }
    } catch (error) {
      message.error(error instanceof Error ? error.message : "自动补字段失败");
    } finally {
      setIsEnsuringFields(false);
    }
  }

  return (
    <div>
      <PageHeader
        eyebrow="Workspace"
        title="设置"
        description="用户空间、安全、文件存储和系统参数会集中在这里。"
      />

      <Row gutter={[16, 16]}>
        <Col xs={24} lg={12}>
          <Card
            title={<span><SafetyCertificateOutlined style={{ marginRight: 8 }} />安全边界</span>}
          >
            <Paragraph>
              所有资源将通过平台用户和平台账号双重归属校验。Cookie 与模型 Key 由后端统一加密存储。
            </Paragraph>
          </Card>
        </Col>

        <Col xs={24}>
          <Card title={<span><ApiOutlined style={{ marginRight: 8, color: "#1677ff" }} />飞书集成</span>}>
            <Alert
              type="info"
              showIcon
              style={{ marginBottom: 16 }}
              message="管理员只需配置一次飞书 App 和协作者。建议拉一个飞书运营群，填写群 ID 后授权，普通运营入群即可编辑分析表。"
            />
            <Form<FeishuConfigFormValues>
              form={feishuForm}
              layout="vertical"
              disabled={isLoadingFeishu}
              initialValues={{ app_id: "", app_secret: "", bitable_url: "", table_id: "", enabled: false, collaborator_member_type: "openchat", collaborator_member_id: "", collaborator_perm: "edit" }}
              onFinish={handleSaveFeishuConfig}
            >
              <Row gutter={16}>
                <Col xs={24} md={12}>
                  <Form.Item label="飞书 App ID" name="app_id">
                    <Input placeholder="cli_xxx" />
                  </Form.Item>
                </Col>
                <Col xs={24} md={12}>
                  <Form.Item label="飞书 App Secret" name="app_secret">
                    <Input.Password placeholder="留空表示不更新密钥" />
                  </Form.Item>
                </Col>
                <Col xs={24} md={16}>
                  <Form.Item label="飞书多维表格地址" name="bitable_url">
                    <Input placeholder="https://.../base/...?...table=..." />
                  </Form.Item>
                </Col>
                <Col xs={24} md={8}>
                  <Form.Item label="目标数据表" name="table_id">
                    <Input placeholder="可从多维表格地址自动识别" />
                  </Form.Item>
                </Col>
                <Col xs={24} md={8}>
                  <Form.Item label="协作者类型" name="collaborator_member_type">
                    <Select
                      options={[
                        { value: "openchat", label: "飞书群（推荐）" },
                        { value: "email", label: "个人邮箱" },
                        { value: "openid", label: "OpenID" },
                        { value: "userid", label: "UserID" },
                      ]}
                    />
                  </Form.Item>
                </Col>
                <Col xs={24} md={12}>
                  <Form.Item label="协作者 ID" name="collaborator_member_id" extra="飞书群请填 openchat/群 ID；个人授权可填飞书邮箱。">
                    <Input placeholder="oc_xxx 或 user@company.com" />
                  </Form.Item>
                </Col>
                <Col xs={24} md={4}>
                  <Form.Item label="协作者权限" name="collaborator_perm">
                    <Select options={[{ value: "edit", label: "可编辑" }, { value: "view", label: "可查看" }]} />
                  </Form.Item>
                </Col>
                <Col xs={24}>
                  <Form.Item label="启用状态" name="enabled" valuePropName="checked">
                    <Switch />
                  </Form.Item>
                </Col>
              </Row>
              <Space wrap>
                <Button type="primary" htmlType="submit" loading={isSavingFeishu}>保存飞书配置</Button>
                <Button onClick={handleCreateFeishuAnalysisBase} loading={isCreatingFeishuBase}>创建飞书分析表</Button>
                <Button onClick={handleGrantFeishuPermission} loading={isGrantingFeishuPermission}>授权协作者编辑表格</Button>
                <Button onClick={handleTestFeishuConnection} loading={isTestingFeishu}>测试连接</Button>
                <Button onClick={handleEnsureFeishuFields} loading={isEnsuringFields}>自动补字段</Button>
              </Space>
            </Form>
          </Card>
        </Col>
      </Row>
    </div>
  );
}
