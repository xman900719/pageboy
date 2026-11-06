#!/usr/bin/env node
/**
 * 书童 Docs-as-Code 静态 Mermaid 图表预渲染流水线
 *
 * 作用：在构建期扫描 docs/assets/diagrams/*.mmd 文件，
 * 使用本地已有的 Playwright 无头 Chromium 和 docs/assets/javascripts/mermaid.min.js，
 * 纯离线渲染为高保真 SVG 静态矢量图，彻底免除客户端对外部 unpkg.com 的网络依赖。
 */

import fs from "fs";
import path from "path";
import { fileURLToPath } from "url";
import { chromium } from "../apps/web/node_modules/@playwright/test/index.mjs";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const REPO_ROOT = path.resolve(__dirname, "..");
const DIAGRAMS_DIR = path.join(REPO_ROOT, "docs", "assets", "diagrams");
const MERMAID_JS_PATH = path.join(REPO_ROOT, "docs", "assets", "javascripts", "mermaid.min.js");

async function main() {
  if (!fs.existsSync(DIAGRAMS_DIR)) {
    console.error(`[错误] 图表目录不存在: ${DIAGRAMS_DIR}`);
    process.exit(1);
  }

  if (!fs.existsSync(MERMAID_JS_PATH)) {
    console.error(`[错误] Mermaid 本地库不存在: ${MERMAID_JS_PATH}`);
    process.exit(1);
  }

  const mmdFiles = fs
    .readdirSync(DIAGRAMS_DIR)
    .filter((f) => f.endsWith(".mmd"))
    .sort();

  if (mmdFiles.length === 0) {
    console.log("[提示] 未发现 .mmd 图表源文件，跳过渲染。");
    return;
  }

  console.log(`[开始] 发现 ${mmdFiles.length} 个 Mermaid 图表源文件，启动本地无头浏览器预渲染...`);

  const mermaidJs = fs.readFileSync(MERMAID_JS_PATH, "utf-8");
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();

  // 注入基础 HTML 骨架与本地 Mermaid 运行时
  await page.setContent("<div id=\"render-container\"></div>");
  await page.addScriptTag({ content: mermaidJs });

  let successCount = 0;

  for (const file of mmdFiles) {
    const baseName = path.basename(file, ".mmd");
    const mmdPath = path.join(DIAGRAMS_DIR, file);
    const svgPath = path.join(DIAGRAMS_DIR, `${baseName}.svg`);
    const code = fs.readFileSync(mmdPath, "utf-8");

    try {
      const svg = await page.evaluate(
        async ({ id, code }) => {
          mermaid.initialize({
            startOnLoad: false,
            theme: "default",
            securityLevel: "loose",
            flowchart: { useMaxWidth: true, htmlLabels: true },
          });
          const { svg } = await mermaid.render(`diagram_${id}`, code);
          return svg;
        },
        { id: baseName.replace(/[^a-zA-Z0-9_]/g, "_"), code }
      );

      fs.writeFileSync(svgPath, svg, "utf-8");
      console.log(`[成功] 已渲染: docs/assets/diagrams/${baseName}.svg (${svg.length} 字节)`);
      successCount++;
    } catch (err) {
      console.error(`[失败] 渲染图表 ${file} 出错:`, err);
      await browser.close();
      process.exit(1);
    }
  }

  await browser.close();
  console.log(`[完成] 全部 ${successCount} 个静态矢量图渲染完成！`);
}

main().catch((err) => {
  console.error("[异常] 渲染流水线异常退出:", err);
  process.exit(1);
});
