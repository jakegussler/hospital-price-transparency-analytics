import { copyFileSync, existsSync, readdirSync, statSync } from "node:fs";
import { basename, join } from "node:path";

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

  if (!existsSync(staticPath)) {
    continue;
  }

  const sourceSize = statSync(sourcePath).size;
  const staticSize = statSync(staticPath).size;

  if (sourceSize > 0 && staticSize === 0) {
    copyFileSync(sourcePath, staticPath);
    repairedCount += 1;
    console.log(`Repaired empty Evidence Parquet output: ${publicName}`);
  }
}

if (repairedCount > 0) {
  console.log(`Repaired ${repairedCount} empty Evidence Parquet output file(s).`);
}
