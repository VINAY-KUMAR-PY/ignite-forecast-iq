import { spawnSync } from "node:child_process";

const result = spawnSync("npx", ["playwright", "test", "tests/e2e/demo.spec.ts"], {
  stdio: "inherit",
  shell: process.platform === "win32",
});

process.exit(result.status ?? 1);
