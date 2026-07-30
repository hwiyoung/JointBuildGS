#!/usr/bin/env node
/**
 * Build and verify the portable report with a narrow Chromium scrollbar fix.
 *
 * data-analytics 0.2.8 sizes the sticky top bar to 100vw. Chromium's classic
 * vertical scrollbar makes 100vw wider than documentElement.clientWidth and
 * triggers the package's hard overflow verifier on long reports. This keeps
 * the plugin runtime and artifact intact, but sizes the bar to its shell.
 */

import { readFileSync, rmSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";

import { buildPortableArtifact } from "/home/innopam/.codex/plugins/cache/openai-curated-remote/data-analytics/0.2.8-13ceeea1f599/skills/build-report/scripts/build_portable_artifact.mjs";
import { extractPortableChartSvgs } from "/home/innopam/.codex/plugins/cache/openai-curated-remote/data-analytics/0.2.8-13ceeea1f599/skills/build-report/scripts/extract_portable_chart_svgs.mjs";
import { verifyPortableArtifact } from "/home/innopam/.codex/plugins/cache/openai-curated-remote/data-analytics/0.2.8-13ceeea1f599/skills/build-report/scripts/verify_portable_artifact.mjs";


const reportDirectory = resolve(import.meta.dirname);
const artifactPath = resolve(reportDirectory, "artifact.json");
const outputPath = resolve(reportDirectory, "report.html");
const extractionPath = resolve(reportDirectory, ".report.chart-extraction.html");
const artifact = JSON.parse(readFileSync(artifactPath, "utf8"));
const compatibilityStyle = [
  "<style id=\"jointbuildgs-portable-scrollbar-fix\">",
  ".analytics-top-bar{",
  "width:calc(100% + var(--ds-gutter) + var(--ds-gutter));",
  "margin-right:calc(0px - var(--ds-gutter));",
  "margin-left:calc(0px - var(--ds-gutter));",
  "}",
  ".portable-page-header{width:calc(100% + 64px);margin-right:-32px;margin-left:-32px}",
  "</style>",
].join("");

function applyCompatibilityStyle(html) {
  if (!html.includes("</body>")) throw new Error("portable HTML has no closing body");
  return html.replace("</body>", `${compatibilityStyle}</body>`);
}

try {
  writeFileSync(extractionPath, applyCompatibilityStyle(buildPortableArtifact(artifact)), "utf8");
  const staticCharts = await extractPortableChartSvgs({ htmlPath: extractionPath });
  const html = applyCompatibilityStyle(buildPortableArtifact(artifact, { staticCharts }));
  writeFileSync(outputPath, html, "utf8");
  const verification = await verifyPortableArtifact({
    artifactPath,
    htmlPath: outputPath,
    timeoutMs: 20_000,
  });
  process.stdout.write(`${JSON.stringify(verification)}\n`);
} finally {
  rmSync(extractionPath, { force: true });
}
