# 蓝图码 → 仿真平台 转换语义研究（已钉死，勿再试错）

> 来源：仿真平台开源仓库 `hsyhhssyy/IndustrialPlanner`（commit 106657fa，endfield.amiyabot.com 的代码）+ 三份官方蓝图解析数据实证（96 节点锚点回归全过）+ 真实游戏截图对照。
> 平台线上版本 v1.5.0 = 蓝图 **schema 5**；仓库 main = schema 6（未发布）。

## 1. 坐标系

| | 官方（游戏/AKEData） | 平台（IndustrialPlanner） |
|---|---|---|
| 轴 | x 东，z 南（y 为高度层） | x 东，**y 向下**（= 官方 z 翻转） |
| 旋转 | rotation.y / direction.y，顺时针 0/90/180/270 | rotation，顺时针 0/90/180/270 |
| 设备锚点 | **随旋转的角落格** | **旋转后 footprint 左上角（min-x/min-y）** |
| 物流 | points 折线（含转折点）+ directionIn/Out | 逐格 1×1 实体（straight/turn_cw/turn_ccw） |

- 镜像公式：`y_platform = (zSize - 1) - z_official`（cell 级）
- 官方锚点表（官方 rot → 锚点在占地中的位置）：
  - rot=0 → (minX, minZ)；rot=90 → (minX, maxZ)；rot=180 → (maxX, maxZ)；rot=270 → (maxX, minZ)
- 官方 footprint 旋转换宽高（与平台 `getRotatedGridFootprint` 同构：rot 90/270 互换 w/h）
- 官方部分节点 `rotation` 为 null，朝向在 `transform.direction.y`（务必 fallback）
- 官方管道 points 的 y=3（高架层）、传送带 y=0 → 2D 转换丢弃高度，带×管可同格叠放

## 2. 旋转映射（schema 5 输出专用）

平台注册表 v6 语义：rotation=0 = 官方默认朝向（AKEData 1.5.3 校准）。schema 5→6 迁移会补偿：
- 37 台机器（furnance_1/storager_1/grinder_1/cmpt_mc_1/shaper_1/tools_asm_mc_1/power_sta_1/liquid_cleaner_1/liquid_furnance_1 等）：迁移 +180
- log_admission/pipe_admission：迁移 +270
- 其余（带/管节、splitter/converger/connector、unloader/loader、power_diffuser、总线）：不动

因此生成 schema 5 文档时：`rot_v5 = (rot_官方 + offset) % 360`，offset ∈ {machine:180, admission:90, identity:0}。
**红利**：v5 线上直接用 ✓；平台升 v6 后导入自动补偿，恰好还原官方朝向 ✓。一份输出通吃。

## 3. 物流节查表（d = 平台流向角 0=E/90=S/180=W/270=N）

- d_in == d_out → `{kind}_straight_1x1`，rot = d
- (d_out − d_in) % 360 == 90 → `{kind}_turn_cw_1x1`，rot = (d_in + 180) % 360
- (d_out − d_in) % 360 == 270 → `{kind}_turn_ccw_1x1`，rot = (d_in + 270) % 360

注册表端口基准（rot=0）：straight 进W出E；turn_cw 进E出N；turn_ccw 进N出E。
（`entity-definition.ts` 里 turn 的头注释 "W→S / W→N" 已过期，以代码端口为准。）

## 4. 官方 directionIn/Out 语义定案（2026-10-05 修订）

**旧结论（已废止）**："directionIn/Out 与几何流向脱钩不可信，仅单格段可作 fallback，邻接图优先"。

**新定案**：
- **多格段**：折线点序 = 流向（游戏截图箭头逐格实证）；directionIn/Out 脱钩为脏数据，忽略。
- **单格段**：**官方声明直连采用**——dIn=dOut → straight；dIn≠dOut → turn（平台角 = (90 − y) % 360，映射经直行/转弯双例实证）。无声明字段才回退邻接推断。

**证据链**：
1. IL2CPP dump（`Gameplay.Beyond.dll.cs`）：蓝图传送带节点落地为
   `BlueprintConveyorEntry{ spatial: ConveyorSpatialInfo{ startFace, GridPath{ startPoint, segments(face,length) } }, extraInfo: ConveyorExtraInfo{ portIn/portOut(position, direction, isFluid) } }`——
   游戏把节点解析为**带显式逐段 face 与声明端口的连接记录**，不是逐格启发式。
2. 解密 Lua `BlueprintPreview._GetConveyorSegmentInfos`：预览拐角按 startFace/endFace 渲染（`corner1/corner2`），证明官方 directionIn/Out 直接决定单格形状。
3. D.I.G.E. 蓝图码生成器：直行写 dIn=dOut、转弯写不同值，其码游戏内可用 → 游戏采信声明。
4. 游戏截图（EF013Eo0i2O06aU0579）：多格段箭头与折线点序逐格吻合；单格带 (90−y)%360 映射吻合。
5. 单格段全量统计（13 蓝图 180 格）：dIn==dOut 172 格（直行声明），dIn≠dOut 8 格（转弯声明）。

**连通审计**：忠实采用声明后，声明出向无对接的格子写入转换报告 `directionDivergences`（不改写声明）——判定为原蓝图断头/装饰带或平台无法表达的宽容结构。

## 5. 平台连通规则（topology compiler 源码级）

两端口连通 ⟺ ① isPipe 相同 ② 不同实体 ③ source.outside格==target.inside格 且 source.inside格==target.outside格（格相邻+端口边互对）④ **至少一端是物流族**（机器↔机器紧贴不连通）。

推论：官方蓝图利用游戏宽容性的两种结构在平台无法 100% 表达：
- 一台设备的多个同边端口被多条平行带"沿边擦过"（只接驳线首/末格的 turn，中间格保留报告）
- 一格带同时贴两台设备的端口（1×1 只能选一个朝向，报告冲突）
→ 转换器对这两种情况输出警告而非静默失败。

## 6. ID 与配置映射

官方 templateId → 平台 definitionId（别名表源：仓库 `device-building-aliases.mjs`）：

| 官方 | 平台 | 备注 |
|---|---|---|
| component_mc_1 | cmpt_mc_1 | |
| tools_assebling_mc_1 | tools_asm_mc_1 | 6×4 |
| power_station_1 | power_sta_1 | |
| log_conditioner | **log_admission** | 物品准入口（不是跳过！） |
| log_pipe_conditioner | **pipe_admission** | 管道准入口（不是占位直管！） |
| power_diffuser_2 | power_diffuser_1 | 降级：布局一致，供电范围 12 不变 |
| log_pipe_splitter | pipe_splitter | |
| furnance_1 + mode=liquid | **liquid_furnance_1** | 独立实体（v5 名；v6 名 furnance_1_liquid），多 W管进+E管出 |

config（扁平路径键）：
- 配方：`config.channelRecipes = {"default": "<recipeId>"}`（按 productIcon 匹配配方 outputs；机器只有 default 单通道）
- 准入口：`portGroups[0].ports[0].acceptRule = {base:{kind:"item",itemId}, exclude:[]}` + `admissionRule = {itemId: 阀门启用?itemId:null, limit:null, perMinuteLimit:null}`
- 取货口（unloader_1）：**不是 acceptRule**，而是 slotLink：
  `{id:"warehouse-link:<eid>:unloader_buffer:slot_1", linkType:"share-all", source:{entityId:<eid>,storageSlotGroupId:"unloader_buffer",slotId:"slot_1"}, target:{entityId:"warehouse",storageSlotGroupId:"warehouse",slotId:<itemId>}}`
  + `config["storageSlotGroups[0].slots[0].ignoreStock"]=true`（无限供应演示，可 --no-infinite 关）

## 7. 蓝图文档格式（schema 5）

```json
{ "schemaVersion": 5, "blueprintId": "<uuid>", "version": "", "name": "...", "description": "...",
  "baseId": "wuling_protocol_core", "initialGridPoint": {"x": <包围盒中心x>, "y": <中心y>},
  "entities": {...}, "entityOrder": [...], "slotLinks": [...], "createdAt": "...", "updatedAt": "..." }
```
- initialGridPoint = 实体包围盒**中心**取整（不是 min 角）
- 实体 id 风格：设备 `<definitionId>:<n>`；物流节 `logistics-draft:<belt|pipe>:<x>:<y>`
- 官方 JSON 无 baseId（只有 xSize/zSize=包围盒）→ 默认 wuling_protocol_core（80×80，无内置总线；龙泡泡类蓝图自带 bus 实体直接摆放，不冲突）
- log_hongs_bus(4×8)/log_hongs_bus_source(4×4) 是空壳设备（无端口，仅展示），可直接摆放

## 0. 蓝图码 → 官方解析 JSON（链路第一段）

**熵增 Endfield-API**（文档：`Entropy-Increase-Team/endfield-plugin` 仓库 API.md v3.5.0）：
- Base URL：`https://end-api.shallow.ink`（注意是 `.ink`；`end.shallow.in` 已停放失效）
- `POST /api/v1/auth/anonymous-token`（body `{"fingerprint": "<uuid≥32位>"}`）→ 匿名 token（2h 有效）
- `GET /api/blueprint/get?code=<蓝图码>`（Header `X-Anonymous-Token`）→ 官方解析 JSON
- 已封装为 `fetch_blueprint.py`（token 自动缓存 `.anon_token`，过期自动重建）
- 响应 `data.data.bluePrintData` = nodes 布局；`data.data.query.code` = 原码

## 8. liquid_cleaner_1 是销毁设备

3×3，仅 W 管输入@(0,1)，无输出端口；配方 outputs 全空（void 污水/废液）。不要把水管接到它“后面”等产出。

## 9. 第二批设备注册表扩展（武陵 1-4 蓝图接入，全部 machine 类 +180）

| 平台 ID | footprint | 端口（rot=0） | 备注 |
|---|---|---|---|
| thickener_1 | 6×4 | 6N带进 + 6S带出 | 增稠机 |
| winder_1 | 6×4 | 6N带进 + 6S带出 | 绕线机 |
| seedcol_1 | 5×5 | 5N带进 + 5S带出 | 官方名 seedcollector_1 |
| planter_1 | 5×5 | 5N带进 + 5S带出 | 种植机（普通） |
| hydro_planter_1 | 5×5 | +W管进@(0,2) | **官方 planter_1 + mode=liquid**（v6 名 planter_1_liquid） |
| liquid_purifier_1 | 5×5 | W管进@(0,1)(0,3) + E管出@(4,1)(4,3) | 提纯机（基机即 liquid 变体，不随 mode 切换） |
| mix_pool_1 | 5×5 | N带进@(3,0)(1,0) + S带出@(3,4)(1,4) + W管进@(0,3)(0,1) + E管出@(4,3)(4,1) | 反应池，channels ch1..ch4 |
| mix_pool_2 | 6×5 | N带进×4 + S带出×4 + W管进×2 + E管出×2 | 扩容反应池，channels ch1..ch8 |
| pipe_converger / pipe_connector | 1×1 | 同 log 版，isPipe=true | 官方名 log_pipe_converger / log_pipe_connector |

配方要点：水培 planter 配方在 `planter_1_liquid` 下（`r_hydro_planter_grass_*`），转换时按 v5 实体名 `hydro_planter_1` 键入 recipes.json；mix_pool 的 productIcon 为空 → 不做配方映射（平台端自动模式默认开启）。

验证基线（截至武陵 1-4）：`verify_anchors.py` **318/318 通过**（7 份蓝图）。

## 验证基线

- `python verify_anchors.py`：318/318 节点锚点回归（7 份官方 JSON）
- bp_simple（EF013Eo0i2O06aU0579）转换结果与真实游戏截图逐格一致（熔炉 E 进 W 出、阀门在线、两拐角形状、电扩位置）
- bp_test：132 实体 140 连接；bp_user：127 实体 115 连接 + 9 slotLinks + 3 液体熔炉配方
- 武陵 1-4（EF013Eou8uo47auUu0579 / EF01I43ouo3OA979O5o08 / EF0170iUeUi6855u2O0Ai / EF010819a91uOi12iE179）：367/93/461/376 实体，357/80/451/325 连接，0 跳过，全部经平台导入验证

