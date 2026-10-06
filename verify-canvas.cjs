// 蓝图放置画布截图（完整流程：导入→保存→预览→放置）
const { chromium } = require("playwright");
const CODE = "EF015i2O4O271uaUOeIoe";

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
  await page.waitForSelector("[data-official-import-results]", { timeout: 60000 });
  await page.click(`[data-ui-button-id="official-import-import-${CODE}"]`);
  await page.waitForTimeout(1500);
  await page.click('button:has-text("保存")');
  await page.waitForTimeout(1500);
  // 库中点蓝图 → 预览 → 放置
  await page.locator('text=龙泡泡一期').first().click();
  await page.waitForTimeout(1200);
  await page.locator('button:has-text("放置")').first().click();
  // 等待预览对话框关闭（backdrop 消失）再点画布
  await page.waitForSelector(".blueprint-preview-dialog-backdrop", { state: "detached", timeout: 10000 }).catch(() => {});
  await page.waitForTimeout(1500);
  await page.mouse.click(480, 430);
  await page.waitForTimeout(800);
  await page.mouse.click(480, 430);
  await page.waitForTimeout(2500);
  await page.screenshot({ path: "out/ui-bpuser-canvas.png" });
  console.log("画布截图完成");
  await browser.close();
})().catch((e) => { console.error("FAIL:", e.message); process.exit(1); });
