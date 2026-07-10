import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const source = readFileSync("frontend/src/components/layout/app-shell.tsx", "utf8");
const packageJson = readFileSync("frontend/package.json", "utf8");

assert.match(
  source,
  /import \{[^}]*\bOutlet\b[^}]*\} from "react-router-dom";/,
  "AppShell should use the official react-router-dom Outlet so route hooks share the BrowserRouter context",
);
assert.doesNotMatch(
  source,
  /keepalive-for-react-router/,
  "AppShell should not use keepalive-for-react-router because it can resolve a different react-router instance in production",
);
assert.match(
  source,
  /<Outlet\s*\/>/,
  "AppShell content should render child routes through Outlet",
);
assert.doesNotMatch(
  packageJson,
  /keepalive-for-react-router|keepalive-for-react/,
  "frontend dependencies should not include unused keepalive router packages that can pull in a mismatched react-router",
);

console.log("app-shell-router-outlet tests passed");
