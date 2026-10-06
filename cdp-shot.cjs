// CDP 连接用户 Chrome，截取平台当前场景
const { chromium } = require("playwright");

(async () => {
  const browser = await chromium.connectOverCDP("http://localhost:9222");
  const contexts = browser.contexts();
  const pages = contexts.flatMap((c) => c.pages());
  const page = pages.find((p) => p.url().includes("localhost:5173"));
  if (!page) { console.error("未找到平台标签页"); process.exit(1); }
  console.log("当前 URL:", page.url());
  await page.screenshot({ path: "out/cdp-scene.png" });
  // 放大右侧精炼炉管网区域（裁剪截图）
  await page.screenshot({
    path: "out/cdp-scene-right.png",
    clip: { x: 1250, y: 60, width: 670, height: 640 },
  });
  // 全页完整截图（含网格坐标参考）
  await page.screenshot({ path: "out/cdp-scene-full.png", fullPage: true });
  console.log("截图完成");
  // 读取画布上的实体（从编辑器文档状态）
  const docInfo = await page.evaluate(() => {
    // 尝试从全局应用状态读文档（平台 MobX 状态在 window 上无暴露时返回 null）
    const w = window;
    return {
      hasApp: !!w.__APP_HOST__,
      title: document.title,
      // 统计画布内 SVG/Canvas 元素
      canvases: document.querySelectorAll("canvas").length,
    };
  });
  console.log("页面信息:", JSON.stringify(docInfo));
  await browser.close();
})().catch((e) => { console.error("FAIL:", e.message); process.exit(1); });
