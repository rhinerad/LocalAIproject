#!/usr/bin/env node
// Reapplies a local Windows fix inside tools/image-blaster (upstream, not committed).
// The stock entry check compares import.meta.url to "file://" + argv[1]. On Windows
// those strings differ (file:///A:/... vs A:\...), so the CLIs exit 0 without running.
// Usage: node scripts/patch-image-blaster-windows-entry.mjs <image-blaster-dir>
import { readdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";

const root = process.argv[2];
if (!root) {
  console.error("Usage: node scripts/patch-image-blaster-windows-entry.mjs <image-blaster-dir>");
  process.exit(1);
}

const OLD = "if (import.meta.url === `file://${process.argv[1]}`)";
const NEXT = "if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href)";
const IMPORT_LINE = 'import { pathToFileURL } from "node:url";';

async function mjsFiles(dir) {
  const found = [];
  const entries = await readdir(dir, { withFileTypes: true });
  for (const entry of entries) {
    const fullPath = path.join(dir, entry.name);
    if (entry.isDirectory()) found.push(...await mjsFiles(fullPath));
    else if (entry.name.endsWith(".mjs")) found.push(fullPath);
  }
  return found;
}

const scriptsDir = path.join(root, ".claude", "scripts");
const files = await mjsFiles(scriptsDir);
let patched = 0;

for (const file of files) {
  const original = await readFile(file, "utf8");
  if (!original.includes(OLD)) continue;

  let text = original;
  if (!text.includes("pathToFileURL")) {
    const newlineAt = text.indexOf("\n");
    const insertAt = text.startsWith("#!") && newlineAt !== -1 ? newlineAt + 1 : 0;
    text = text.slice(0, insertAt) + IMPORT_LINE + "\n" + text.slice(insertAt);
  }

  const count = text.split(OLD).length - 1;
  text = text.replaceAll(OLD, NEXT);
  if (text !== original) {
    await writeFile(file, text);
    patched += count;
    console.log(`patched ${path.relative(root, file)}`);
  }
}

console.log(`entry guards patched: ${patched}`);
