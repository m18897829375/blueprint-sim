const { chromium } = require("playwright");
const CODE = "EF013Eo0i2O06aU0579";
(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  await page.goto("http://localhost:5173/", { waitUntil: "domcontentloaded" });
  await page.waitForTimeout(5000);
  await page.click('button[aria-label="蓝图模式"]');
  await page.waitForTimeout(1000);
  await page.click('[data-ui-button-id="blueprint-action-import-code"]');
  await page.waitForTimeout(500);
  await page.fill("[data-official-import-input]", CODE);
  await page.click('[data-ui-button-id="official-import-parse"]');
  await page.waitForSelector("[data-official-import-results]", { timeout: 30000 });
  await page.click(`[data-ui-button-id="official-import-import-${CODE}"]`);
  await page.waitForTimeout(1500);
  // 保存对话框：点"保存"
  await page.click('button:has-text("保存")');
  await page.waitForTimeout(1500);
  await page.screenshot({ path: "out/ui-import-saved.png" });
  // 验证库中出现该蓝图
  const libText = await page.textContent("body");
  console.log("库中含'未命名蓝图':", libText.includes("未命名蓝图"));
  await browser.close();
})().catch((e) => { console.error("FAIL:", e.message); process.exit(1); });
