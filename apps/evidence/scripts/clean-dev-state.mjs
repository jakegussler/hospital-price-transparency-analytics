import { existsSync, rmSync } from "node:fs";
import { join } from "node:path";

const appRoot = new URL("..", import.meta.url).pathname;

const generatedPaths = [
  join(appRoot, ".evidence", "template", ".evidence-queries", "cache"),
  join(appRoot, ".evidence", "template", ".svelte-kit"),
];

for (const path of generatedPaths) {
  if (!existsSync(path)) {
    continue;
  }

  rmSync(path, {
    force: true,
    maxRetries: 5,
    recursive: true,
    retryDelay: 200,
  });
}
