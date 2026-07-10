import { copyFileSync, existsSync, mkdirSync, readdirSync, statSync } from "node:fs";
import { basename, dirname, join } from "node:path";

// Evidence's duckdb source extraction has two zero-row quirks:
//   1. it can emit a zero-byte static Parquet file for a source query that
//      returns no rows, and
//   2. it can skip (re)writing the static Parquet entirely, leaving a stale
//      file from an earlier run whose schema no longer matches the source.
// Both break build-time page queries. The exported source Parquet under
// sources/hpt/data/ is always schema-valid (including legitimately empty
// marts), so repair by copying it over any missing, zero-byte, or stale
// generated file. "Stale" = the generated file predates the exported source.
const appRoot = new URL("..", import.meta.url).pathname;
const sourceDataDir = join(appRoot, "sources", "hpt", "data");
const staticDataRoot = join(appRoot, ".evidence", "template", "static", "data", "hpt");

if (!existsSync(sourceDataDir) || !existsSync(staticDataRoot)) {
  process.exit(0);
}

let repairedCount = 0;

for (const fileName of readdirSync(sourceDataDir)) {
  if (!fileName.endsWith(".parquet")) {
    continue;
  }

  const publicName = basename(fileName, ".parquet");
  const sourcePath = join(sourceDataDir, fileName);
  const staticPath = join(staticDataRoot, publicName, fileName);

  const sourceStat = statSync(sourcePath);
  if (sourceStat.size === 0) {
    continue;
  }

  let reason = null;
  if (!existsSync(staticPath)) {
    reason = "missing";
  } else {
    const staticStat = statSync(staticPath);
    if (staticStat.size === 0) {
      reason = "empty";
    } else if (staticStat.mtimeMs < sourceStat.mtimeMs) {
      reason = "stale";
    }
  }

  if (reason === null) {
    continue;
  }

  mkdirSync(dirname(staticPath), { recursive: true });
  copyFileSync(sourcePath, staticPath);
  repairedCount += 1;
  console.log(`Repaired ${reason} Evidence Parquet output: ${publicName}`);
}

if (repairedCount > 0) {
  console.log(`Repaired ${repairedCount} Evidence Parquet output file(s).`);
}
