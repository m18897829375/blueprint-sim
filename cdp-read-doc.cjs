// CDP 读取平台蓝图库内容（name/实体数/完整实体）
const { chromium } = require("playwright");
const fs = require("fs");

(async () => {
  const browser = await chromium.connectOverCDP("http://localhost:9222");
  const pages = browser.contexts().flatMap((c) => c.pages());
  const page = pages.find((p) => p.url().includes("localhost:5173"));
  if (!page) { console.error("未找到平台标签页"); process.exit(1); }

  const blueprints = await page.evaluate(async () => {
    const db = await new Promise((res, rej) => {
      const r = indexedDB.open("v3-industrial-planner");
      r.onsuccess = () => res(r.result);
      r.onerror = () => rej(r.error);
    });
    const tx = db.transaction("blueprints", "readonly");
    const store = tx.objectStore("blueprints");
    const all = await new Promise((res) => { const g = store.getAll(); g.onsuccess = () => res(g.result); });
    db.close();
    return all;
  });

  const summary = blueprints.map((b) => ({
    key: b.blueprintId ?? b.id,
    name: b.name,
    entities: b.entities ? Object.keys(b.entities).length : 0,
    updatedAt: b.updatedAt,
  }));
  console.log(JSON.stringify(summary, null, 1));
  fs.writeFileSync("out/cdp-blueprints.json", JSON.stringify(blueprints, null, 1), "utf8");
  console.log("完整蓝图已存 out/cdp-blueprints.json");
  await browser.close();
})().catch((e) => { console.error("FAIL:", e.message); process.exit(1); });
