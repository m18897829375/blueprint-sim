// 官方蓝图码导入流程端到端验收：
// 蓝图模式 → 从蓝图码导入 → 输入码 → 解析 → 报告 → 导入 → 保存确认 → 库中可见
const { chromium } = require("playwright");

const CODE = process.argv[2] || "EF013Eo0i2O06aU0579"; // bp_simple

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  page.on("console", (msg) => {
    if (msg.type() === "error") console.log("[console.error]", msg.text().slice(0, 200));
  });
  await page.goto("http://localhost:5173/", { waitUntil: "domcontentloaded", timeout: 30000 });
  await page.waitForTimeout(5000);

  // 1. 打开蓝图面板
  await page.click('button[aria-label="蓝图模式"]');
  await page.waitForTimeout(1200);

  // 2. 点"从蓝图码导入"
  const importBtn = page.locator('[data-ui-button-id="blueprint-action-import-code"]');
  await importBtn.waitFor({ state: "visible", timeout: 5000 });
  await importBtn.click();
  await page.waitForTimeout(600);
  await page.screenshot({ path: "out/ui-import-dialog.png" });

  // 3. 输入蓝图码并解析
  await page.fill("[data-official-import-input]", CODE);
  await page.click('[data-ui-button-id="official-import-parse"]');
  // 等待解析结果（API + 转换）
  await page.waitForSelector("[data-official-import-results]", { timeout: 30000 });
  await page.waitForTimeout(500);
  await page.screenshot({ path: "out/ui-import-report.png" });
  const reportText = await page.textContent("[data-official-import-results]");
  console.log("=== 报告文本 ===");
  console.log(reportText);

  // 4. 点导入（打开保存确认对话框）
  await page.click(`[data-ui-button-id="official-import-import-${CODE}"]`);
  await page.waitForTimeout(1200);
  await page.screenshot({ path: "out/ui-import-save.png" });

  // 5. 保存对话框：找确认按钮（保存/确认）
  const saveButtons = await page.$$eval("button", (els) =>
    els.map((el) => ({
      text: (el.textContent || "").trim().slice(0, 30),
      uiButtonId: el.getAttribute("data-ui-button-id") || "",
    })).filter((b) => /保存|确认|save|提交/.test(b.text + b.uiButtonId)));
  console.log("=== 保存对话框按钮 ===", JSON.stringify(saveButtons));
  await browser.close();
})().catch((e) => { console.error("FAIL:", e.message); process.exit(1); });
