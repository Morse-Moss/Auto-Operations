# XHS Crawler Keyword Channels Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the XHS data crawler page expose two clear keyword crawl channels: keyword group collection and manual keyword collection.

**Architecture:** This is a frontend-only UI/state refactor. The existing backend endpoints and stream clients remain unchanged: keyword group collection continues to call `crawlXhsKeywordGroupStream`, while manual keyword collection calls `crawlXhsDataStream` with `mode: "search"`.

**Tech Stack:** React 19, TypeScript strict mode, Vite, Ant Design 6, existing FastAPI-backed stream API clients.

---

## File Structure

**Modify:**

- `frontend/src/pages/platforms/xhs/crawler-page.tsx`
  - Add explicit crawl channel state.
  - Change keyword group detection from `Boolean(selectedKeywordGroupId)` to the selected channel.
  - Default normal page entry to manual keyword search.
  - Keep the existing note URL and comments modes as secondary/manual advanced paths.
  - Update form copy so users see two primary keyword channels first.

**Verify:**

- `frontend/package.json`
  - Use existing `build` script: `npm --prefix frontend run build`.

No backend files, database migrations, SDK files, or API type definitions should change.

Project rule: do not create git commits unless the user explicitly asks. This plan intentionally omits commit steps.

---

### Task 1: Add explicit crawler channel state

**Files:**
- Modify: `frontend/src/pages/platforms/xhs/crawler-page.tsx`

- [ ] **Step 1: Add Ant Design Radio to the component import**

Replace the existing Ant Design import at the top of `frontend/src/pages/platforms/xhs/crawler-page.tsx`:

```tsx
import { Alert, Button, Card, Checkbox, Col, Collapse, Empty, Form, Input, InputNumber, Row, Select, Space, Spin, Table, Tag, Typography } from "antd";
```

with:

```tsx
import { Alert, Button, Card, Checkbox, Col, Collapse, Empty, Form, Input, InputNumber, Radio, Row, Select, Space, Spin, Table, Tag, Typography } from "antd";
```

- [ ] **Step 2: Add a crawl channel type near the existing option constants**

Insert this type after `distanceOptions` and before `splitUrls`:

```tsx
type CrawlChannel = "keyword_group" | "manual_keyword";
```

The nearby code should look like this after the change:

```tsx
const distanceOptions = [
  { value: 0, label: "不限距离" },
  { value: 1, label: "同城" },
  { value: 2, label: "附近" },
];

type CrawlChannel = "keyword_group" | "manual_keyword";

function splitUrls(value: string): string[] {
  return value.split(/\r?\n|,/).map((url) => url.trim()).filter(Boolean);
}
```

- [ ] **Step 3: Change crawler state initialization**

Inside `XhsCrawlerPage`, replace this block:

```tsx
  const [selectedAccountId, setSelectedAccountId] = useState<number | null>(null);
  const [selectedKeywordGroupId, setSelectedKeywordGroupId] = useState<number | null>(initialKeywordGroupId);
  const [keywordLimit, setKeywordLimit] = useState(5);
  const [maxNotesPerKeyword, setMaxNotesPerKeyword] = useState(5);
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [summaryMessage, setSummaryMessage] = useState<string | null>(null);
  const [keywordGroupSummary, setKeywordGroupSummary] = useState<XhsKeywordGroupCrawlSummary | null>(null);
  const [mode, setMode] = useState<XhsDataCrawlMode>(initialKeywordGroupId ? "search" : "note_urls");
```

with:

```tsx
  const [selectedAccountId, setSelectedAccountId] = useState<number | null>(null);
  const [selectedKeywordGroupId, setSelectedKeywordGroupId] = useState<number | null>(initialKeywordGroupId);
  const [crawlChannel, setCrawlChannel] = useState<CrawlChannel>(initialKeywordGroupId ? "keyword_group" : "manual_keyword");
  const [keywordLimit, setKeywordLimit] = useState(5);
  const [maxNotesPerKeyword, setMaxNotesPerKeyword] = useState(5);
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [summaryMessage, setSummaryMessage] = useState<string | null>(null);
  const [keywordGroupSummary, setKeywordGroupSummary] = useState<XhsKeywordGroupCrawlSummary | null>(null);
  const [mode, setMode] = useState<XhsDataCrawlMode>("search");
```

This makes normal entry default to manual keyword collection, while links from a keyword group still open the keyword group channel.

- [ ] **Step 4: Change keyword group mode detection**

Replace:

```tsx
  const isKeywordGroupMode = Boolean(selectedKeywordGroupId);
```

with:

```tsx
  const isKeywordGroupMode = crawlChannel === "keyword_group";
```

Do not use `selectedKeywordGroupId` to decide the visible channel. A selected keyword group can exist while the user is using the manual keyword channel.

- [ ] **Step 5: Add a channel-change helper**

Add this function after `loadKeywordGroups` and before `handleSimpleRun`:

```tsx
  function handleChannelChange(nextChannel: CrawlChannel) {
    setCrawlChannel(nextChannel);
    if (nextChannel === "manual_keyword") {
      setMode("search");
    }
  }
```

This ensures choosing the manual keyword channel always returns the user to the primary manual search path instead of leaving them in the secondary URL/comment mode.

- [ ] **Step 6: Run TypeScript build to catch import/state mistakes**

Run:

```bash
npm --prefix frontend run build
```

Expected result: the build succeeds. Existing Vite chunk-size warnings are acceptable. Any TypeScript error here should be fixed before moving to Task 2.

---

### Task 2: Update submit logic to use the explicit channel

**Files:**
- Modify: `frontend/src/pages/platforms/xhs/crawler-page.tsx`

- [ ] **Step 1: Confirm `handleRun` branches on `isKeywordGroupMode`**

After Task 1, `isKeywordGroupMode` is channel-based. The beginning of `handleRun` should remain this shape:

```tsx
  async function handleRun(e?: FormEvent) {
    e?.preventDefault();
    setError(null);
    setSummaryMessage(null);
    setKeywordGroupSummary(null);
    if (isKeywordGroupMode) { await handleSimpleRun(); return; }
    if (!selectedAccountId) { setError("请先选择一个 PC 账号。"); return; }
    const parsedUrls = splitUrls(urls);
    if (mode !== "search" && parsedUrls.length === 0) { setError("请至少输入一个笔记链接。"); return; }
    if (mode === "search" && !keyword.trim()) { setError("请填写搜索关键词。"); return; }
```

No backend call changes are needed in this step. The important behavior change is that manual keyword mode is no longer overridden by an already-selected keyword group.

- [ ] **Step 2: Keep the existing stream payload for manual keyword search**

The `crawlXhsDataStream` call should continue to pass the current `mode`, but because the manual keyword channel sets `mode` to `"search"`, the normal manual path calls the search crawler:

```tsx
      const summary = await crawlXhsDataStream(
        { account_id: selectedAccountId, mode, urls: parsedUrls, keyword: keyword.trim(), pages, max_notes: maxNotes, time_sleep: timeSleep, comment_sleep: commentSleep, fetch_comments: mode === "comments" ? false : fetchCommentsChecked, ...filters, geo: filters.geo.trim() },
        (index, item) => { setItems((prev) => [...prev, item]); },
        (msg) => { setProgressMsg(msg); },
        (msg) => { setError(msg); },
      );
```

This preserves the existing note URL and comment paths for the secondary modes.

- [ ] **Step 3: Run build after submit-logic changes**

Run:

```bash
npm --prefix frontend run build
```

Expected result: the build succeeds. Existing Vite chunk-size warnings are acceptable.

---

### Task 3: Replace the crawler form with clear channel-first UI

**Files:**
- Modify: `frontend/src/pages/platforms/xhs/crawler-page.tsx`

- [ ] **Step 1: Replace the current form content from the first info alert through the pre-submit field blocks**

Inside the `<Card style={{ marginBottom: 24 }}>` form, replace the current block that starts with:

```tsx
          <Alert
            type="info"
            showIcon
            message="关键词组一键采集"
            description="选择关键词组后，系统会自动低频搜索、获取详情，只保存有效内容，并在结束后汇总保存和跳过原因。"
            style={{ marginBottom: 16 }}
          />
```

and ends just before:

```tsx
          <Space>
            <Button type="primary" htmlType="submit" loading={isRunning} disabled={noPcAccount || (isKeywordGroupMode && !selectedKeywordGroupId)} icon={isKeywordGroupMode || mode === "search" ? <SearchOutlined /> : <CloudDownloadOutlined />}>
```

with this complete block:

```tsx
          <Alert
            type="info"
            showIcon
            message="选择采集通道"
            description="关键词组适合计划内批量采集；手动关键词适合临时验证选题。系统会低频搜索、获取详情，只保存有效内容，并在结束后汇总保存和跳过原因。"
            style={{ marginBottom: 16 }}
          />

          <Row gutter={16}>
            <Col xs={24} md={8}>
              <Form.Item label="PC 账号">
                <Select
                  value={selectedAccountId}
                  onChange={setSelectedAccountId}
                  placeholder="选择 PC 账号"
                  options={pcAccounts.map((a) => ({ value: a.id, label: `${a.nickname || `PC 账号 ${a.id}`} · ${a.status}` }))}
                />
              </Form.Item>
            </Col>
            <Col xs={24} md={16}>
              <Form.Item label="采集通道">
                <Radio.Group value={crawlChannel} onChange={(e) => handleChannelChange(e.target.value as CrawlChannel)}>
                  <Radio.Button value="keyword_group">关键词组采集</Radio.Button>
                  <Radio.Button value="manual_keyword">手动关键词</Radio.Button>
                </Radio.Group>
              </Form.Item>
            </Col>
          </Row>

          {isKeywordGroupMode ? (
            <>
              <Row gutter={16}>
                <Col xs={24} md={8}>
                  <Form.Item label="关键词组">
                    <Select
                      allowClear
                      value={selectedKeywordGroupId ?? undefined}
                      onChange={(value) => setSelectedKeywordGroupId(value ?? null)}
                      placeholder="选择关键词组后一键采集"
                      options={keywordGroups.map((group) => ({ value: group.id, label: `${group.name} · ${group.keywords.length} 词` }))}
                    />
                  </Form.Item>
                </Col>
                <Col xs={12} md={4}>
                  <Form.Item label="关键词数">
                    <InputNumber min={1} max={20} value={keywordLimit} onChange={(v) => setKeywordLimit(v ?? 5)} style={{ width: "100%" }} />
                  </Form.Item>
                </Col>
                <Col xs={12} md={4}>
                  <Form.Item label="每词最多">
                    <InputNumber min={1} max={50} value={maxNotesPerKeyword} onChange={(v) => setMaxNotesPerKeyword(v ?? 5)} style={{ width: "100%" }} />
                  </Form.Item>
                </Col>
              </Row>
              {selectedKeywordGroup ? (
                <Alert
                  type="success"
                  showIcon
                  message={`将采集「${selectedKeywordGroup.name}」前 ${Math.min(keywordLimit, selectedKeywordGroup.keywords.length)} 个关键词，每个关键词最多 ${maxNotesPerKeyword} 条。`}
                  style={{ marginBottom: 16 }}
                />
              ) : null}
            </>
          ) : (
            <>
              {mode === "search" ? (
                <>
                  <Alert
                    type="success"
                    showIcon
                    message="手动关键词采集"
                    description="输入一个关键词后，系统会按搜索结果抓取详情。适合临时验证选题、探索新关键词。"
                    style={{ marginBottom: 16 }}
                  />
                  <Row gutter={16}>
                    <Col xs={24} md={8}>
                      <Form.Item label="搜索关键词">
                        <Input value={keyword} onChange={(e) => setKeyword(e.target.value)} placeholder="低卡早餐、通勤穿搭" />
                      </Form.Item>
                    </Col>
                    <Col xs={12} md={4}>
                      <Form.Item label="爬取数量">
                        <InputNumber min={1} max={200} value={maxNotes} onChange={(v) => { const n = v ?? 20; setMaxNotes(n); setPages(Math.max(1, Math.ceil(n / 20))); }} style={{ width: "100%" }} />
                      </Form.Item>
                    </Col>
                    <Col xs={12} md={4}>
                      <Form.Item label="排序">
                        <Select value={filters.sort_type_choice} onChange={(v) => setFilters((c) => ({ ...c, sort_type_choice: v }))} options={sortOptions} />
                      </Form.Item>
                    </Col>
                    <Col xs={12} md={4}>
                      <Form.Item label="类型">
                        <Select value={filters.note_type} onChange={(v) => setFilters((c) => ({ ...c, note_type: v }))} options={noteTypeOptions} />
                      </Form.Item>
                    </Col>
                    <Col xs={12} md={4}>
                      <Form.Item label="时间范围">
                        <Select value={filters.note_time} onChange={(v) => setFilters((c) => ({ ...c, note_time: v }))} options={noteTimeOptions} />
                      </Form.Item>
                    </Col>
                    <Col xs={12} md={4}>
                      <Form.Item label="距离">
                        <Select value={filters.pos_distance} onChange={(v) => setFilters((c) => ({ ...c, pos_distance: v }))} options={distanceOptions} />
                      </Form.Item>
                    </Col>
                    <Col xs={12} md={4}>
                      <Form.Item label="Geo">
                        <Input value={filters.geo} onChange={(e) => setFilters((c) => ({ ...c, geo: e.target.value }))} placeholder="经纬度" />
                      </Form.Item>
                    </Col>
                  </Row>
                </>
              ) : (
                <Form.Item label="笔记链接">
                  <Input.TextArea value={urls} onChange={(e) => setUrls(e.target.value)} placeholder="每行一个链接，也可以用英文逗号分隔" rows={4} />
                </Form.Item>
              )}

              <Collapse
                ghost
                items={[{
                  key: "secondary-crawl-modes",
                  label: <Space><CloudDownloadOutlined />更多抓取方式（笔记链接 / 评论）</Space>,
                  children: (
                    <Row gutter={16}>
                      <Col xs={24} md={8}>
                        <Form.Item label="辅助抓取方式">
                          <Select
                            value={mode}
                            onChange={(value) => setMode(value)}
                            options={[
                              { value: "search", label: "通过搜索爬取详情" },
                              { value: "note_urls", label: "直接爬取笔记链接" },
                              { value: "comments", label: "只爬取评论" },
                            ]}
                          />
                        </Form.Item>
                      </Col>
                    </Row>
                  ),
                }]}
                style={{ marginBottom: 8 }}
              />
            </>
          )}

          <Row gutter={16}>
            <Col span={8} style={{ display: "flex", alignItems: "center", paddingTop: 8 }}>
              <Checkbox checked={fetchCommentsChecked} onChange={(e) => setFetchCommentsChecked(e.target.checked)} disabled={!isKeywordGroupMode && mode === "comments"}>同时抓取评论</Checkbox>
            </Col>
          </Row>

          {isKeywordGroupMode ? (
            <Collapse
              ghost
              activeKey={showAdvanced ? ["advanced"] : []}
              onChange={(keys) => setShowAdvanced(Array.isArray(keys) ? keys.includes("advanced") : keys === "advanced")}
              items={[{
                key: "advanced",
                label: <Space><SettingOutlined />高级设置</Space>,
                children: <Row gutter={16}>
                  <Col span={4}><Form.Item label="Time Sleep"><InputNumber min={0} max={60} step={0.5} value={timeSleep} onChange={(v) => setTimeSleep(v ?? 1)} style={{ width: "100%" }} /></Form.Item></Col>
                  <Col span={4}><Form.Item label="Comment Sleep"><InputNumber min={0} max={120} step={0.5} value={commentSleep} onChange={(v) => setCommentSleep(v ?? 5)} style={{ width: "100%" }} /></Form.Item></Col>
                  <Col span={4}><Form.Item label="排序"><Select value={filters.sort_type_choice} onChange={(v) => setFilters((c) => ({ ...c, sort_type_choice: v }))} options={sortOptions} /></Form.Item></Col>
                  <Col span={4}><Form.Item label="类型"><Select value={filters.note_type} onChange={(v) => setFilters((c) => ({ ...c, note_type: v }))} options={noteTypeOptions} /></Form.Item></Col>
                  <Col span={4}><Form.Item label="时间范围"><Select value={filters.note_time} onChange={(v) => setFilters((c) => ({ ...c, note_time: v }))} options={noteTimeOptions} /></Form.Item></Col>
                </Row>,
              }]}
            />
          ) : null}
```

- [ ] **Step 2: Update the submit button label for the manual keyword path**

Replace this button block:

```tsx
            <Button type="primary" htmlType="submit" loading={isRunning} disabled={noPcAccount || (isKeywordGroupMode && !selectedKeywordGroupId)} icon={isKeywordGroupMode || mode === "search" ? <SearchOutlined /> : <CloudDownloadOutlined />}>
              {isRunning ? "抓取中..." : isKeywordGroupMode ? "开始采集" : "开始抓取"}
            </Button>
```

with:

```tsx
            <Button type="primary" htmlType="submit" loading={isRunning} disabled={noPcAccount || (isKeywordGroupMode && !selectedKeywordGroupId)} icon={isKeywordGroupMode || mode === "search" ? <SearchOutlined /> : <CloudDownloadOutlined />}>
              {isRunning ? "抓取中..." : isKeywordGroupMode ? "开始采集" : mode === "search" ? "开始抓取关键词" : "开始抓取"}
            </Button>
```

- [ ] **Step 3: Run build after UI replacement**

Run:

```bash
npm --prefix frontend run build
```

Expected result: the build succeeds. Existing Vite chunk-size warnings are acceptable.

---

### Task 4: Manual UX verification checklist

**Files:**
- No source files changed in this task.

- [ ] **Step 1: Verify normal entry defaults to manual keyword**

Open or reason through `/platforms/xhs/crawler`.

Expected visible state:

```text
采集通道: 手动关键词
Visible fields: PC 账号, 搜索关键词, 爬取数量, 排序, 类型, 时间范围, 距离, Geo, 同时抓取评论
Primary button: 开始抓取关键词
```

- [ ] **Step 2: Verify keyword-group entry defaults to keyword group channel**

Open or reason through `/platforms/xhs/crawler?keyword_group_id=123` where `123` is an existing keyword group id.

Expected visible state:

```text
采集通道: 关键词组采集
Visible fields: PC 账号, 关键词组, 关键词数, 每词最多, 同时抓取评论, 高级设置
Primary button: 开始采集
```

- [ ] **Step 3: Verify manual channel is not hijacked by an auto-selected keyword group**

Use the normal page entry after keyword groups load. The code in `loadKeywordGroups` may still set `selectedKeywordGroupId` to the first keyword group, but the channel should remain `manual_keyword` because `isKeywordGroupMode` uses `crawlChannel`.

Expected behavior:

```text
Even when selectedKeywordGroupId is non-null, the page remains in 手动关键词 mode until the user selects 关键词组采集.
```

- [ ] **Step 4: Verify validation messages**

Use the code paths in `handleRun` to confirm these messages still match the selected channel:

```text
No PC account selected: 请先选择一个 PC 账号。
Keyword group channel without a group: 请先选择一个关键词组。
Manual keyword channel with empty keyword: 请填写搜索关键词。
Secondary URL/comment mode without URLs: 请至少输入一个笔记链接。
```

- [ ] **Step 5: Final build verification**

Run:

```bash
npm --prefix frontend run build
```

Expected result: TypeScript and Vite complete successfully. Existing Vite chunk-size warnings are acceptable and do not block completion.
