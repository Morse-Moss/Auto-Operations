import {
  DeleteOutlined,
  EditOutlined,
  PlayCircleOutlined,
  PlusOutlined,
  ReloadOutlined,
  SaveOutlined,
} from "@ant-design/icons";
import {
  Alert,
  Button,
  Card,
  Col,
  Collapse,
  Empty,
  Form,
  Input,
  List,
  Row,
  Select,
  Space,
  Spin,
  Statistic,
  Table,
  Tag,
  Typography,
} from "antd";
import type { ColumnsType } from "antd/es/table";
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import { PageHeader } from "../../../components/layout/app-shell";
import {
  createHuitunKeywordDiscoveryRun,
  createKeywordGroup,
  deleteKeywordGroup,
  fetchAccounts,
  fetchHuitunKeywordDiscoveryRuns,
  fetchKeywordGroup,
  fetchKeywordGroups,
  importKeywordCandidates,
  importKeywordCandidatesToGroup,
  updateKeywordGroup,
} from "../../../lib/api";
import type { KeywordDiscoveryItem, KeywordDiscoveryRun, KeywordGroup, KeywordGroupDetail, PlatformAccount } from "../../../types";

const { Text } = Typography;

function splitKeywords(value: string): string[] {
  return value
    .split(/[,，\n]/)
    .map((keyword) => keyword.trim())
    .filter(Boolean);
}

function splitSeedKeywords(value: string): string[] {
  return value
    .split(/[\r\n,，]+/)
    .map((seed) => seed.trim())
    .filter(Boolean);
}

function joinKeywords(keywords: string[]): string {
  return keywords.join("，");
}

function parseHuitunTableRows(value: string): string[][] {
  return value
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line) => line.split(/\t|,|，/).map((cell) => cell.trim()))
    .filter((cells) => cells.length >= 2);
}

function categoryText(item: KeywordDiscoveryItem): string {
  return item.categories
    .map((category) => category.rate ? `${category.label} ${category.rate}%` : category.label)
    .filter(Boolean)
    .join("；");
}

function failedSeedText(run: KeywordDiscoveryRun): string {
  return (run.seed_results ?? [])
    .filter((result) => result.status === "failed")
    .map((result) => `${result.source_keyword}${result.error_message ? `：${result.error_message}` : ""}`)
    .join("；");
}

export function XhsKeywordsPage() {
  const navigate = useNavigate();
  const [groups, setGroups] = useState<KeywordGroup[]>([]);
  const [detailsByGroup, setDetailsByGroup] = useState<
    Record<number, KeywordGroupDetail>
  >({});
  const [name, setName] = useState("");
  const [keywords, setKeywords] = useState("");
  const [editingGroupId, setEditingGroupId] = useState<number | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isWorking, setIsWorking] = useState(false);
  const [huitunAccounts, setHuitunAccounts] = useState<PlatformAccount[]>([]);
  const [selectedHuitunAccountId, setSelectedHuitunAccountId] = useState<number | null>(null);
  const [huitunSeed, setHuitunSeed] = useState("");
  const [huitunRows, setHuitunRows] = useState("");
  const [huitunRun, setHuitunRun] = useState<KeywordDiscoveryRun | null>(null);
  const [huitunRuns, setHuitunRuns] = useState<KeywordDiscoveryRun[]>([]);
  const [selectedCandidateIds, setSelectedCandidateIds] = useState<number[]>([]);
  const [targetGroupId, setTargetGroupId] = useState<number | "create">("create");
  const [targetGroupName, setTargetGroupName] = useState("");
  const [isHuitunWorking, setIsHuitunWorking] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function loadGroups() {
    setIsLoading(true);
    setError(null);
    try {
      const [result, accounts, discoveryRuns] = await Promise.all([
        fetchKeywordGroups("xhs"),
        fetchAccounts("huitun"),
        fetchHuitunKeywordDiscoveryRuns(1, 5),
      ]);
      setGroups(result.items);
      setHuitunAccounts(accounts);
      setHuitunRuns(discoveryRuns.items);
      setSelectedHuitunAccountId((currentId) => currentId ?? accounts[0]?.id ?? null);
      const details = await Promise.all(
        result.items.map(async (group) => {
          try {
            return [group.id, await fetchKeywordGroup(group.id)] as const;
          } catch {
            return [group.id, undefined] as const;
          }
        })
      );
      setDetailsByGroup(
        Object.fromEntries(
          details.filter(
            (entry): entry is readonly [number, KeywordGroupDetail] =>
              Boolean(entry[1])
          )
        )
      );
    } catch {
      setError("关键词组加载失败。");
    } finally {
      setIsLoading(false);
    }
  }

  useEffect(() => {
    void loadGroups();
  }, []);

  function resetForm() {
    setEditingGroupId(null);
    setName("");
    setKeywords("");
  }

  function editGroup(group: KeywordGroup) {
    setEditingGroupId(group.id);
    setName(group.name);
    setKeywords(joinKeywords(group.keywords));
  }

  async function saveGroup() {
    const nextKeywords = splitKeywords(keywords);
    if (!name.trim() || nextKeywords.length === 0) {
      setMessage("请填写名称和至少一个关键词。");
      return;
    }
    setIsWorking(true);
    setMessage(null);
    try {
      if (editingGroupId) {
        const updated = await updateKeywordGroup(editingGroupId, {
          name: name.trim(),
          keywords: nextKeywords,
        });
        setGroups((currentGroups) =>
          currentGroups.map((group) =>
            group.id === updated.id ? updated : group
          )
        );
        const detail = await fetchKeywordGroup(updated.id);
        setDetailsByGroup((currentDetails) => ({
          ...currentDetails,
          [updated.id]: detail,
        }));
        setMessage("关键词组已更新。");
      } else {
        const created = await createKeywordGroup({
          platform: "xhs",
          name: name.trim(),
          keywords: nextKeywords,
        });
        setGroups((currentGroups) => [created, ...currentGroups]);
        const detail = await fetchKeywordGroup(created.id);
        setDetailsByGroup((currentDetails) => ({
          ...currentDetails,
          [created.id]: detail,
        }));
        setMessage("关键词组已创建。");
      }
      resetForm();
    } catch {
      setMessage("关键词组保存失败。");
    } finally {
      setIsWorking(false);
    }
  }

  async function removeGroup(groupId: number) {
    setIsWorking(true);
    setMessage(null);
    try {
      await deleteKeywordGroup(groupId);
      setGroups((currentGroups) =>
        currentGroups.filter((group) => group.id !== groupId)
      );
      setDetailsByGroup((currentDetails) => {
        const nextDetails = { ...currentDetails };
        delete nextDetails[groupId];
        return nextDetails;
      });
      if (editingGroupId === groupId) {
        resetForm();
      }
      setMessage("关键词组已删除。");
    } catch {
      setMessage("关键词组删除失败。");
    } finally {
      setIsWorking(false);
    }
  }

  async function fetchHuitunHotwordsFromAccount() {
    const seeds = splitSeedKeywords(huitunSeed);
    if (!seeds.length) {
      setMessage("请输入至少一个种子关键词。");
      return;
    }
    if (!selectedHuitunAccountId) {
      setMessage("请先到账号矩阵绑定灰豚账号。");
      return;
    }
    setIsHuitunWorking(true);
    setMessage(null);
    setError(null);
    try {
      const run = await createHuitunKeywordDiscoveryRun({
        source_mode: "live_account",
        account_id: selectedHuitunAccountId,
        limit_per_seed: 50,
        inputs: seeds.map((source_keyword) => ({ source_keyword })),
      });
      setHuitunRun(run);
      setHuitunRuns((currentRuns) => [run, ...currentRuns.filter((item) => item.id !== run.id)].slice(0, 5));
      setSelectedCandidateIds(run.items.map((item) => item.id));
      setTargetGroupName(seeds.length === 1 ? `${seeds[0]} 热词` : "灰豚批量热词");
      const failedSeeds = (run.seed_results ?? []).filter((result) => result.status === "failed");
      if (run.items.length && failedSeeds.length) {
        setMessage(`已获取 ${run.items.length} 个候选词，${failedSeeds.length} 个种子词失败，成功结果仍可导入。`);
      } else {
        setMessage(run.items.length ? "已获取灰豚候选词，请选择要导入的关键词。" : "没有获取到候选词，可展开手工导入灰豚热词临时处理。");
      }
    } catch {
      setMessage("灰豚候选词获取失败，请检查账号登录态，或使用手工导入灰豚热词。");
    } finally {
      setIsHuitunWorking(false);
    }
  }

  async function parseHuitunHotwords() {
    const seed = huitunSeed.trim();
    const tableRows = parseHuitunTableRows(huitunRows);
    if (!seed || tableRows.length === 0) {
      setMessage("请粘贴灰豚热词表格或 JSON 导出。");
      return;
    }
    setIsHuitunWorking(true);
    setMessage(null);
    setError(null);
    try {
      const run = await createHuitunKeywordDiscoveryRun({
        source_mode: "manual_table",
        limit_per_seed: 50,
        inputs: [{ source_keyword: seed, table_rows: tableRows }],
      });
      setHuitunRun(run);
      setSelectedCandidateIds(run.items.map((item) => item.id));
      setTargetGroupName(seed ? `${seed} 热词` : "灰豚热词");
      setMessage(run.items.length ? "灰豚热词已解析，请选择要导入的候选词。" : "没有解析到候选词，请粘贴灰豚热词表格或 JSON 导出。");
    } catch {
      setMessage("解析失败。请粘贴灰豚热词表格或 JSON 导出。");
    } finally {
      setIsHuitunWorking(false);
    }
  }

  async function importSelectedCandidates() {
    if (!selectedCandidateIds.length) {
      setMessage("请先选择要导入的灰豚热词候选词。");
      return;
    }
    if (targetGroupId === "create" && !targetGroupName.trim()) {
      setMessage("请填写新关键词组名称，或选择已有关键词组。");
      return;
    }
    setIsHuitunWorking(true);
    setMessage(null);
    try {
      const payload = {
        candidate_ids: selectedCandidateIds,
        merge_mode: "append_dedupe" as const,
        ...(targetGroupId === "create"
          ? { target: { mode: "create" as const, name: targetGroupName.trim(), platform: "xhs" as const } }
          : {}),
      };
      const result = targetGroupId === "create"
        ? await importKeywordCandidates(payload)
        : await importKeywordCandidatesToGroup(targetGroupId, payload);
      await loadGroups();
      setHuitunRun((currentRun) => currentRun ? {
        ...currentRun,
        items: currentRun.items.map((item) => selectedCandidateIds.includes(item.id) ? { ...item, selected: true, imported_group_id: result.group.id } : item),
      } : currentRun);
      setSelectedCandidateIds([]);
      setTargetGroupId(result.group.id);
      setMessage(`已导入 ${result.imported_keywords.length} 个关键词到「${result.group.name}」。`);
    } catch {
      setMessage("导入失败，请重新选择候选词后再试。");
    } finally {
      setIsHuitunWorking(false);
    }
  }

  const candidateColumns: ColumnsType<KeywordDiscoveryItem> = [
    { title: "关键词", dataIndex: "keyword", width: 140, render: (value: string) => <Text strong>{value}</Text> },
    { title: "热度", dataIndex: "hot_value_text", width: 110, render: (value: string | null, item) => value || item.hot_value_number || "-" },
    { title: "笔记数", dataIndex: "note_count", width: 100, render: (value: number | null) => value ?? "-" },
    { title: "互动", dataIndex: "interaction_text", width: 110, render: (value: string | null, item) => value || item.interaction_number || "-" },
    { title: "分类", key: "categories", ellipsis: true, render: (_, item) => categoryText(item) || "-" },
    { title: "来源", dataIndex: "source_keyword", width: 100 },
    { title: "排名", dataIndex: "rank_index", width: 80 },
  ];

  return (
    <div>
      <PageHeader
        eyebrow="XHS Keywords"
        title="关键词组"
        description="维护选题、赛道和品牌关键词组，从已保存笔记中观察命中量和互动机会。"
        action={
          <Button
            icon={<ReloadOutlined />}
            disabled={isLoading}
            onClick={loadGroups}
          >
            刷新
          </Button>
        }
      />

      <Card
        title="灰豚候选词"
        extra={<Tag color="gold">账号登录后自动获取</Tag>}
        style={{ background: "#1f1f1f", borderColor: "#303030", marginBottom: 24 }}
      >
        <Alert
          type="info"
          showIcon
          message="输入多个种子关键词，系统会用已绑定的灰豚账号低频逐个获取候选词；单个种子失败不会隐藏其他成功结果。"
          style={{ marginBottom: 16 }}
        />
        <Row gutter={16}>
          <Col xs={24} md={8}>
            <Form.Item label="灰豚账号">
              <Select
                value={selectedHuitunAccountId ?? undefined}
                onChange={setSelectedHuitunAccountId}
                placeholder="请选择灰豚账号"
                options={huitunAccounts.map((account) => ({ value: account.id, label: account.nickname || account.external_user_id || `灰豚账号 ${account.id}` }))}
              />
            </Form.Item>
          </Col>
          <Col xs={24} md={10}>
            <Form.Item label="种子关键词">
              <Input.TextArea
                value={huitunSeed}
                onChange={(e) => setHuitunSeed(e.target.value)}
                placeholder="例如：低卡早餐、通勤穿搭\n敏感肌护肤"
                autoSize={{ minRows: 2, maxRows: 4 }}
              />
            </Form.Item>
          </Col>
          <Col xs={24} md={6}>
            <Form.Item label=" ">
              <Button type="primary" block onClick={() => void fetchHuitunHotwordsFromAccount()} loading={isHuitunWorking}>
                获取灰豚候选词
              </Button>
            </Form.Item>
          </Col>
        </Row>

        <Collapse
          ghost
          items={[
            {
              key: "manual",
              label: "手工导入灰豚热词",
              children: (
                <>
                  <Alert
                    type="warning"
                    showIcon
                    message="自动获取失败时，把灰豚热词表格复制到这里作为临时兜底。"
                    style={{ marginBottom: 16 }}
                  />
                  <Form.Item label="灰豚热词表格">
                    <Input.TextArea
                      value={huitunRows}
                      onChange={(e) => setHuitunRows(e.target.value)}
                      placeholder="每行一个热词，按灰豚表格复制：关键词、热度、笔记数、互动、分类"
                      autoSize={{ minRows: 3, maxRows: 6 }}
                    />
                  </Form.Item>
                  <Button onClick={() => void parseHuitunHotwords()} loading={isHuitunWorking}>
                    解析灰豚热词
                  </Button>
                </>
              ),
            },
          ]}
          style={{ marginBottom: huitunRun?.items.length ? 16 : 0 }}
        />

        {huitunRun?.seed_results?.length ? (
          <div style={{ marginBottom: 16 }}>
            <Space wrap>
              {huitunRun.seed_results.map((result) => (
                <Tag key={result.source_keyword} color={result.status === "failed" ? "red" : "green"}>
                  {result.source_keyword} · {result.status === "failed" ? "种子失败" : `${result.item_count} 个候选词`}
                </Tag>
              ))}
              {huitunRun.status === "partial_failed" && <Tag color="orange">partial_failed</Tag>}
            </Space>
            {failedSeedText(huitunRun) && (
              <Alert
                type="warning"
                showIcon
                style={{ marginTop: 8 }}
                message={`失败种子：${failedSeedText(huitunRun)}`}
              />
            )}
          </div>
        ) : null}

        {huitunRun?.items.length ? (
          <Space wrap style={{ marginBottom: 16 }}>
            <Select
              value={targetGroupId}
              onChange={setTargetGroupId}
              style={{ width: 220 }}
              options={[
                { value: "create", label: "创建新关键词组" },
                ...groups.map((group) => ({ value: group.id, label: group.name })),
              ]}
            />
            {targetGroupId === "create" && (
              <Input
                value={targetGroupName}
                onChange={(e) => setTargetGroupName(e.target.value)}
                placeholder="新关键词组名称"
                style={{ width: 220 }}
              />
            )}
            <Button onClick={() => void importSelectedCandidates()} disabled={!selectedCandidateIds.length} loading={isHuitunWorking}>
              导入选中候选词
            </Button>
            <Text type="secondary">已选 {selectedCandidateIds.length} / {huitunRun.items.length}</Text>
          </Space>
        ) : null}
        {huitunRun?.items.length ? (
          <Table<KeywordDiscoveryItem>
            rowKey="id"
            size="small"
            columns={candidateColumns}
            dataSource={huitunRun.items}
            pagination={{ pageSize: 8 }}
            rowSelection={{ selectedRowKeys: selectedCandidateIds, onChange: (keys) => setSelectedCandidateIds(keys.map(Number)) }}
          />
        ) : null}

        {huitunRuns.length ? (
          <div style={{ marginTop: 16 }}>
            <Text type="secondary" style={{ display: "block", marginBottom: 8 }}>最近灰豚发现记录</Text>
            <List
              size="small"
              dataSource={huitunRuns}
              renderItem={(run) => (
                <List.Item onClick={() => setHuitunRun(run)} style={{ cursor: "pointer" }}>
                  <Space wrap>
                    <Text>{run.seed_keywords.join("，") || `发现记录 #${run.id}`}</Text>
                    <Tag color={run.status === "partial_failed" ? "orange" : run.status === "failed" ? "red" : "green"}>{run.status}</Tag>
                    <Text type="secondary">成功 {run.summary?.success_seed_count ?? 0} / 失败 {run.summary?.failed_seed_count ?? 0} / 候选 {run.summary?.total_item_count ?? 0}</Text>
                    {failedSeedText(run) && <Text type="danger">失败种子：{failedSeedText(run)}</Text>}
                  </Space>
                </List.Item>
              )}
            />
          </div>
        ) : null}
      </Card>

      <Card
        style={{ background: "#1f1f1f", borderColor: "#303030", marginBottom: 24 }}
      >
        <Form layout="inline" style={{ flexWrap: "wrap", gap: 8 }}>
          <Form.Item>
            <Input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="关键词组名称"
              disabled={isLoading}
              style={{ width: 200 }}
            />
          </Form.Item>
          <Form.Item>
            <Input.TextArea
              value={keywords}
              onChange={(e) => setKeywords(e.target.value)}
              placeholder="关键词，用逗号或换行分隔"
              disabled={isLoading}
              autoSize={{ minRows: 1, maxRows: 3 }}
              style={{ width: 320 }}
            />
          </Form.Item>
          <Form.Item>
            <Button
              type="primary"
              icon={editingGroupId ? <SaveOutlined /> : <PlusOutlined />}
              disabled={isWorking}
              onClick={() => void saveGroup()}
            >
              {editingGroupId ? "保存修改" : "创建组"}
            </Button>
          </Form.Item>
          {editingGroupId && (
            <Form.Item>
              <Button disabled={isWorking} onClick={resetForm}>
                取消
              </Button>
            </Form.Item>
          )}
        </Form>
      </Card>

      {message && (
        <Alert
          type="info"
          message={message}
          showIcon
          closable
          style={{ marginBottom: 16 }}
        />
      )}
      {error && (
        <Alert
          type="error"
          message={error}
          showIcon
          closable
          style={{ marginBottom: 16 }}
        />
      )}

      {isLoading ? (
        <div style={{ textAlign: "center", padding: 48 }}>
          <Spin tip="正在加载关键词组..." />
        </div>
      ) : groups.length === 0 ? (
        <Card style={{ background: "#1f1f1f", borderColor: "#303030" }}>
          <Empty description="暂无关键词组。" />
        </Card>
      ) : (
        <Row gutter={[16, 16]}>
          {groups.map((group) => {
            const detail = detailsByGroup[group.id];
            return (
              <Col xs={24} md={12} key={group.id}>
                <Card
                  title={
                    <Space>
                      <Text strong>{group.name}</Text>
                      <Tag color="blue">xhs</Tag>
                    </Space>
                  }
                  style={{ background: "#1f1f1f", borderColor: "#303030" }}
                >
                  <Text type="secondary" style={{ display: "block", marginBottom: 12 }}>
                    {joinKeywords(group.keywords)}
                  </Text>

                  <Row gutter={16} style={{ marginBottom: 16 }}>
                    <Col span={8}>
                      <Statistic
                        title="命中"
                        value={detail?.trend.total_matches ?? 0}
                        suffix="条"
                        valueStyle={{ fontSize: 16 }}
                      />
                    </Col>
                    <Col span={8}>
                      <Statistic
                        title="互动"
                        value={detail?.trend.total_engagement ?? 0}
                        valueStyle={{ fontSize: 16 }}
                      />
                    </Col>
                    <Col span={8}>
                      <Statistic
                        title="关键词"
                        value={group.keywords.length}
                        suffix="个"
                        valueStyle={{ fontSize: 16 }}
                      />
                    </Col>
                  </Row>

                  {detail?.trend.keywords.length ? (
                    <div
                      style={{
                        display: "flex",
                        flexWrap: "wrap",
                        gap: 8,
                        marginBottom: 16,
                      }}
                    >
                      {detail.trend.keywords.map((kw) => (
                        <Tag key={kw.keyword}>
                          {kw.keyword} · {kw.notes} 条
                        </Tag>
                      ))}
                    </div>
                  ) : null}

                  {detail?.trend.matched_notes.length ? (
                    <List
                      size="small"
                      dataSource={detail.trend.matched_notes.slice(0, 3)}
                      style={{ marginBottom: 16 }}
                      renderItem={(note) => (
                        <List.Item>
                          <List.Item.Meta
                            title={note.title || note.note_id}
                            description={`${note.author_name || "未知作者"} · 互动 ${note.engagement}`}
                          />
                        </List.Item>
                      )}
                    />
                  ) : null}

                  <Space>
                    <Button
                      type="primary"
                      icon={<PlayCircleOutlined />}
                      disabled={isWorking}
                      onClick={() => navigate(`/platforms/xhs/crawler?keyword_group_id=${group.id}`)}
                    >
                      开始采集
                    </Button>
                    <Button
                      icon={<EditOutlined />}
                      disabled={isWorking}
                      onClick={() => editGroup(group)}
                    >
                      编辑
                    </Button>
                    <Button
                      icon={<DeleteOutlined />}
                      danger
                      disabled={isWorking}
                      onClick={() => removeGroup(group.id)}
                    >
                      删除
                    </Button>
                  </Space>
                </Card>
              </Col>
            );
          })}
        </Row>
      )}
    </div>
  );
}
