# PRD: 平台内嵌官方蓝图码导入器（IndustrialPlanner Fork）

> 日期：2026-09-21 ｜ 状态：已批准执行（计划见 `PLATFORM-IMPORT-PLAN.md` + plans 目录计划文件）
> 执行范围：P0 环境验证 → P1 导入器核心+测试 → P2 API 客户端+编辑器入口 → P4 Python 对齐回归（P3 公网部署暂缓）

## 1. Introduction/Overview

将游戏《明日方舟：终末地》官方蓝图码解析结果 100% 复刻到本地部署的仿真平台（hsyhhssyy/IndustrialPlanner，本地副本 `vendor/IndustrialPlanner/`，v3 分支 @60ecc38，schema 6）。

现有外部 Python 转换器（`convert_v5.py`）的痛点：必须在平台之外重新实现平台全部语义（注册表切片、旋转映射、连通规则、配置默认值），平台更新即需手工追平，且已发生"双版本语义"验证事故（rot=90 陷阱）。

本功能在平台源码内实现内嵌导入器：`输入官方蓝图码 → 熵增 API 解析 → 官方蓝图导入器（直接调用平台注册表/旋转原语/拓扑编译器本尊）→ BlueprintDocument（schema 6）→ 编辑器立即可视/可仿真`。

## 2. Goals

- 平台内输入官方蓝图码，一步导入为可仿真的平台蓝图（无需外部转换器、无需手动粘贴 JSON）
- 7 份基准 fixture（bp_simple / bp_test / bp_user / 壤晶 / 武陵1-4）转换后拓扑编译 **error 级诊断 = 0**，仿真 150s 关键物品产出达阈值（复刻 sim-runner/reports 基线）
- 锚点回归：318 节点 + 559 interactiveParam 中心样本全过（verify_anchors.py 的 TS 移植）
- 自有代码与上游隔离：上游文件改动 ≤ 5 处、每处几行，保证 upstream merge 冲突面最小
- P4 阶段 TS 输出与 Python 修正版输出深度 diff 为空，Python 原型归档

## 3. User Stories

### US-001: P0 本地环境基线验证
**Description:** 作为开发者，我需要确认本地平台源码可安装、可测试、可运行，作为后续改动的基线。

**Acceptance Criteria:**
- [ ] `vendor/IndustrialPlanner/` 确认 v3 分支 @60ecc38，工作区干净；`git remote add upstream https://github.com/hsyhhssyy/IndustrialPlanner`（若未配置）
- [ ] `npm ci` 成功完成
- [ ] `npx vitest run --project normal` 全绿（记录基线通过数）
- [ ] `npm run dev` 启动成功，浏览器可打开编辑器界面
- [ ] 基线结果记录在 PR 描述或提交信息中

### US-002: 导入器基础模块（类型/ID 映射/锚点/旋转求解器）
**Description:** 作为开发者，我需要导入器的纯函数基础模块，支撑后续转换流水线。

**Acceptance Criteria:**
- [ ] 新建 `src/shared/official-blueprint-import/official-types.ts`：`OfficialBlueprintNode`/`OfficialBlueprintData`/`ConvertOptions`/`ConvertReport` 类型
- [ ] 新建 `official-id-map.ts`：`OFFICIAL_TO_PLATFORM_ID` 常量表（10 条别名，目标用 **v6 名**：`furnance_1_liquid`/`planter_1_liquid`）+ `resolveOfficialDefinitionId(templateId, coms)` 模式变体分流；未知 templateId 返回 null（不抛错）
- [ ] 新建 `official-anchor.ts`：`nodeOfficialRot`（rotation.y ?? direction.y fallback）、`nodeAnchor`（position ?? interactiveParam 回退）、`officialFootprintOrigin`（4 分支表）、`toPlatformPosition`（Z 镜像 y=(zSize−1)−z）、`expandPolyline`（逐格展开）
- [ ] 新建 `official-rotation.ts`：`solveDeviceRotation(def, officialRot, officialFacingEdges)` 主路径恒等 q=officialRot，校验用 `src/shared/geometry/port.ts` 的 `resolveRotatedPortGeometry`（**只准引 shared 版**）；不匹配枚举 q∈{0,90,180,270}；不唯一回退 q=r 并写 `rotationResolutions`；**代码中不得出现 v5 K 值表**
- [ ] 全部模块有单测（normal project），`npx tsc --noEmit` 零错

### US-003: 物流展开 + 端口接驳
**Description:** 作为开发者，我需要把官方物流折线展开为平台传送带/管道实体，并完成端口接驳（最高风险模块）。

**Acceptance Criteria:**
- [ ] 新建 `official-logistics.ts`：`classifyLogistics` 查表（dIn==dOut→straight rot=d；(dOut−dIn)%360==90→turn_cw rot=(dIn+180)%360；==270→turn_ccw rot=(dIn+270)%360）；`convertLogistics` 两遍法（多格段先/单格段后 `inferSingleCellDir` 邻接推断 + directionOut fallback `(90−dOut.y)%360`）；实体 ID `logistics-draft:{belt|pipe}:{x}:{y}`；`cellOwner` Map 支持带×管同格叠放
- [ ] 新建 `official-port-adaptation.ts`：`adaptLineEndpoints` 与 `convert_v5.py` 274-339 行**逐行同构**（facing 索引 / 首格遇 output、末格遇 input / swapLogi 改判 / adapted 防二次改写 / 一格多端口冲突写 warning 不静默）；端口几何统一走 `resolveRotatedPortGeometry` + `rotateGridEdge`
- [ ] 合成微场景单测：一格带贴设备端口朝向不符 → 期望改判 turn
- [ ] `npx tsc --noEmit` 零错

### US-004: 功能配置 + 拓扑自检 + 编排器
**Description:** 作为开发者，我需要设备功能配置生成、平台本尊拓扑自检、以及转换编排入口。

**Acceptance Criteria:**
- [ ] 上游改动 #1：`src/simulation/topology/compiler.ts:1701` `compilePhysicalConnections` 加 `export`（仅 1 个关键字）
- [ ] 上游改动 #2：`src/shared/storage/legacy-blueprint-import.ts:1016` `buildWarehouseSlotLink` 加 `export`
- [ ] 新建 `official-config.ts`：`expandPlacementDefaultsLocal`（[Self] 替换，契约同 placement-action.ts:465）+ `buildOfficialConfig`：base=placementDefaults 展开（自动覆盖 storager `warehouse_submit` 与 mix_pool `recipeChannelAutomaticModeEnabled:true`，**不手写这两条**）；unloader→slotLink（target slotId=selector.selectedItemId）+`ignoreStock`（infiniteSupply 可关）；admission→acceptRule+admissionRule（valveEnable 映射 itemId）；mix_pool→输出端口 acceptRule 按 comPos 61-66 selector 放开（固口 Solid/管口 Fluid，isPipe 从 portGroup 级取）+ `channelRecipes.ch1`；productIcon→平台真注册表配方匹配（mode 优先 `_<mode>` 或 tags）
- [ ] 单测：遍历全部 52 个实体定义，证明 placementDefaults 键 ∩ 官方推导键 = ∅
- [ ] 新建 `official-topology-check.ts`：`checkImportTopology` 构造最小 port 对象调 export 后的 `compilePhysicalConnections`；返回 `{ connectionCount, unconnectedPortWarnings }`
- [ ] 新建 `index.ts`：`convertOfficialBlueprint(json, opts) → { doc, report }`；经 `createBlueprintDocument` 工厂（blueprint-document.ts:46）落文档；initialGridPoint=实体包围盒中心取整；baseId 默认 `wuling_protocol_core`（含 hongs_bus 节点时 report 提示可选 valley4）
- [ ] `npx tsc --noEmit` 零错

### US-005: 锚点回归测试套件
**Description:** 作为开发者，我需要 verify_anchors.py 的 TS 移植，钉死坐标/锚点语义。

**Acceptance Criteria:**
- [ ] `src/tests/fixtures/official/` 拷入 7 份官方解析 JSON（bp_simple / bp_test / bp_user / bp_EF013Eou8uo47auUu0579 / bp_EF01I43ouo3OA979O5o08 / bp_EF0170iUeUi6855u2O0Ai / bp_EF010819a91uOi12iE179，来自 `workspace/blueprint-sim/data/`）
- [ ] `src/tests/simulation/official-import-anchors.test.ts`（**normal project**）：7 份 fixture 全量非物流节点——官方锚点→平台 position/占地与 fixture 内 `transform.interactiveParam.position` 中心互推一致（容差 0.01），318 节点 + 559 中心样本全过
- [ ] `npx vitest run --project normal official-import-anchors` 全绿

### US-006: 仿真验证测试套件
**Description:** 作为开发者，我需要端到端仿真断言，证明转换结果在平台真实引擎中可运行且产出正确。

**Acceptance Criteria:**
- [ ] `src/tests/simulation/blueprint/official-import-verify.test.ts`（**blueprint project 120s**）：每份 fixture `convertOfficialBlueprint` → 拓扑 `diagnostics` 按 `severity==="error"` 过滤计数 = 0（**注意无 topologyDiagnostics 名称**）→ `runBlueprintSimulation({maxDurationSeconds: 150})` → 断言 `warehouseStats.items[item].producedPerMinute` 阈值：simple `item_iron_nugget ≥ 1`；武陵系 `item_copper_nugget > 0`；wuling_all 追加 `item_equip_script_4_3 ≥ 1` + storager 提交生效（warehouseCount 增长）
- [ ] 连接数相等断言：TS `topologyCheck.connectionCount` 与 Python 基线逐一相等（bp_test 140、bp_user 115、武陵1-4：357/80/451/325）
- [ ] wuling_all（~1309 实体）若 120s 墙钟超时 → 移入 `src/tests/simulation/blueprint-slow/official-import-wuling-all.test.ts`（1800s project）
- [ ] engineKind 用默认 legacy（注释说明不矩阵化原因）
- [ ] `npx vitest run --project blueprint official-import-verify` 7 份全绿

### US-007: 熵增 API 客户端 + 缓存
**Description:** 作为用户，我希望输入蓝图码即可获取官方解析 JSON，无需手动导出。

**Acceptance Criteria:**
- [ ] 上游改动 #3：`vite.config.ts` server 段新增 `proxy: { "/entropy-api": { target: "https://end-api.shallow.ink", changeOrigin: true, rewrite: p => p.replace(/^\/entropy-api/, "") } }`
- [ ] 新建 `src/shared/endfield/entropy-api-types.ts` + `entropy-api.ts`：`createEntropyClient()` → `fetchBlueprintByCode(code)`；匿名 token（fingerprint=crypto.randomUUID()，localStorage key `endfield.anonFingerprint`；token 内存缓存 2h 提前 5min 重建）；GET `/api/blueprint/get?code=…` 带 `X-Anonymous-Token`；统一走 `/entropy-api` 前缀
- [ ] 新建 `src/shared/endfield/entropy-cache.ts`：蓝图码→JSON localStorage 缓存（key `endfield.bp.<code>`，LRU 50 条，单条 4MB 守卫）
- [ ] 单测覆盖 token 重建/缓存命中（normal project，mock fetch）
- [ ] `npx tsc --noEmit` 零错

### US-008: 编辑器导入入口
**Description:** 作为用户，我希望在蓝图面板点"从蓝图码导入"，粘贴码后看到转换报告，确认后入库并立即可仿真。

**Acceptance Criteria:**
- [ ] 新建 `src/app/shell/panels/official-import-dialog.tsx`：自包含 modal（多码输入框支持空白/逗号/换行分隔 → 逐码 fetch+convert → ConvertReport 视图：实体/物流/slotLinks 计数、skipped、warnings、rotationResolutions、topologyCheck 摘要 → 确认后 `createImportedBlueprintDocument` + `appHost.saveBlueprintDialog.openImported` 入库）；含"粘贴官方 JSON"降级路径（API 失效时直连 convert）
- [ ] 上游改动 #4：`src/app/shell/panels/blueprint-panel.tsx` 新增第三个操作按钮（照抄 :257-271 按钮定义模式）+ 一行 modal 条件渲染（~15 行）
- [ ] 上游改动 #5：`src/shared/i18n/zh-cn/ui.ts` + `en-us/ui.ts` 新增 ~10 个 key
- [ ] **人工验收**：`npm run dev` → 输入武陵3 码 `EF0170iUeUi6855u2O0Ai` → 一步导入 → 编辑器可见 → 仿真产出铜锭（item_copper_nugget）
- [ ] `npx vitest run --project normal` 全绿（面板改动无回归）
- [ ] 在浏览器中验证（dev-browser / playwright 截图）

### US-009: P4 Python 对齐回归 + 归档
**Description:** 作为开发者，我需要证明 TS 导入器与 Python 修正版输出一致，然后归档 Python 原型。

**Acceptance Criteria:**
- [ ] Python 原型修正为 v6 语义：emit `schemaVersion=6` + `regions:[]`、liquid 变体改 v6 名、旋转恒等 q=r（ROT_OFFSET_V5 删除留注释参照）
- [ ] 新建 workspace 级 `compare_ts_python.py`：同 fixture 双端转换 → 归一化（剥 blueprintId/createdAt/updatedAt）→ entities/entityOrder/slotLinks 深度 diff
- [ ] 7 份 fixture diff 报告全部为空
- [ ] 归档 `convert_v5.py` / `registry_table.py` / `recipes.json`（移至 `archive/` 或标记 deprecated）；`RESEARCH.md` 保留
- [ ] diff 为空前不得归档

## 4. Functional Requirements

- FR-1: 导入器必须只生成 **schema 6** 蓝图文档，经 `createBlueprintDocument` 工厂构造（自动补 regions/blueprintId/时间戳）
- FR-2: 旋转映射主路径为恒等 q=officialRot（v6 注册表 rotation=0 = 官方默认朝向）；端口边集合校验失败时枚举求解；不可解时回退 q=r 并在报告中显式警告（禁止静默摆错）
- FR-3: 设备 config 必须先做 placementDefaults 等价展开（含 [Self] 占位符替换），再叠加官方数据推导的配置；官方推导键与 defaults 键不得冲突（有单测保证）
- FR-4: 拓扑自检必须调用平台本尊 `compilePhysicalConnections`（re-export），禁止重写连通规则
- FR-5: 旋转数学必须引用 `src/shared/geometry/port.ts`（resolveRotatedPortGeometry/rotateLocalPortCell/rotateGridEdge），禁止引用 editor/simulation/renderer 内的本地副本
- FR-6: 物流展开必须保持两遍法顺序（多格段先、单格段后），带×管允许同格叠放
- FR-7: 端口接驳冲突必须写入 ConvertReport.warnings，禁止静默跳过
- FR-8: 未知 templateId 计入 report.skipped，转换不中断
- FR-9: API 客户端必须统一走 `/entropy-api` 相对前缀（dev 走 vite proxy，生产走 Functions 代理），token 2h 过期自动重建
- FR-10: 上游文件改动仅限 5 处（2 个 export + vite proxy + 面板按钮 + i18n key），每处最小化
- FR-11: 所有新代码在 `vendor/IndustrialPlanner/` 内；不改 `subprojects/`（只读）
- FR-12: 配方匹配必须查平台真注册表 recipeDefinitions（outputs 包含匹配 + mode 优先），禁止搬 Python recipes.json 切片

## 5. Non-Goals (Out of Scope)

- **P3 公网部署**（fork 推送 / EdgeOne Pages / Functions 代理）——本轮暂缓，本地部署为验收边界
- schema 5 输出支持（v5 K 值表不移植；线上 v1.5.0 兼容不在范围内）
- 3D 高度层还原（官方管道 y=3 高架层丢弃，与 Python 原型一致）
- 游戏宽容性结构的 100% 表达（同边多端口平行带擦过、一格带贴双端口）——转换为警告而非强行适配
- water_pump_1 / water_purifier_node 的特殊处理（样本蓝图未出现，遇时按平台语义处理）
- UI 组件自动化测试（仓库无组件测试先例；P2 用人工验收 + 截图）
- Dense 引擎适配（测试用默认 legacy 引擎）

## 6. Technical Considerations

- **技术栈**：TypeScript 严格模式 + Vite ^8 + Vitest ^4 + React 19 + MobX + PixiJS（遵循仓库既有风格）
- **关键源码锚点**（已亲验）：
  - 注册表：`src/registry/entity-definition.ts:1003`（52 实体）；端口字段 `localCellX/localCellY`，isPipe/direction 在 portGroup 级
  - 旋转原语：`src/shared/geometry/port.ts:26/50/70`
  - 拓扑编译：`src/simulation/topology/compiler.ts:117`（compileSimulationTopology）/`:1701`（compilePhysicalConnections 私有→export）；诊断 `SimulationCompileDiagnostic[]`（contracts/types.ts:99）
  - 蓝图文档：`src/domain/document/blueprint-document.ts:15`（BlueprintDocument）/`:46`（createBlueprintDocument）；BLUEPRINT_SCHEMA_VERSION=6
  - legacy 导入器：`src/shared/storage/legacy-blueprint-import.ts:163`/`:1016`
  - 导入面板：`src/app/shell/panels/blueprint-panel.tsx:257-298`
  - placementDefaults 合并参照：`src/editor/actions/placement-action.ts:96-103`/`:465`
  - 仿真测试基建：`src/tests/simulation/blueprint-runner.ts:31` runBlueprintSimulation
  - 产出统计：`RuntimeTickSnapshot.warehouseStats.items[item].producedPerMinute`
  - 已覆盖默认：storager placementDefaults channelRecipes.warehouse_submit（entity-definition.ts:1112）；mix_pool placementDefaults recipeChannelAutomaticModeEnabled:true（:3236-3240）
- **Python 原型资产**（移植源）：`convert_v5.py`（497 行 5 步流水线）、`registry_table.py`（31 实体切片）、`data/`（12 份官方蓝图样本）、`sim-runner/reports/`（7 份仿真基线报告含 expectResults 阈值）、`verify_anchors.py`（318/318 基线）
- **风险最高两处**：端口接驳 adapt_line_endpoints 移植（逐行同构 + 连接数相等断言 + 合成微场景单测）；双版本旋转语义（结构性消除：只产 schema 6 + 恒等主路径 + 求解器安全网 + 三重回归兜底）

## 7. Success Metrics

- `npx vitest run --project normal official-import-anchors`：318 节点 + 559 中心样本全过
- `npx vitest run --project blueprint official-import-verify`：7 份 fixture error 诊断 = 0 且关键产出达阈值
- 连接数与 Python 基线逐一相等（140/115/357/80/451/325）
- `npm run dev` 输入武陵3 码一步导入并仿真出铜锭
- P4：7 份 fixture TS vs Python 修正版 diff 为空
- `npx tsc --noEmit` 零错；`npx vitest run --project normal` 无回归

## 8. Open Questions

- P3 公网部署的 fork 目标 org 与 EdgeOne Functions 细节（本轮暂缓，启动 P3 时再定）
- wuling_all 用例最终落在 blueprint 还是 blueprint-slow project（实现时按实际墙钟决定）
- 含 hongs_bus 蓝图是否需要在导入对话框提供 baseId 选择器（本轮仅在 report 中提示）
