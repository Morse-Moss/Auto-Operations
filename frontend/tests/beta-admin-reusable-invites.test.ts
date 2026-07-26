import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const pageSource = readFileSync("frontend/src/pages/admin/beta-admin-page.tsx", "utf8");
const apiSource = readFileSync("frontend/src/lib/api/admin.ts", "utf8");

assert.match(
  apiSource,
  /createAdminInviteCode\(payload: \{ code\?: string; max_uses: number \}\)/,
  "Admin API should allow the server to generate an invite code",
);
assert.match(
  apiSource,
  /disableAdminInviteCode\(inviteId: number\)/,
  "Admin API should expose invite disabling",
);
assert.match(
  apiSource,
  /activateAdminInviteCode\(inviteId: number\)/,
  "Admin API should expose invite reactivation",
);
assert.match(
  pageSource,
  /const RESUME_INVITE_MAX_USES = 100;/,
  "Resume invites should be bounded to 100 uses",
);
assert.match(
  pageSource,
  /async function createResumeInvite\(\)/,
  "Admin page should expose one-click resume invite creation",
);
assert.match(
  pageSource,
  /navigator\.clipboard\.writeText\(invite\.code\)/,
  "Invite codes should be copyable from the admin page",
);
assert.match(
  pageSource,
  /Math\.max\(invite\.max_uses - invite\.used_count, 0\)/,
  "Invite table should display remaining uses without going negative",
);
assert.match(
  pageSource,
  /toggleInviteStatus/,
  "Admin page should expose disable and reactivate actions",
);
assert.match(
  pageSource,
  /scroll=\{\{ x: 760 \}\}/,
  "Invite table should scroll internally instead of compressing columns on mobile",
);
assert.match(
  pageSource,
  /whiteSpace: "nowrap"/,
  "Invite codes should remain readable without character-by-character wrapping",
);
assert.match(
  pageSource,
  /const \{ message \} = App\.useApp\(\);/,
  "Admin feedback should use the configured Ant Design app context",
);
assert.match(
  pageSource,
  /title=\{`可使用 \$\{latestInvite\.max_uses\} 次`\}/,
  "Generated invite alert should use the current Ant Design title API",
);

console.log("beta-admin reusable invite tests passed");
