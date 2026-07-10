import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const source = readFileSync("frontend/src/components/ui/protected-route.tsx", "utf8");

assert.match(
  source,
  /function AuthCheckingScreen\(\)[\s\S]*?setTimeout\(\(\) => setShowRecovery\(true\), 8000\)/,
  "auth checking screen should reveal a recovery action after a short wait",
);
assert.match(
  source,
  /function resetStalledAuthCheck\(\): void \{[\s\S]*?clearAuthTokens\(\);[\s\S]*?window\.location\.assign\("\/login"\);/,
  "recovery action should clear stale auth state and return the user to login",
);
assert.match(
  source,
  /<Button type="primary" onClick=\{resetStalledAuthCheck\}>[\s\S]*?重新登录[\s\S]*?<\/Button>/,
  "stalled auth recovery should be visible as a primary login action",
);

console.log("protected-route-auth-checking tests passed");
