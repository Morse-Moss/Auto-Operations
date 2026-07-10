import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const platformsSource = readFileSync("frontend/src/lib/platforms.ts", "utf8");
const routerSource = readFileSync("frontend/src/app/router.tsx", "utf8");

assert.match(
  platformsSource,
  /export const WECHAT_OFFICIAL_PUBLIC_ENABLED = false;/,
  "WeChat Official should have a single frontend public-enable switch that is off while offline development continues",
);

assert.match(
  platformsSource,
  /id: "wechat_official",[\s\S]*enabled: WECHAT_OFFICIAL_PUBLIC_ENABLED,[\s\S]*status: WECHAT_OFFICIAL_PUBLIC_ENABLED \? "beta" : "coming_soon",[\s\S]*release_stage: WECHAT_OFFICIAL_PUBLIC_ENABLED \? "beta" : "planned",[\s\S]*default_route: WECHAT_OFFICIAL_PUBLIC_ENABLED \? "\/platforms\/wechat-official\/library" : null,[\s\S]*adapter_key: WECHAT_OFFICIAL_PUBLIC_ENABLED \? "wechat_official" : null,/,
  "fallback platform metadata should keep WeChat Official hidden from the public selector when the switch is off",
);

assert.match(
  routerSource,
  /import \{ WECHAT_OFFICIAL_PUBLIC_ENABLED \} from "\.\.\/lib\/platforms";/,
  "router should read the same public-enable switch as the fallback registry",
);

assert.match(
  routerSource,
  /WECHAT_OFFICIAL_PUBLIC_ENABLED \? \([\s\S]*path="\/platforms\/wechat-official\/dashboard"[\s\S]*\) : \([\s\S]*path="\/platforms\/wechat-official\/\*"[\s\S]*<Navigate to="\/platform-select" replace \/>/,
  "direct WeChat Official URLs should redirect back to platform select while the public switch is off",
);

console.log("wechat-official-public-disabled tests passed");
