# 平台内嵌蓝图码导入方案（IndustrialPlanner Fork）

> 目标：在仿真平台（hsyhhssyy/IndustrialPlanner）源码内实现"输入官方蓝图码 → 直接得到可仿真的平台蓝图"，替代外部 Python 转换器（convert_v5.py）。
> 状态：方案设计 ｜ 日期：2026-09-21
> 追加（2026-10-05）：**显式边表（logisticsEdges）** 已落地——协议级证据（`Moli13337/Endfield-proto`：
> `CSD_BLUE_PRINT_NODE`/`CSD_BLUE_PRINT_TRANSFORM` 无连接字段；游戏运行时虽有
> `CSD_FACTORY_OP_ADD_CONNECTION{fromComId,toComId}` 组件边，但保存蓝图时被丢弃）
> 证明连接只能几何重建。边表把导入时 `checkImportTopology` 已算出的连接冻结为
> 可 diff/审查/人工覆盖的 JSON 工件（sidecar `bp_*.edges.json` + 文档内嵌
> `logisticsEdges`），仿真编译在场即权威（`simulation/topology/explicit-connections.ts`
> 的 `reconcileExplicitConnections`：几何先行作顺序基准，缺边=不连，manual 边经平台
> 约束校验追加，失配>50% 整体回退）。多端口差异实证见 REPLICATION-DIFFS.md D9。

## 1. 为什么从"外部转换器"转向"平台内嵌"

外部 Python 转换器的根本痛点：它必须在平台之外**重新实现平台的全部语义**——注册表切片（registry_table.py）、旋转/迁移双版本映射、连通规则、功能配置默认值。平台每更新一次注册表，外部副本就要手工追平；而我们已经在"双版本语义"上栽过一次（rot=90 验证陷阱，见 RESEARCH.md）。

内嵌方案让转换逻辑直接调用平台自己的原语：

| 维度 | 外部 Python 转换器 | 平台内嵌导入器 |
|---|---|---|
| 注册表 | 手工切片，需追平 | **直接用 `entity-definition.ts` 本尊** |
| 旋转/迁移 | 硬编码 K 值表，双版本映射易错 | 用平台 `rotateGridEdge`/`rotateLocalPortCell` 原语 + 迁移链自动执行 |
| 连通校验 | Python 重写 topology compiler 规则 | **直接跑 `compilePhysicalConnections`** |
| 功能配置 | 手工抄写 placementDefaults（已漏过 storager/mix_pool） | 调平台放置默认合并函数，与编辑器行为天然一致 |
| 验证 | matplotlib 渲染"看起来像" | **vitest 跑真实仿真引擎断言产出** |
| 用户体验 | 导出 JSON → 手动导入 | 输入蓝图码一步到位 |

Python 原型不退场：它作为**语义参照与回归基准**（TS 版输出应与 Python 修正版 diff 为空），且 RESEARCH.md 的实证结论全部保留。

## 2. 总体架构

```
蓝图码 ──▶ [A] 熵增 API 客户端 ──▶ 官方解析 JSON
                                      │
                                      ▼
                          [B] 官方蓝图导入器（核心）
                          official-blueprint-import.ts
                          锚点/z翻转/旋转镜像/物流展开/ID别名/config
                                      │
                                      ▼
                          BlueprintDocument（平台原生 schema）
                                      │
              ┌───────────────────────┼───────────────────────┐
              ▼                       ▼                       ▼
       [C] 编辑器入口           [D] vitest 断言套件       转换报告 UI
       "从蓝图码导入"          bphub-verify.test.ts     （跳过/警告/配置清单）
```

## 3. 模块设计

### [A] 熵增 API 客户端 `src/shared/endfield/entropy-api.ts`

- `POST /api/v1/auth/anonymous-token`（fingerprint = UUID，localStorage 持久化；token 2h，过期自动重建）
- `GET /api/blueprint/get?code=<码>` → 官方解析 JSON（`data.data.bluePrintData`）
- **CORS**：开发期用 `vite.config.ts` 的 `server.proxy` 转发 `/entropy-api` → `https://end-api.shallow.ink`；生产期在自有部署上加一层 Functions 代理（见 §6 部署）
- 蓝图码查询结果 IndexedDB 缓存（同一码内容不可变）

### [B] 官方蓝图导入器 `src/shared/official-blueprint-import.ts`（核心，~600 行）

签名：`convertOfficialBlueprint(json: OfficialBlueprintJson, opts): { doc: BlueprintDocument; report: ConvertReport }`

**移植自 Python 原型的实证数据**（registry_table.py / RESEARCH.md）：

1. **锚点与占地**：官方锚点随旋转变化表（rot=0→minX,minZ；90→minX,maxZ；180→maxX,maxZ；270→maxX,minZ）+ footprint 尺寸表（28 种实体，559 节点 interactiveParam 回归全过）
2. **坐标镜像**：`y = (zSize−1) − z`（cell 级）
3. **旋转映射（本方案最大的收益点）——不再硬编码 K 值，改为注册表原语求解**：
   - 对每台设备，取注册表端口定义（localCell/edge/direction/isPipe），枚举 q∈{0,90,180,270}，用平台 `rotateLocalPortCell`/`rotateGridEdge` 计算"平台 rot=q 时端口边集合（换算到官方坐标）"，与官方 rot=r 的实际端口边（由官方邻接数据/解包朝向表确定）匹配
   - 匹配唯一 → 采用；匹配不到 → 回退 Python 版推导的逐类公式表：
     - machine 类 `(360−r)%360`；unloader/loader/splitter `(180−r)%360`；converger/connector `(360−r)%360`；admission `(270−r)%360`
   - **该求解器同时是诊断工具**：新设备接入时自动报告"映射不可解"，而不是静默摆错
4. **物流展开**：points 折线逐格展开（已实证 points 顺序=流向）；turn 镜像查表：
   - 官方 `(dout−din)%360==90`（cw）→ 平台 `turn_ccw`，`p=(270−din)%360`
   - 官方 `==270`（ccw）→ 平台 `turn_cw`，`p=(180−din)%360`
   - straight：`p=(360−d)%360`
5. **ID 别名**：直接 import 仓库已有的 `device-building-aliases.mjs`（`RAW_BUILDING_ID_BY_PROJECT_ID`），外加模式变体分流（furnance_1+liquid→liquid_furnance_1；planter_1+liquid→hydro_planter_1）
6. **功能配置**：
   - unloader → warehouse slotLink（复用 legacy 导入器的 `buildWarehouseSlotLink` 逻辑）+ `ignoreStock`（可开关）
   - admission → `acceptRule` + `admissionRule`（阀门 selectedItemId/valveEnable）
   - **storager → `channelRecipes.warehouse_submit = "r_warehouse_submit"`**（当前 Python 版缺失，导致不提交仓库）
   - **mix_pool → 从 coms selector（comPos 61..66 = 输出端口选择器）反推配方写 `channelRecipes.ch1`，并写 `recipeChannelAutomaticModeEnabled = true`**（当前缺失导致反应池不生产）
   - 其余设备走平台 placementDefaults 合并（与编辑器放置行为一致）

   **游戏隐式默认行为 → 平台显式配置同步表**（2026-09-21 全量排查，来源：注册表 placementDefaults/createPort 默认值/compiler 回退逻辑）：

   | 设备 | 游戏内隐式默认 | 平台导入缺省 | 同步动作 |
   |---|---|---|---|
   | storager_1 协议储存箱 | 无线提交开启（22/22 蓝图 coms 全空证实） | channelRecipes 空 → 不提交 | **写死** `channelRecipes.warehouse_submit="r_warehouse_submit"` |
   | mix_pool_1/2 反应池 | 按输入物品自动反应 | automaticMode 缺省 false → manualRecipeOnly 锁死 | **写死** `recipeChannelAutomaticModeEnabled=true`（automaticModeConfigKey 全注册表仅这两台使用，已核实） |
   | mix_pool_1/2 输出端口 | 产物自由输出 | acceptRule 默认 `{kind:"none"}` → 不出货（全注册表仅 mix_pool 输出端口默认 none，已核实） | 按 selector 物品放开：固口→Solid 域、管口→Fluid 域 |
   | mix_pool_1/2 配方快照 | 拍蓝图时已选好配方（coms selector comPos 61-66 记录） | channelRecipes 空 | 增强项：非空 selector 物品集合→outputs 覆盖匹配，写 `channelRecipes.ch1/ch2`（automaticMode 下作固化/兜底） |
   | mix_pool_2 堵塞自动清除 | 开启 | `config[enabledConfigKey] ?? enabledByDefault(true)`（compiler.ts:1504 证实定义级回退） | **无需写** |
   | 普通生产机（furnance/grinder/cmpt/shaper/tools_asm/thickener/winder/seedcol/planter/hydro_planter/liquid_furnance/liquid_cleaner/liquid_purifier/power_sta） | 配方为显式选择（productIcon 记录） | channelRecipes 空 | 已覆盖：productIcon→outputs 匹配写 `channelRecipes.default` |
   | unloader_1 取货口 | 从总线取选中物品 | 无链接 → 不取货 | 已覆盖：warehouse slotLink + `ignoreStock`（可开关） |
   | loader_1 存货口 | 入仓 | WarehouseSink 为定义 tag 自带 | **无需写** |
   | log/pipe_admission 阀门 | 阀门物品/开关 | 无规则 → 全放行 | 已覆盖：acceptRule+admissionRule（valveEnable 映射 itemId null/具体值） |
   | splitter/converger/connector | 优先级默认 5 | portPriorityGroups 定义级默认 | **无需写** |
   | power_diffuser 电扩 | 无线供电范围 12 | powerRange 定义级 | **无需写** |
   | water_pump_1 抽水泵（样本蓝图未出现） | — | 2026-08-19 起：必须选配方才运行（真实配方设备，注册表注释证实） | 遇时按 productIcon 配 `channelRecipes.default`；无则不运行（属平台语义，非转换错误） |
   | water_purifier_node 净水节点（样本蓝图未出现） | 输出模式 | placementDefaults 有 OUTPUT_MODE + MANUAL_PER_MINUTE 默认 | 遇时写 placementDefaults 同款默认值 |
   | log_hongs_bus/source 总线 | 空壳展示 | 无配置 | **无需写** |
   | rotateToSnapOnBuilding（unloader/udpipe 贴线自动旋转） | — | 编辑器单设备放置行为，**蓝图放置路径不触发**（rotate-to-snap-on-building.ts 仅被 selection-actions.ts 引用，已核实） | 无影响，无需处理 |

   原则：**凡平台 placementDefaults/定义级默认能覆盖的，转换器一律不写；凡导入缺省会改变设备行为的，转换器必须显式写死或从官方数据反推。**
7. **initialGridPoint** = 实体包围盒中心；`baseId` 按蓝图特征选择（含 hongs_bus → 可提示用户选 valley4/wuling；默认 wuling_protocol_core）

**ConvertReport**：转换清单（实体/物流节/slotLinks 计数）、跳过项、端口接驳警告、拓扑自检结果（直接调 `compilePhysicalConnections` 而非重写）。

### [C] 编辑器入口

蓝图导入对话框新增 **"从蓝图码导入"** tab：
- 输入框（支持一次多码）→ fetch → convert → 显示 ConvertReport → 确认入库
- 导入后立即可在编辑器查看/仿真；可选"导入并立即仿真 N 秒"显示产出摘要

### [D] vitest 断言套件 `src/tests/simulation/official-import-verify.test.ts`

常驻回归（之前会话的 bphub-verify 模式，reports/ 格式保留）：
- fixtures：`src/tests/fixtures/official/*.json`（bp_simple/bp_test/bp_user/壤晶/武陵1-4 官方解析 JSON）
- 每份：转换 → `topologyDiagnostics == 0` → 仿真 150s → 断言关键物品 `producedPerMinute > 0`
  - simple：item_iron_nugget > 0
  - longpao / rangjing / wuling_all：item_copper_nugget > 0
  - wuling_all 追加：item_equip_script_4_3 > 0、storager 提交生效（warehouseCount 增长）
- 锚点回归：fixtures 全量节点 interactiveParam 中心一致性（559 样本）

## 4. 分阶段实施

| 阶段 | 内容 | 验收 |
|---|---|---|
| P1 | [B] 导入器核心（锚点/镜像/旋转求解器/物流/ID/config）+ [D] fixtures 与断言 | 7 份 fixture 全部 `topologyDiagnostics==0` 且关键产出 > 0 |
| P2 | [A] API 客户端 + CORS 代理 + [C] 编辑器入口 | 平台内输入蓝图码一步导入武陵3，仿真产出铜锭 |
| P3 | 部署自有实例（fork + 静态托管 + Functions 代理） | 公网可访问，用户无需本地环境 |
| P4 | 与 Python 版回归对齐（TS 输出 vs Python 修正版 diff 为空）后归档 Python 版 | diff 报告为空 |

## 5. 与现有资产的关系

- `convert_v5.py` / `registry_table.py` / `recipes.json`：语义参照，P4 后归档；其中的实证数据（尺寸表/锚点表/旋转公式/配方切片）逐条翻译为 TS 常量
- `RESEARCH.md`：全部结论保留为导入器的设计依据（文档随 fork 走）
- `sim-runner/reports/`：断言输出格式沿用
- `fetch_blueprint.py`：逻辑移植为 [A] 模块

## 6. 部署方案

- fork `hsyhhssyy/IndustrialPlanner` 到自有 org；自有改动集中在 `src/shared/official-*`、`src/shared/endfield/*`、导入对话框一处 tab、`src/tests/official-*`——**隔离改动面，降低上游 merge 冲突**
- 静态构建（`vite build`）部署 EdgeOne Pages（vendor 已有 `edgeone.json` 先例）
- CORS 代理：EdgeOne Functions（或 Cloudflare Workers）一条 `/entropy-api/* → https://end-api.shallow.ink/*` 转发规则
- 上游同步：`git remote upstream` 定期 merge；schema 迁移链自动处理旧蓝图

## 7. 风险与对策

| 风险 | 对策 |
|---|---|
| 上游大改注册表 | 旋转求解器用注册表原语，天然跟随；fixtures 断言兜底报警 |
| 熵增 API 不稳定/失效 | 查询结果 IndexedDB 缓存；保留"粘贴官方 JSON 导入"降级路径 |
| CORS | 自有部署 Functions 代理；开发期 vite proxy |
| 官方蓝图结构变更（游戏更新） | ConvertReport 显式报告未知 templateId；锚点回归测试第一时间暴露 |

## 8. 工作量估算

转换核心 ~600 行 TS + API 客户端 ~100 行 + 编辑器入口 ~150 行 + 测试 ~200 行 ≈ **2-3 个工作日当量**（Python 原型与全部实证数据已就绪，无研究性开销）。
