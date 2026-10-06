# blueprint-sim —— 终末地蓝图码 → 仿真平台

官方蓝图码/解析 JSON → [endfield.amiyabot.com](https://endfield.amiyabot.com)（IndustrialPlanner）可仿真的蓝图。

## 主路径：平台内嵌导入器（TS，当前推荐）

平台 fork 内嵌"从蓝图码导入"：蓝图面板 → 从蓝图码导入 → 输入码 → 转换报告 → 确认入库，一步到位。

- 导入器：`vendor/IndustrialPlanner/src/shared/official-blueprint-import/`（9 模块）
- API 客户端：`vendor/IndustrialPlanner/src/shared/endfield/`（熵增 API + localStorage LRU 缓存）
- 编辑器入口：`src/app/shell/panels/official-import-dialog.tsx`（蓝图面板第三个按钮）
- CLI 转换：`npx tsx --tsconfig tsconfig.app.json src/scripts/dump-official-blueprint-conversion.ts <in.json> <out.json>`

### 测试（vendor/IndustrialPlanner 下）

```bash
npx vitest run --project normal official-blueprint-import official-import-anchors official-edge-table official-single-cell-direction topology-explicit-connections  # 单测 + 锚点回归 + 边表 + 单格规则
npx vitest run --project blueprint official-import-verify official-import-explicit-edges   # 小蓝图端到端（转换+仿真产出+边表编译）
npx vitest run --project blueprint-slow official-import-wuling                      # 武陵 1/3/4 大蓝图端到端
```

## 连接解析规则（2026-10-05 定案）

蓝图码对连接是**自描述完备的**（游戏拍蓝图不需要人工修边），导入器按以下规则解析：

1. **多格段**：折线点序 = 流向（游戏截图箭头逐格实证）；directionIn/Out 为脏数据忽略
2. **单格段**：**官方声明直连采用**（dIn=dOut 直行 / dIn≠dOut 转弯），无声明才邻接推断
3. **设备对接**：position + direction + 端口表（多端口设备沿整边每格一个端口，游戏建筑表实证，D9）
4. **断头审计**：声明出向无对接的格子列于转换报告 `directionDivergences`（不改写声明，不静默）

证据链见 RESEARCH.md §4；差异清单见 REPLICATION-DIFFS.md（D9 多端口、D10 单格规则）。

## 蓝图边表（显式连接，`bp_<code>.edges.json`）

蓝图协议不含连接字段（游戏保存蓝图时丢弃运行时连接边，拍蓝图按几何重建），
平台导入器的几何推断与游戏同款。边表把推断结果**冻结为可审查、可手工覆盖的
JSON 工件**：导入时由 `checkImportTopology` 生成（与运行时编译同源同码），
内嵌进蓝图文档 `logisticsEdges`，仿真编译时**边表在场即权威**（不再逐次重猜）。

```bash
# 导出边表（审查/手工修正的起点）
npx tsx --tsconfig tsconfig.app.json src/scripts/dump-official-blueprint-conversion.ts data/bp_x.json out/doc_x.json --edges data/bp_x.edges.json

# 手工修正：改端点坐标并标 "provenance": "manual"；或把推断边 id 加入 "disabled"
# 校验：重新转换 diff（manual 边只校验端口可解析性，不报几何不一致）
npx tsx --tsconfig tsconfig.app.json src/scripts/dump-official-blueprint-conversion.ts --check-edges data/bp_x.json data/bp_x.edges.json

# 合并入文档：仿真按修正后的边表连接
npx tsx --tsconfig tsconfig.app.json src/scripts/dump-official-blueprint-conversion.ts data/bp_x.json out/doc_x.json --merge-edges data/bp_x.edges.json
```

**固有限制（必读）**：
- 边表**不创造信息**——推断错误（如单格段 fallback 用不可信的 directionOut）会原样写入，靠人工修正兜底；
- 平台语义约束仍在：显式边不能表达"双非物流设备直连"、不能跨 belt/pipe 类型、不能隔空连接（编译期 error 诊断，不静默成功）；
- 编辑器手工改动文档后实体 ID 漂移，边表失配超 50% 时**整体回退几何推断**并报 `stale-explicit-edge-table`；
- `sourceHash` 与源蓝图失配时 `--check-edges` 会警告边表可能过期。

## 回归基准：Python 原型（已归档 v6 修正版）

`archive/python-converter/`（convert_v5.py / registry_table.py / recipes.json / verify_anchors.py）——
v6 语义修正版（schema 6 + 恒等旋转 + or-bug 修复），仅供回归参照，不再作为主转换路径。

```bash
python compare_ts_python.py          # P4 对齐回归：TS vs Python 8 份 fixture 深度 diff（应为空）
cd archive/python-converter && python verify_anchors.py   # 锚点回归 559/559
```

## 文件

| 文件 | 作用 |
|---|---|
| `PLATFORM-IMPORT-PLAN.md` | 内嵌方案设计文档 |
| `tasks/prd-official-blueprint-import.md` | 本次实施的 PRD（9 个用户故事） |
| `RESEARCH.md` | 坐标/旋转/连通语义实证依据（改动前必读） |
| `data/` | 官方蓝图解析 JSON 样本（12 份）+ 对照图 |
| `sim-runner/reports/` | 早期仿真基线报告（产出阈值参考） |
| `fetch_blueprint.py` | 熵增 API 取蓝图（Python 版，其逻辑已移植为 TS `entropy-api.ts`） |
| `compare_ts_python.py` | TS vs Python 深度 diff 回归工具 |
| `verify-import-ui.cjs` | 浏览器端导入流程验收脚本（需 dev server 运行中） |

## 已知平台语义差异（非转换错误）

1. **准入口/管准入口不主动从仓库取货**：官方蓝图依赖游戏隐式供应（bp_simple 的铁矿、武陵 1/3 的酸）。
   平台需 unloader（取货口）显式供应。转换已忠实复刻布局；无上游供应的准入口不产出属平台语义。
2. **液体隐式供应无对应**：游戏内基地液体直供，平台需暗管取液口（udpipe_unloader）显式配置。
3. 游戏宽容性结构（一格带贴双端口、同边多端口平行带擦过）平台无法表达 → 转换报告显式警告。
