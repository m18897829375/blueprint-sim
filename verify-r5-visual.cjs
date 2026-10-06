// R5 蓝图码校验浏览器验收 + R2/R3 视觉诊断（bp_user 画布截图）
const { chromium } = require("playwright");

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  await page.goto("http://localhost:5173/", { waitUntil: "domcontentloaded" });
  await page.waitForTimeout(5000);
  await page.click('button[aria-label="蓝图模式"]');
  await page.waitForTimeout(1000);
  await page.click('[data-ui-button-id="blueprint-action-import-code"]');
  await page.waitForTimeout(500);

  // 场景 1：带空格的码（用户最常见错误）
  await page.fill("[data-official-import-input]", "  EF015i2O4O271uaUOeIoe  ");
  await page.click('[data-ui-button-id="official-import-parse"]');
  await page.waitForSelector("[data-official-import-results]", { timeout: 60000 });
  const r1 = await page.textContent("[data-official-import-results]");
  console.log("场景1（前后空格）:", r1.includes("实体 127") ? "PASS 解析成功" : "FAIL: " + r1.slice(0, 150));

  // 场景 2：外服码（EFO 前缀）应拒绝
  await page.fill("[data-official-import-input]", "EFO01eAo0I01OI4Aoui8");
  await page.click('[data-ui-button-id="official-import-parse"]');
  await page.waitForSelector("[data-official-import-results]", { timeout: 10000 });
  await page.waitForTimeout(400);
  const r2 = await page.textContent("[data-official-import-results]");
  console.log("场景2（外服码拒绝）:", r2.includes("中国大陆") ? "PASS 明确拒绝" : "FAIL: " + r2.slice(0, 150));
  await page.screenshot({ path: "out/ui-r5-validation.png" });

  // 场景 3：bp_user 导入 → 应用到画布 → 截图（R2/R3 视觉诊断）
  await page.fill("[data-official-import-input]", "EF015i2O4O271uaUOeIoe");
  await page.click('[data-ui-button-id="official-import-parse"]');
  await page.waitForSelector("[data-official-import-results]", { timeout: 60000 });
  await page.click('[data-ui-button-id="official-import-import-EF015i2O4O271uaUOeIoe"]');
  await page.waitForTimeout(1500);
  // 保存对话框确认
  const saveBtn = page.locator('button:has-text("保存")');
  if (await saveBtn.count() > 0) { await saveBtn.first().click(); await page.waitForTimeout(1500); }
  // 库中找到蓝图并点击（预览/应用）
  const libItem = page.locator('text=龙泡泡一期').first();
  if (await libItem.count() > 0) {
    await libItem.click();
    await page.waitForTimeout(1200);
    await page.screenshot({ path: "out/ui-bpuser-preview.png" });
    // 找"应用蓝图"按钮
    const applyBtn = page.locator('button:has-text("应用蓝图")');
    console.log("应用蓝图按钮存在:", await applyBtn.count() > 0);
    if (await applyBtn.count() > 0) {
      await applyBtn.first().click();
      await page.waitForTimeout(2500);
      await page.screenshot({ path: "out/ui-bpuser-canvas.png" });
      console.log("已应用并截图 out/ui-bpuser-canvas.png");
    }
  } else {
    console.log("库中未找到龙泡泡一期");
  }
  await browser.close();
})().catch((e) => { console.error("FAIL:", e.message); process.exit(1); });
