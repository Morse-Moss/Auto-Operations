import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const filePath = path.resolve(__dirname, "../src/pages/platforms/xhs/xhs-draft-workbench.tsx");
const source = readFileSync(filePath, "utf8");

assert.match(
  source,
  /visibleAssets\.map\(\(asset, index\) =>/,
  "Draft source asset thumbnails should expose the index for user-facing alt text",
);

assert.match(
  source,
  /referrerPolicy="no-referrer"/,
  "Draft source asset thumbnails should not send a referrer when loading remote images",
);

assert.match(
  source,
  /alt=\{`来源图片 \$\{index \+ 1\}`\}/,
  "Draft source asset thumbnails should use user-facing alt text",
);

console.log("xhs-draft-workbench preview tests passed");
