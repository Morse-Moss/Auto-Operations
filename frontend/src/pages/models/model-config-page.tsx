import {
  ApiOutlined,
  DeleteOutlined,
  EditOutlined,
  FileImageOutlined,
  KeyOutlined,
  PlusOutlined,
  ReloadOutlined,
  RobotOutlined,
} from "@ant-design/icons";
import {
  Alert,
  Button,
  Card,
  Col,
  Empty,
  Form,
  Input,
  Popconfirm,
  Row,
  Segmented,
  Select,
  Space,
  Spin,
  Tag,
  Typography,
} from "antd";
import type { FormEvent } from "react";
import { useEffect, useMemo, useState } from "react";

import { PageHeader } from "../../components/layout/app-shell";
import {
  configureDoubaoMainModels,
  createModelConfig,
  deleteModelConfig,
  fetchModelCapabilityDefaults,
  fetchModelConfigs,
  apiErrorMessage,
  getUsageLimitError,
  setModelCapabilityDefault,
  testModelConfig,
  updateModelConfig,
} from "../../lib/api";
import { useUsageBalance } from "../../hooks/use-usage-balance";
import type { ModelCapability, ModelCapabilityDefault, ModelConfig, ModelConfigPayload, ModelType } from "../../types";

const { Text } = Typography;
const DOUBAO_MAIN_MODEL = "doubao-seed-2-0-mini-260428";
const VOLCENGINE_ARK_BASE_URL = "https://ark.cn-beijing.volces.com/api/v3";

const emptyForm: ModelConfigPayload = {
  name: "",
  model_type: "text",
  provider: "volcengine-ark",
  model_name: DOUBAO_MAIN_MODEL,
  base_url: VOLCENGINE_ARK_BASE_URL,
  api_key: "",
  is_default: false,
};

const capabilityOrder: ModelCapability[] = ["text", "vision", "image_generation"];
const capabilityMeta: Record<ModelCapability, { label: string; description: string }> = {
  text: { label: "文本生成", description: "改写、草稿与分析文本" },
  vision: { label: "图片理解", description: "图片描述与内容理解" },
  image_generation: { label: "图片生成", description: "文生图与参考图生图" },
};

function defaultModelName(type: ModelType): string {
  return DOUBAO_MAIN_MODEL;
}

function defaultProvider(type: ModelType): string {
  return "volcengine-ark";
}

function defaultBaseUrl(type: ModelType): string {
  return VOLCENGINE_ARK_BASE_URL;
}

function defaultFormForType(type: ModelType): ModelConfigPayload {
  return {
    ...emptyForm,
    model_type: type,
    provider: defaultProvider(type),
    model_name: defaultModelName(type),
    base_url: defaultBaseUrl(type),
  };
}

function typeLabel(type: ModelType): string {
  return type === "text" ? "文本模型" : "图片模型";
}

function ModelTypeIcon({ type }: { type: ModelType }) {
  return type === "text" ? <RobotOutlined /> : <FileImageOutlined />;
}

const cardStyle = { background: "#1f1f1f", borderColor: "#303030" };

export function ModelConfigPage() {
  const [configs, setConfigs] = useState<ModelConfig[]>([]);
  const [form, setForm] = useState<ModelConfigPayload>(emptyForm);
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [capabilityDefaults, setCapabilityDefaults] = useState<ModelCapabilityDefault[]>([]);
  const [capabilitySelections, setCapabilitySelections] = useState<Partial<Record<ModelCapability, number>>>({});
  const [savingCapability, setSavingCapability] = useState<ModelCapability | null>(null);
  const [testingKey, setTestingKey] = useState<string | null>(null);
  const [testResults, setTestResults] = useState<Record<string, { status: string; message: string }>>({});
  const [doubaoApiKey, setDoubaoApiKey] = useState("");
  const [isConfiguringDoubao, setIsConfiguringDoubao] = useState(false);
  const usage = useUsageBalance();

  const grouped = useMemo(
    () => ({
      text: configs.filter((config) => config.model_type === "text"),
      image: configs.filter((config) => config.model_type === "image"),
    }),
    [configs]
  );

  async function loadConfigs() {
    setIsLoading(true);
    setError(null);
    try {
      const [configResult, defaultResult] = await Promise.all([
        fetchModelConfigs(),
        fetchModelCapabilityDefaults(),
      ]);
      setConfigs(configResult.items);
      setCapabilityDefaults(defaultResult.items);
      setCapabilitySelections(
        Object.fromEntries(
          defaultResult.items
            .filter((item) => item.model_config)
            .map((item) => [item.capability, item.model_config?.id])
        ) as Partial<Record<ModelCapability, number>>
      );
    } catch {
      setError("模型配置加载失败。");
    } finally {
      setIsLoading(false);
    }
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!form.name.trim() || !form.model_name.trim()) {
      setError("请填写配置名称和模型名称。");
      return;
    }

    setIsSaving(true);
    setMessage(null);
    setError(null);
    const payload = {
      ...form,
      name: form.name.trim(),
      model_name: form.model_name.trim(),
      provider: form.provider.trim(),
      base_url: form.base_url.trim(),
      api_key: form.api_key.trim(),
    };
    try {
      if (editingId) {
        const updated = await updateModelConfig(editingId, payload);
        setConfigs((current) => current.map((config) => config.id === updated.id ? updated : config));
        setMessage(`${typeLabel(updated.model_type)}配置已更新。`);
        setEditingId(null);
      } else {
        const created = await createModelConfig(payload);
        setConfigs((current) => [created, ...current]);
        setMessage(`${typeLabel(created.model_type)}配置已保存。`);
      }
      setForm(defaultFormForType(form.model_type));
    } catch {
      setError("模型配置保存失败。");
    } finally {
      setIsSaving(false);
    }
  }

  function handleEdit(config: ModelConfig) {
    setEditingId(config.id);
    setForm({
      name: config.name,
      model_type: config.model_type,
      provider: config.provider,
      model_name: config.model_name,
      base_url: config.base_url,
      api_key: "",
      is_default: false,
    });
    setMessage(null);
    setError(null);
  }

  function handleCancelEdit() {
    setEditingId(null);
    setForm(defaultFormForType(form.model_type));
  }

  async function handleDelete(configId: number) {
    setError(null);
    setMessage(null);
    try {
      await deleteModelConfig(configId);
      setConfigs((current) => current.filter((c) => c.id !== configId));
      if (editingId === configId) {
        setEditingId(null);
        setForm(defaultFormForType(form.model_type));
      }
      setMessage("配置已删除。");
    } catch (err) {
      setError(apiErrorMessage(err, "配置删除失败。"));
    }
  }

  async function handleTest(configId: number, capability: ModelCapability) {
    const resultKey = `${configId}:${capability}`;
    setTestingKey(resultKey);
    try {
      const result = await testModelConfig(configId, capability);
      setTestResults((prev) => ({ ...prev, [resultKey]: { status: result.status, message: result.message } }));
    } catch (err) {
      const limitError = getUsageLimitError(err);
      setTestResults((prev) => ({ ...prev, [resultKey]: { status: "error", message: limitError?.message || apiErrorMessage(err, "检查请求失败") } }));
    } finally {
      setTestingKey(null);
    }
  }

  async function handleSetCapabilityDefault(capability: ModelCapability) {
    const modelConfigId = capabilitySelections[capability];
    if (!modelConfigId) {
      setError(`请先为${capabilityMeta[capability].label}选择模型。`);
      return;
    }
    setSavingCapability(capability);
    setError(null);
    setMessage(null);
    try {
      const updated = await setModelCapabilityDefault(capability, modelConfigId);
      setCapabilityDefaults((current) => current.map((item) => item.capability === capability ? updated : item));
      setConfigs((current) =>
        current.map((config) => ({
          ...config,
          assigned_capabilities: config.id === modelConfigId
            ? Array.from(new Set([...config.assigned_capabilities.filter((item) => item !== capability), capability]))
            : config.assigned_capabilities.filter((item) => item !== capability),
        }))
      );
      setMessage(`${capabilityMeta[capability].label}已切换为 ${updated.model_config?.name || "所选模型"}。`);
    } catch (err) {
      setError(apiErrorMessage(err, `${capabilityMeta[capability].label}路由保存失败。`));
    } finally {
      setSavingCapability(null);
    }
  }

  async function handleConfigureDoubaoMain() {
    const apiKey = doubaoApiKey.trim();
    if (!apiKey) {
      setError("请填写方舟 API Key。");
      return;
    }
    setIsConfiguringDoubao(true);
    setMessage(null);
    setError(null);
    try {
      const result = await configureDoubaoMainModels(apiKey);
      await loadConfigs();
      setDoubaoApiKey("");
      setMessage(`豆包主力模型已更新：${result.text.name}、${result.vision.name}。`);
    } catch (err) {
      setError(apiErrorMessage(err, "豆包主力模型配置失败。"));
    } finally {
      setIsConfiguringDoubao(false);
    }
  }

  useEffect(() => {
    void loadConfigs();
  }, []);

  return (
    <div>
      <PageHeader
        eyebrow="Model Routing"
        title="模型配置"
        description="为改写、生成、封面和图片处理配置用户级文本与图片模型，后续 AI 任务会从默认配置解析调用参数。"
        action={
          <Button
            icon={<ReloadOutlined />}
            onClick={loadConfigs}
            loading={isLoading}
          >
            刷新
          </Button>
        }
      />

      <Alert
        type="info"
        showIcon
        style={{ marginBottom: 16 }}
        message="模型配置建议"
        description={<>
          主力模型使用火山方舟：Provider <Typography.Text code>volcengine-ark</Typography.Text>，Base URL <Typography.Text code>{VOLCENGINE_ARK_BASE_URL}</Typography.Text>，模型名称 <Typography.Text code>{DOUBAO_MAIN_MODEL}</Typography.Text>。<br />
          同一个 Doubao 配置可以分别保存为文本模型和图片分析模型；图片生成仍需单独使用支持生成的服务。<br />
          模型连接测试会按积分计费；余额不足时不会请求模型服务。图片生成连接测试会真实调用上游，可能消耗上游额度。
        </>}
      />

      {usage.error ? (
        <Alert type="warning" showIcon style={{ marginBottom: 16 }} message={usage.error} />
      ) : null}

      {error && (
        <Alert
          type="error"
          message={error}
          showIcon
          closable
          style={{ marginBottom: 16 }}
        />
      )}
      {message && (
        <Alert
          type="success"
          message={message}
          showIcon
          closable
          style={{ marginBottom: 16 }}
        />
      )}

      <Card
        title="能力路由"
        extra={<Text type="secondary">管理员统一指定，全系统立即使用</Text>}
        style={{ ...cardStyle, marginBottom: 24 }}
      >
        <Row gutter={[16, 16]}>
          {capabilityOrder.map((capability) => {
            const route = capabilityDefaults.find((item) => item.capability === capability);
            const compatibleConfigs = configs.filter((config) => config.supported_capabilities.includes(capability));
            return (
              <Col xs={24} md={8} key={capability}>
                <Card
                  size="small"
                  style={{
                    height: "100%",
                    background: "#262626",
                    borderColor: route?.status === "configured" ? "#245b92" : "#5c3030",
                  }}
                >
                  <Space direction="vertical" size="small" style={{ width: "100%" }}>
                    <Space style={{ width: "100%", justifyContent: "space-between" }}>
                      <Text strong>{capabilityMeta[capability].label}</Text>
                      <Tag color={route?.status === "configured" ? "blue" : "error"}>
                        {route?.status === "configured" ? "已配置" : route?.status === "invalid" ? "配置失效" : "尚未配置"}
                      </Tag>
                    </Space>
                    <Text type="secondary" style={{ fontSize: 12 }}>
                      {capabilityMeta[capability].description}
                    </Text>
                    <Text style={{ minHeight: 22 }}>
                      {route?.model_config
                        ? `${route.model_config.name} · ${route.model_config.provider}`
                        : "选择模型后，相关 AI 任务才会启用"}
                    </Text>
                    <Select<number>
                      value={capabilitySelections[capability]}
                      onChange={(value) => setCapabilitySelections((current) => ({ ...current, [capability]: value }))}
                      options={compatibleConfigs.map((config) => ({
                        value: config.id,
                        label: `${config.name} · ${config.model_name}`,
                      }))}
                      placeholder={compatibleConfigs.length ? "选择默认模型" : "暂无兼容模型"}
                      disabled={compatibleConfigs.length === 0}
                      style={{ width: "100%" }}
                    />
                    <Button
                      type="primary"
                      block
                      loading={savingCapability === capability}
                      disabled={!capabilitySelections[capability]}
                      onClick={() => void handleSetCapabilityDefault(capability)}
                    >
                      保存路由
                    </Button>
                  </Space>
                </Card>
              </Col>
            );
          })}
        </Row>
      </Card>

      <Row gutter={[24, 24]}>
        <Col xs={24} lg={8}>
          <Card
            title={
              <Space>
                <RobotOutlined />
                <span>豆包主力模型</span>
              </Space>
            }
            style={{ ...cardStyle, marginBottom: 16 }}
          >
            <Space direction="vertical" style={{ width: "100%" }} size="middle">
              <Text type="secondary">
                一次保存方舟 API Key，同时创建或更新文本模型和图片分析模型，并设为默认。图片生成配置保持不变。
              </Text>
              <Input.Password
                value={doubaoApiKey}
                onChange={(event) => setDoubaoApiKey(event.target.value)}
                placeholder="ARK_API_KEY / 方舟 API Key"
              />
              <Button
                type="primary"
                icon={<KeyOutlined />}
                loading={isConfiguringDoubao}
                onClick={() => void handleConfigureDoubaoMain()}
                block
              >
                保存为主力模型
              </Button>
            </Space>
          </Card>

          <Card
            title={
              <Space>
                {editingId ? <EditOutlined /> : <PlusOutlined />}
                <span>{editingId ? "编辑模型" : "新增模型"}</span>
              </Space>
            }
            extra={editingId ? <Button size="small" onClick={handleCancelEdit}>取消编辑</Button> : undefined}
            style={cardStyle}
          >
            <Segmented
              value={form.model_type}
              options={[
                { label: "文本模型", value: "text" },
                { label: "图片模型", value: "image" },
              ]}
              onChange={(val) =>
                setForm((current) => {
                  const nextType = val as ModelType;
                  return {
                    ...current,
                    model_type: nextType,
                    provider: defaultProvider(nextType),
                    model_name: defaultModelName(nextType),
                    base_url: defaultBaseUrl(nextType),
                  };
                })
              }
              block
              style={{ marginBottom: 20 }}
            />

            <form onSubmit={handleSubmit}>
              <Form layout="vertical" component="div">
                <Form.Item label="配置名称">
                  <Input
                    value={form.name}
                    onChange={(e) =>
                      setForm((current) => ({
                        ...current,
                        name: e.target.value,
                      }))
                    }
                    placeholder="例如：默认文本模型"
                  />
                </Form.Item>
                <Form.Item label="Provider">
                  <Input
                    value={form.provider}
                    onChange={(e) =>
                      setForm((current) => ({
                        ...current,
                        provider: e.target.value,
                      }))
                    }
                    placeholder="volcengine-ark"
                  />
                  <Text type="secondary" style={{ fontSize: 12 }}>
                    方舟 Doubao 使用 volcengine-ark；其他 OpenAI 兼容服务可按实际 Provider 命名。
                  </Text>
                </Form.Item>
                <Form.Item label="模型名称">
                  <Input
                    value={form.model_name}
                    onChange={(e) =>
                      setForm((current) => ({
                        ...current,
                        model_name: e.target.value,
                      }))
                    }
                    placeholder={DOUBAO_MAIN_MODEL}
                  />
                </Form.Item>
                <Form.Item label="Base URL">
                  <Input
                    value={form.base_url}
                    onChange={(e) =>
                      setForm((current) => ({
                        ...current,
                        base_url: e.target.value,
                      }))
                    }
                    placeholder={VOLCENGINE_ARK_BASE_URL}
                  />
                </Form.Item>
                <Form.Item label="API Key">
                  <Input.Password
                    value={form.api_key}
                    onChange={(e) =>
                      setForm((current) => ({
                        ...current,
                        api_key: e.target.value,
                      }))
                    }
                    placeholder="保存后只显示是否已配置"
                  />
                </Form.Item>
                <Button
                  type="primary"
                  htmlType="submit"
                  icon={<KeyOutlined />}
                  loading={isSaving}
                  block
                >
                  {isSaving ? "保存中..." : editingId ? "更新配置" : "保存配置"}
                </Button>
              </Form>
            </form>
          </Card>
        </Col>

        <Col xs={24} lg={16}>
          <Row gutter={[16, 16]}>
            {(["text", "image"] as ModelType[]).map((type) => (
              <Col xs={24} md={12} key={type}>
                <Card
                  title={
                    <Space>
                      <ModelTypeIcon type={type} />
                      <span>{typeLabel(type)}</span>
                    </Space>
                  }
                  style={cardStyle}
                >
                  {isLoading ? (
                    <div style={{ textAlign: "center", padding: 24 }}>
                      <Spin tip="正在加载配置..." />
                    </div>
                  ) : grouped[type].length === 0 ? (
                    <Empty
                      image={
                        <ModelTypeIcon type={type} />
                      }
                      description={
                        <div>
                          <Text strong>暂无{typeLabel(type)}</Text>
                          <br />
                          <Text type="secondary">
                            保存一个配置后，AI 改写和生成流程就能读取默认模型。
                          </Text>
                        </div>
                      }
                    />
                  ) : (
                    <Space
                      direction="vertical"
                      style={{ width: "100%" }}
                      size="middle"
                    >
                      {grouped[type].map((config) => (
                        <Card
                          key={config.id}
                          size="small"
                          style={{
                            background: "#262626",
                            borderColor: "#303030",
                          }}
                        >
                          <Space
                            style={{
                              width: "100%",
                              justifyContent: "space-between",
                            }}
                          >
                            <Text strong>{config.name}</Text>
                            <Space size={4} wrap>
                              {config.assigned_capabilities.map((capability) => (
                                <Tag key={capability} color="blue">
                                  {capabilityMeta[capability].label}
                                </Tag>
                              ))}
                            </Space>
                          </Space>
                          <div style={{ marginTop: 4, marginBottom: 4 }}>
                            <Text>{config.model_name || "未填写模型名称"}</Text>
                          </div>
                          <div
                            style={{
                              marginTop: 8,
                              marginBottom: 8,
                            }}
                          >
                            <Text
                              type="secondary"
                              style={{ fontSize: 12, marginRight: 12 }}
                            >
                              {config.base_url || "未配置 Base URL"}
                            </Text>
                            <Text
                              type="secondary"
                              style={{ fontSize: 12 }}
                            >
                              {config.has_api_key
                                ? "已保存 API Key"
                                : "未保存 API Key"}
                            </Text>
                          </div>
                          <Space size={4} wrap>
                            {config.supported_capabilities.map((capability) => {
                              const resultKey = `${config.id}:${capability}`;
                              return (
                                <Button
                                  key={capability}
                                  size="small"
                                  icon={<ApiOutlined />}
                                  loading={testingKey === resultKey}
                                  onClick={() => void handleTest(config.id, capability)}
                                >
                                  测试{capabilityMeta[capability].label}
                                </Button>
                              );
                            })}
                            <Button
                              size="small"
                              icon={<EditOutlined />}
                              onClick={() => handleEdit(config)}
                            >
                              编辑
                            </Button>
                            <Popconfirm title="确定删除此模型配置？" onConfirm={() => void handleDelete(config.id)}>
                              <Button size="small" danger icon={<DeleteOutlined />}>删除</Button>
                            </Popconfirm>
                          </Space>
                          {config.supported_capabilities.map((capability) => {
                            const result = testResults[`${config.id}:${capability}`];
                            return result ? (
                              <div key={capability} style={{ marginTop: 6 }}>
                                <Tag color={result.status === "ok" ? "success" : "error"}>
                                  {capabilityMeta[capability].label} · {result.status === "ok" ? "连接正常" : "连接失败"}
                                </Tag>
                                <Text type="secondary" style={{ fontSize: 11 }}>{result.message}</Text>
                              </div>
                            ) : null;
                          })}
                        </Card>
                      ))}
                    </Space>
                  )}
                </Card>
              </Col>
            ))}
          </Row>
        </Col>
      </Row>
    </div>
  );
}
