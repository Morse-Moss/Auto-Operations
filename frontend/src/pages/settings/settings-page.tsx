import { useEffect, useState } from "react";
import { ApiOutlined, HeartOutlined, SafetyCertificateOutlined, WarningOutlined } from "@ant-design/icons";
import { Alert, Button, Card, Col, Form, Image, Input, message, Row, Space, Switch, Typography } from "antd";

import { PageHeader } from "../../components/layout/app-shell";
import { ensureFeishuFields, fetchFeishuConfig, saveFeishuConfig, testFeishuConnection } from "../../lib/api";
import type { FeishuIntegrationConfigPayload } from "../../types";

const { Paragraph, Text } = Typography;

type FeishuConfigFormValues = FeishuIntegrationConfigPayload;

export function SettingsPage() {
  const [feishuForm] = Form.useForm<FeishuConfigFormValues>();
  const [isLoadingFeishu, setIsLoadingFeishu] = useState(false);
  const [isSavingFeishu, setIsSavingFeishu] = useState(false);
  const [isEnsuringFields, setIsEnsuringFields] = useState(false);
  const [isTestingFeishu, setIsTestingFeishu] = useState(false);

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

        <Col xs={24} lg={12}>
          <Card
            title={<span><WarningOutlined style={{ marginRight: 8, color: "#faad14" }} />项目声明</span>}
          >
            <Alert
              type="warning"
              showIcon
              style={{ marginBottom: 12 }}
              message="Spider_XHS 为开源学习项目，仅供技术研究和个人学习使用"
            />
            <Paragraph>
              <ul style={{ paddingLeft: 20, margin: 0 }}>
                <li><Text strong>禁止任何形式的商业化使用</Text>，包括但不限于出售、转卖、收费服务</li>
                <li><Text strong>禁止用于任何违法违规活动</Text>，包括但不限于数据贩卖、恶意爬取、侵犯隐私</li>
                <li>使用者需自行承担因使用本项目产生的一切法律责任</li>
                <li>请遵守小红书平台的用户协议和相关法律法规</li>
              </ul>
            </Paragraph>
          </Card>
        </Col>

        <Col xs={24}>
          <Card title={<span><ApiOutlined style={{ marginRight: 8, color: "#1677ff" }} />飞书集成</span>}>
            <Alert
              type="info"
              showIcon
              style={{ marginBottom: 16 }}
              message="第一版先打通 dry-run 字段检查和本地同步状态；真实飞书写入需配置凭据后单独启用。"
            />
            <Form<FeishuConfigFormValues>
              form={feishuForm}
              layout="vertical"
              disabled={isLoadingFeishu}
              initialValues={{ app_id: "", app_secret: "", bitable_url: "", table_id: "", enabled: false }}
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
                <Col xs={24}>
                  <Form.Item label="启用状态" name="enabled" valuePropName="checked">
                    <Switch />
                  </Form.Item>
                </Col>
              </Row>
              <Space wrap>
                <Button type="primary" htmlType="submit" loading={isSavingFeishu}>保存飞书配置</Button>
                <Button onClick={handleTestFeishuConnection} loading={isTestingFeishu}>测试连接</Button>
                <Button onClick={handleEnsureFeishuFields} loading={isEnsuringFields}>自动补字段</Button>
              </Space>
            </Form>
          </Card>
        </Col>

        <Col xs={24}>
          <Card
            title={<span><HeartOutlined style={{ marginRight: 8, color: "#ff4d4f" }} />为爱发电</span>}
          >
            <Paragraph>
              本项目完全开源免费，如果对你有帮助，欢迎请作者喝杯咖啡 :)
            </Paragraph>
            <Row gutter={24} justify="center">
              <Col>
                <div style={{ textAlign: "center" }}>
                  <Image
                    src="/api/files/media/wx_pay.png"
                    width={200}
                    fallback="data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iMjAwIiBoZWlnaHQ9IjIwMCIgeG1sbnM9Imh0dHA6Ly93d3cudzMub3JnLzIwMDAvc3ZnIj48cmVjdCB3aWR0aD0iMjAwIiBoZWlnaHQ9IjIwMCIgZmlsbD0iIzFmMWYxZiIvPjx0ZXh0IHg9IjUwJSIgeT0iNTAlIiBkb21pbmFudC1iYXNlbGluZT0ibWlkZGxlIiB0ZXh0LWFuY2hvcj0ibWlkZGxlIiBmaWxsPSIjOGM4YzhjIiBmb250LXNpemU9IjE0Ij7lvq7kv6HmlK/ku5g8L3RleHQ+PC9zdmc+"
                  />
                  <Text type="secondary" style={{ display: "block", marginTop: 8 }}>微信支付</Text>
                </div>
              </Col>
              <Col>
                <div style={{ textAlign: "center" }}>
                  <Image
                    src="/api/files/media/zfb_pay.jpg"
                    width={200}
                    fallback="data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iMjAwIiBoZWlnaHQ9IjIwMCIgeG1sbnM9Imh0dHA6Ly93d3cudzMub3JnLzIwMDAvc3ZnIj48cmVjdCB3aWR0aD0iMjAwIiBoZWlnaHQ9IjIwMCIgZmlsbD0iIzFmMWYxZiIvPjx0ZXh0IHg9IjUwJSIgeT0iNTAlIiBkb21pbmFudC1iYXNlbGluZT0ibWlkZGxlIiB0ZXh0LWFuY2hvcj0ibWlkZGxlIiBmaWxsPSIjOGM4YzhjIiBmb250LXNpemU9IjE0Ij7mlK/ku5jlrp3mlK/ku5g8L3RleHQ+PC9zdmc+"
                  />
                  <Text type="secondary" style={{ display: "block", marginTop: 8 }}>支付宝</Text>
                </div>
              </Col>
            </Row>
          </Card>
        </Col>
      </Row>
    </div>
  );
}
