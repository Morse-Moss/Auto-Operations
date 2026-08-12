import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";

const registrySource = readFileSync("frontend/src/platform-core/registry/platform-sections.tsx", "utf8");
const shellSource = readFileSync("frontend/src/components/layout/app-shell.tsx", "utf8");
const routerSource = readFileSync("frontend/src/app/router.tsx", "utf8");
const discoverySource = readFileSync("frontend/src/pages/platforms/xhs/discovery-page.tsx", "utf8");
const pagePath = "frontend/src/pages/platforms/xhs/xhs-data-sources-page.tsx";
assert.equal(existsSync(pagePath), true, "Unified System Data Sources page should exist");
const pageSource = readFileSync(pagePath, "utf8");

const xhsRegistry = registrySource.match(/"xhs": \[([\s\S]*?)\],\s*"demo-platform"/)?.[1] ?? "";

assert.match(
  xhsRegistry,
  /key: "sources"[\s\S]*?path: "\/platforms\/xhs\/crawler"[\s\S]*?label: "系统数据源"/,
  "XHS sidebar should expose one unified System Data Sources entry",
);
assert.doesNotMatch(xhsRegistry, /key: "discovery"|key: "keywords"/, "Legacy discovery and keyword pages should not remain separate sidebar entries");

assert.match(pageSource, /import \{ XhsKeywordsPage \} from "\.\/keywords-page";/, "Unified page should render keyword groups as a data-source mode");
assert.match(
  pageSource,
  /key: "keywords"[\s\S]*?关键词组[\s\S]*?key: "system"[\s\S]*?系统发现[\s\S]*?key: "realtime"[\s\S]*?小红书实时/,
  "Keyword groups should be the first data-source tab before System Discovery and XHS Realtime",
);
assert.match(pageSource, /历史上已出现账号封禁/, "XHS Realtime should disclose the observed account-ban risk");
assert.match(pageSource, /<XhsDiscoveryPage\s*\/>/, "XHS Realtime should preserve note cards and URL lookup from Note Discovery");
assert.doesNotMatch(pageSource, /管理关键词组/, "Keyword groups should not be hidden behind a contextual management button");

assert.match(
  routerSource,
  /path="\/platforms\/xhs\/crawler" element=\{<XhsDataSourcesPage\s*\/>\}/,
  "The canonical data-source route should render the unified page",
);
assert.match(
  routerSource,
  /path="\/platforms\/xhs\/discovery"[\s\S]*?<Navigate to="\/platforms\/xhs\/crawler\?source=realtime" replace \/>/,
  "Legacy Note Discovery links should redirect to XHS Realtime",
);
assert.match(
  shellSource,
  /getPlatformSelectedNavPath\(location\.pathname\)/,
  "Legacy keyword and discovery routes should keep the unified sidebar entry selected",
);
assert.match(
  discoverySource,
  /<Col xs=\{24\} sm=\{12\} lg=\{6\}>[\s\S]*?搜索账号[\s\S]*?<Col xs=\{24\} sm=\{12\} lg=\{6\}>[\s\S]*?关键词/,
  "Realtime account and keyword fields should stack cleanly on mobile",
);
assert.match(
  discoverySource,
  /<Col xs=\{12\} sm=\{6\} lg=\{3\}>[\s\S]*?排序[\s\S]*?<Col xs=\{12\} sm=\{6\} lg=\{3\}>[\s\S]*?范围/,
  "Realtime compact filters should use two columns on mobile and four columns on larger screens",
);
assert.match(
  discoverySource,
  /<Col xs=\{24\} sm=\{16\} lg=\{12\}>[\s\S]*?笔记 URL[\s\S]*?<Col xs=\{24\} sm=\{8\} lg=\{4\}>[\s\S]*?<Button[\s\S]*?block[\s\S]*?>URL 直查<\/Button>/,
  "Realtime URL lookup should remain readable and tappable on mobile",
);

console.log("xhs data sources navigation tests passed");
