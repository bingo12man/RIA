import { defineConfig } from "vite";
import baseConfig from "./vite.config.js";

const original = baseConfig.server?.proxy || {};

const commandRule = original["/api/command"];

if (!commandRule) {
  throw new Error(
    "Expected /api/command proxy not found. Check vite.config.js."
  );
}

const replaceTarget = (rule, target) =>
  typeof rule === "string"
    ? target
    : { ...rule, target };

// Put the experimental command route first.
// Preserve its existing rewrite rules.
const proxy = {
  "/api/command": replaceTarget(
    commandRule,
    "http://127.0.0.1:8012"
  ),
};

for (const [route, rule] of Object.entries(original)) {
  if (route === "/api/command") continue;

  // Redirect reminder routes to temporary port 8011.
  const target = typeof rule === "string" ? rule : rule.target;

  proxy[route] = target?.includes("127.0.0.1:8001")
    ? replaceTarget(rule, "http://127.0.0.1:8011")
    : rule;
}

export default defineConfig({
  ...baseConfig,
  server: {
    ...baseConfig.server,
    host: "127.0.0.1",
    port: 5174,
    strictPort: true,
    proxy,
  },
});
