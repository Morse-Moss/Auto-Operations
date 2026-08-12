import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const analysisServiceSource = readFileSync(path.resolve(__dirname, "../../backend/app/services/note_analysis_service.py"), "utf8");
const adapterSource = readFileSync(path.resolve(__dirname, "../src/pages/platforms/xhs/xhs-content-library-adapter.ts"), "utf8");

assert.match(
  analysisServiceSource,
  /所有面向用户的字段值必须使用简体中文，不能输出英文翻译或英文标签/,
  "System analysis prompt should require Chinese-facing analysis values",
);
assert.match(
  adapterSource,
  /function feishuPushStatusLabel\(status: string\)/,
  "Content detail should translate internal Feishu push states",
);
assert.match(
  adapterSource,
  /function analysisSourceLabel\(source: string\)/,
  "Content detail should translate internal analysis-source states",
);
assert.match(
  adapterSource,
  /function feishuPullStatusLabel\(status: string\)/,
  "Content detail should translate internal Feishu pull states",
);
assert.match(
  adapterSource,
  /analysisSourceLabel\(analysis\?\.source \|\| \(analysis \? "system" : "-"\)\)/,
  "Content detail should render a Chinese analysis-source label",
);
assert.match(
  adapterSource,
  /feishuPushStatusLabel\(note\.feishu_sync\?\.push_status \|\| "not_synced"\)/,
  "Content detail should render a Chinese push-status label",
);
assert.match(
  adapterSource,
  /feishuPullStatusLabel\(note\.feishu_sync\?\.pull_status \|\| "not_pulled"\)/,
  "Content detail should render a Chinese pull-status label",
);

console.log("xhs content library analysis language tests passed");
