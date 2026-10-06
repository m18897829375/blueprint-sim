// 平台 UI 探索脚本：打开首页，截图 + 列出可操作按钮
const { chromium } = require("playwright");

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  await page.goto("http://localhost:5173/", { waitUntil: "domcontentloaded", timeout: 30000 });
  await page.waitForTimeout(6000);
  await page.screenshot({ path: "out/ui-home.png", fullPage: false });
  // 列出全部按钮文本与 aria-label
  const buttons = await page.$$eval("button", (els) =>
    els.slice(0, 60).map((el) => ({
      text: (el.textContent || "").trim().slice(0, 40),
      aria: el.getAttribute("aria-label") || "",
      uiButtonId: el.getAttribute("data-ui-button-id") || "",
    })).filter((b) => b.text || b.aria || b.uiButtonId));
  console.log(JSON.stringify(buttons, null, 1));
  await browser.close();
})().catch((e) => { console.error(e); process.exit(1); });
