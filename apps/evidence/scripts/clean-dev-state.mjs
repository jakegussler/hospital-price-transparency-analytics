import { existsSync, renameSync, rmSync } from "node:fs";
import { basename, dirname, join } from "node:path";

const appRoot = new URL("..", import.meta.url).pathname;

const generatedPaths = [
  join(appRoot, ".evidence", "template", ".evidence-queries", "cache"),
  join(appRoot, ".evidence", "template", ".svelte-kit"),
];

for (const path of generatedPaths) {
  removeGeneratedPath(path);
}

function removeGeneratedPath(path) {
  for (let attempt = 1; attempt <= 5; attempt += 1) {
    if (!existsSync(path)) {
      return;
    }

    const deletePath = join(
      dirname(path),
      `.${basename(path)}.delete-${process.pid}-${Date.now()}-${attempt}`,
    );

    try {
      renameSync(path, deletePath);
      removeTree(deletePath);
    } catch {
      removeTree(path);
    }

    sleep(250);
  }

  if (existsSync(path)) {
    console.warn(`Warning: generated Evidence state still exists at ${path}`);
  }
}

function removeTree(path) {
  try {
    rmSync(path, {
      force: true,
      maxRetries: 20,
      recursive: true,
      retryDelay: 250,
    });
  } catch (error) {
    if (error?.code === "ENOENT") {
      return;
    }

    console.warn(
      `Warning: could not fully remove generated Evidence state at ${path}: ${error.message}`,
    );
  }
}

function sleep(milliseconds) {
  Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, milliseconds);
}
