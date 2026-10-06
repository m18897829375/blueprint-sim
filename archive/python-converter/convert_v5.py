#!/usr/bin/env python3
# 官方蓝图解析JSON → 终末地工业仿真器(endfield.amiyabot.com / IndustrialPlanner) schema-6 蓝图转换器
# （v6 修正版：对齐平台 v3 分支 schema 6 语义，供 TS 内嵌导入器 P4 回归对照）
#
# 语义依据（全部源码/数据实证，见 workspace/blueprint-sim/RESEARCH.md）：
#   A. 官方锚点随旋转变化：rot=0→(minX,minZ) 90→(minX,maxZ) 180→(maxX,maxZ) 270→(maxX,minZ)
#   B. 坐标镜像：platform.y = (zSize-1) - official.z；平台 position = 旋转后 footprint 左上角
#   C. 旋转映射（v6 语义）：恒等 q=rot（v6 注册表 rotation=0 = 官方默认朝向，AKEData 校准）；
#      v5 时代 ROT_OFFSET_V5（machine+180/admission+90/identity 0）已移除——5→6 迁移的补偿
#      恒等式（+180/+270）恰好还原官方朝向，v6 直接生成官方朝向即可
#   D. 物流：straight rot=流向；turn 查表 classify_logistics（cw/ccw 与 rotation 均查表，非启发式）
#   E. 端口接驳：平台连通规则严格（端口格相邻+边互对+isPipe 一致），物流线首/末格若与设备端口
#      几何接触但朝向不符，自动改判定为 turn 使端口面对接（游戏侧宽容、平台侧严格的语义差）
#   F. or-bug 修复（2026-09-21）：单格段流向推断 `infer() or fallback` 会把合法的 0(E 流)
#      误判为推断失败；改为显式 None 判定。TS 版行为即修复后行为（武陵4 (17,5)/(32,5) 实证）。
import argparse
import json
import sys
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from registry_table import (
    ID_MAP, REGISTRY, LOGISTICS_FAMILY, ROT_OFFSET_V5,
    official_footprint_origin, EDGE_DELTA, EDGE_ORDER, rotate_edge, rotate_local_cell,
    rotated_size, dir_angle, classify_logistics,
)

LOGISTICS_TIDS = {"grid_belt_01": "belt", "log_pipe_01": "pipe"}


# ---------- 官方 JSON 读取 ----------

def load_blueprint(src_path):
    raw = json.load(open(src_path, encoding="utf-8"))
    bp = raw["data"]["data"]["bluePrintData"]
    return bp


def node_rot(node):
    tr = node.get("transform", {})
    return int((tr.get("rotation") or tr.get("direction") or {}).get("y", 0)) % 360


def node_anchor(node):
    """设备锚点格：transform.position（官方语义=随旋转的角落格）。
    极少数节点仅有 interactiveParam（中心点），回退按 rot=0 角点近似。"""
    tr = node.get("transform", {})
    pos = tr.get("position")
    if pos:
        return int(pos["x"]), int(pos["z"])
    ip = (tr.get("interactiveParam") or {}).get("position") or {}
    return round(ip.get("x", 0.5) - 0.5), round(ip.get("z", 0.5) - 0.5)


# ---------- 物流展开 ----------

def expand_polyline(pts):
    """points 折线（平台坐标，已 z 翻转）逐段连线展开为逐格序列"""
    cells = []
    for i in range(len(pts) - 1):
        x1, y1 = pts[i]
        x2, y2 = pts[i + 1]
        steps = max(abs(x2 - x1), abs(y2 - y1))
        if steps == 0:
            if not cells or cells[-1] != (x1, y1):
                cells.append((x1, y1))
            continue
        for s in range(steps + 1):
            c = (round(x1 + (x2 - x1) * s / steps), round(y1 + (y2 - y1) * s / steps))
            if not cells or cells[-1] != c:
                cells.append(c)
    return cells


class Converter:
    def __init__(self, bp, base_id="wuling_protocol_core", infinite_supply=True, recipes=None):
        self.bp = bp
        self.zmax = bp.get("zSize", 0) - 1
        self.base_id = base_id
        self.infinite = infinite_supply
        self.recipes = recipes or {}
        self.entities = {}          # eid -> platform entity dict
        self.order = []
        self.slot_links = []
        self.skipped = []           # (templateId, 原因)
        self.report_notes = []
        self.dev_meta = {}          # eid -> (defId, x, y, rot_official, w, h)
        self.logi_meta = {}         # eid -> (kind, x, y)  物流节
        self.cell_owner = {}        # (kind, x, y) -> eid（物流占用）
        self.counters = defaultdict(int)

    # ----- 设备 -----
    def convert_device(self, node):
        t = node["templateId"]
        # 模式变体分流：furnance_1 + liquid 模式 → 平台 v6 独立实体 furnance_1_liquid
        mode = None
        for com in node.get("coms") or []:
            fm = com.get("formulaMan")
            if fm and fm.get("curMode"):
                mode = fm["curMode"]
        def_id = ID_MAP.get(t, t)
        # 模式变体分流（官方基机+mode=liquid → 平台 v6 独立实体名）
        if mode == "liquid" and t in ("furnance_1", "planter_1"):
            def_id = {"furnance_1": "furnance_1_liquid", "planter_1": "planter_1_liquid"}[t]
        if def_id not in REGISTRY:
            self.skipped.append((t, "注册表无此实体"))
            return
        (W, H), rot_class, _ports = REGISTRY[def_id]
        rot_off = node_rot(node)
        ax, az = node_anchor(node)
        x0, z0, w, h = official_footprint_origin(ax, az, rot_off, W, H)
        # 平台 position = 翻转后占地左上角
        px, py = x0, self.zmax - z0 - (h - 1)
        # v6 语义：旋转恒等（v6 注册表 rotation=0 = 官方默认朝向）。
        # v5 的 ROT_OFFSET_V5（machine+180/admission+90）已移除——5→6 迁移补偿恒等式恰好还原。
        rot_out = rot_off

        idx = self.counters[def_id]
        self.counters[def_id] += 1
        eid = f"{def_id}:{idx}"
        config, links = self.build_config(node, def_id, eid)

        self.entities[eid] = {
            "id": eid, "definitionId": def_id,
            "position": {"x": px, "y": py}, "rotation": rot_out,
            "config": config, "tags": [],
        }
        self.order.append(eid)
        self.slot_links.extend(links)
        # rot_phys = 物理朝向（=官方 rot = v6 emitted rot，恒等）
        self.dev_meta[eid] = (def_id, px, py, rot_off, w, h)

    def build_config(self, node, def_id, eid):
        config, links = {}, []
        product = node.get("productIcon") or ""
        mode = None
        for com in node.get("coms") or []:
            sel = com.get("selector", {}).get("selectedItemId")
            if sel and def_id == "unloader_1":
                links.append({
                    "id": f"warehouse-link:{eid}:unloader_buffer:slot_1",
                    "linkType": "share-all",
                    "source": {"entityId": eid, "storageSlotGroupId": "unloader_buffer", "slotId": "slot_1"},
                    "target": {"entityId": "warehouse", "storageSlotGroupId": "warehouse", "slotId": sel},
                })
                if self.infinite:
                    config["storageSlotGroups[0].slots[0].ignoreStock"] = True
                self.report_notes.append(f"{eid}: 取货口→仓库链接 {sel}")
            valve = com.get("boxValve") or com.get("fluidValve")
            if valve and def_id in ("log_admission", "pipe_admission"):
                item = valve.get("selectedItemId")
                if item:
                    config["portGroups[0].ports[0].acceptRule"] = {
                        "base": {"kind": "item", "itemId": item}, "exclude": []}
                    config["portGroups[0].ports[0].admissionRule"] = {
                        "itemId": item if valve.get("valveEnable") else None,
                        "limit": None, "perMinuteLimit": None}
                    self.report_notes.append(f"{eid}: 准入口材料 {item} (valveEnable={valve.get('valveEnable')})")
            fm = com.get("formulaMan")
            if fm:
                mode = fm.get("curMode")
        if product and def_id in self.recipes and def_id not in ("mix_pool_1", "mix_pool_2"):
            rid = self.match_recipe(def_id, product, mode)
            if rid:
                config["channelRecipes"] = {"default": rid}
                self.report_notes.append(f"{eid}: 配方 {rid} (product={product}, mode={mode})")
            else:
                self.report_notes.append(f"⚠️ {eid}: 配方未匹配 product={product} mode={mode}，留默认")
        # —— v6 placementDefaults 等价补漏（TS 版来自平台定义默认，此处显式写）——
        # storager：无线提交（22/22 蓝图 coms 全空证实游戏隐式默认开启）
        if def_id == "storager_1":
            config["channelRecipes"] = {**config.get("channelRecipes", {}),
                                        "warehouse_submit": "r_warehouse_submit"}
        # mix_pool：自动反应模式 + 输出端口按 selector 写 item 级白名单 + ch1 配方固化
        # （R1 同步 2026-09-22：严格按蓝图原本输出规则；comPos 61=固体口、62-66=液体口）
        if def_id in ("mix_pool_1", "mix_pool_2"):
            config["recipeChannelAutomaticModeEnabled"] = True
            solid_item = None
            fluid_items = []
            for com in node.get("coms") or []:
                pos = com.get("comPos") or 0
                sel = (com.get("selector") or {}).get("selectedItemId")
                if not sel:
                    continue
                if pos == 61:
                    solid_item = sel
                elif 62 <= pos <= 66:
                    fluid_items.append((pos, sel))
            fluid_items.sort(key=lambda x: x[0])
            fluid_items = [item for _pos, item in fluid_items]
            # 固体口：item_output 组（portGroups[0]）全部端口 item 级白名单
            if solid_item:
                n_belt_out = 2 if def_id == "mix_pool_1" else 4
                for pi in range(n_belt_out):
                    config[f"portGroups[0].ports[{pi}].acceptRule"] = {
                        "base": {"kind": "item", "itemId": solid_item}, "exclude": []}
            # 液体口：按 comPos 顺序分配 fluid_output_a（[2]）/ fluid_output_b（[3]）
            for idx, item in enumerate(fluid_items):
                gi = 2 + idx
                if gi > 3:
                    self.report_notes.append(
                        f"⚠️ {eid}: 液体选择器物品 {item} 超出平台液体输出口数，未配置")
                    break
                config[f"portGroups[{gi}].ports[0].acceptRule"] = {
                    "base": {"kind": "item", "itemId": item}, "exclude": []}
            # 配方意图：selector 集合 ⊆ outputs 优先，否则交集最大
            selector_all = ([solid_item] if solid_item else []) + fluid_items
            if selector_all:
                rid = self.match_recipe_by_set(def_id, selector_all, mode)
                if rid:
                    config.setdefault("channelRecipes", {})["ch1"] = rid
                    self.report_notes.append(
                        f"{eid}: 反应池配方 {rid}（selector={','.join(selector_all)}）")
        return config, links

    def match_recipe(self, def_id, product, mode):
        cands = [r for r in self.recipes.get(def_id, []) if product in r.get("outputs", [])]
        if not cands:
            return None
        if mode:
            for r in cands:
                if f"_{mode}" in r["id"] or mode in r.get("tags", []):
                    return r["id"]
        return cands[0]["id"]

    def match_recipe_by_set(self, def_id, selector_items, mode=None):
        """selector 集合 ⊆ outputs 优先；否则交集最大（对齐 TS matchRecipeBySelectorSet）。"""
        recipes = self.recipes.get(def_id, [])
        item_set = set(selector_items)
        full = [r for r in recipes if item_set <= set(r.get("outputs", []))]
        if full:
            return full[0]["id"]
        best, best_overlap = None, 0
        for r in recipes:
            overlap = len(item_set & set(r.get("outputs", [])))
            if overlap > best_overlap:
                best, best_overlap = r, overlap
        return best["id"] if best else None

    # ----- 物流 -----
    def convert_logistics(self):
        """两遍处理：先展开全部多格段（几何方向确定），再处理单格段（邻接推断依赖邻格已存在）"""
        pending_single = []
        for node in self.bp["nodes"]:
            t = node["templateId"]
            if t not in LOGISTICS_TIDS:
                continue
            kind = LOGISTICS_TIDS[t]
            raw_pts = node["transform"].get("points") or []
            pts = [(int(p["x"]), self.zmax - int(p["z"])) for p in raw_pts]
            cells = expand_polyline(pts)
            if not cells:
                continue
            if len(cells) == 1:
                pending_single.append((node, kind, cells))
                continue
            dirs = self.flow_dirs(node, cells, kind, None)
            for i, (cx, cy) in enumerate(cells):
                d_in = dirs[i - 1] if i > 0 else dirs[i]
                shape, rot = classify_logistics(d_in, dirs[i])
                self.add_logi_cell(kind, cx, cy, shape, rot)
        for node, kind, cells in pending_single:
            dout = (node["transform"].get("directionOut") or {}).get("y")
            fallback_dir = (90 - int(dout)) % 360 if dout is not None else None
            dirs = self.flow_dirs(node, cells, kind, fallback_dir)
            shape, rot = classify_logistics(dirs[0], dirs[0])
            self.add_logi_cell(kind, cells[0][0], cells[0][1], shape, rot)

    def flow_dirs(self, node, cells, kind, fallback_dir):
        """每格流向（平台角）。多格段按几何；单格段邻接图推断，fallback directionOut。"""
        if len(cells) > 1:
            dirs = []
            for i, c in enumerate(cells):
                if i + 1 < len(cells):
                    d = dir_angle(cells[i + 1][0] - c[0], cells[i + 1][1] - c[1])
                else:
                    d = dir_angle(c[0] - cells[i - 1][0], c[1] - cells[i - 1][1])
                dirs.append(d)
            return dirs
        # or-bug 修复：infer 返回 0（E 流）是合法值，不能用 `or` 短路（会把 0 误判为失败）
        d = self.infer_single_cell_dir(cells[0], kind)
        if d is None:
            d = fallback_dir if fallback_dir is not None else 0
        return [d]

    def infer_single_cell_dir(self, cell, kind):
        """单格段：从邻接图推断流向。上游=邻格流向指向本格/设备输出口面对本格；下游同理。"""
        cx, cy = cell
        ups, downs = [], []
        for edge, ang in (("E", 0), ("S", 90), ("W", 180), ("N", 270)):
            dx, dy = EDGE_DELTA[edge]
            nb = self.cell_owner.get((kind, cx + dx, cy + dy))
            if nb:
                nrot = self.entities[nb]["rotation"]
                if nrot == (ang + 180) % 360:
                    ups.append(ang)      # 邻格流向指向本格
                elif nrot == ang:
                    downs.append(ang)    # 本格流向指向邻格
        if len(ups) == 1 and not downs:
            return (ups[0] + 180) % 360  # 上游来向 = 穿过本格继续
        if len(downs) == 1 and not ups:
            return downs[0]
        return None

    def add_logi_cell(self, kind, x, y, shape, rot):
        key = (kind, x, y)
        if key in self.cell_owner:
            return  # 同族同格去重（带×管可叠放，不同 key）
        eid = f"logistics-draft:{kind}:{x}:{y}"
        def_id = f"{kind}_{shape}_1x1"
        self.entities[eid] = {
            "id": eid, "definitionId": def_id,
            "position": {"x": x, "y": y}, "rotation": rot,
            "config": {}, "tags": []}
        self.order.append(eid)
        self.cell_owner[key] = eid
        self.logi_meta[eid] = (kind, x, y)

    # ----- 端口模型（物理帧 = v6 注册表 + 官方 rot / 物流节用 emitted rot）-----
    def entity_ports(self, eid):
        e = self.entities[eid]
        def_id = e["definitionId"]
        (W, H), _rc, ports = REGISTRY[def_id]
        if eid in self.dev_meta:
            rot = self.dev_meta[eid][3]      # 设备：物理帧 = 官方 rot
        else:
            rot = e["rotation"]              # 物流节：恒等类，emitted 即物理
        px, py = e["position"]["x"], e["position"]["y"]
        out = []
        for (lx, ly, edge, direction, kind) in ports:
            cx, cy = rotate_local_cell(lx, ly, W, H, rot)
            e2 = rotate_edge(edge, rot)
            dx, dy = EDGE_DELTA[e2]
            inside = (px + cx, py + cy)
            out.append({"edge": e2, "dir": direction, "kind": kind,
                        "inside": inside, "outside": (inside[0] + dx, inside[1] + dy)})
        return out

    # ----- 端口接驳（E 规则）-----
    def adapt_line_endpoints(self):
        """物流线首/末格：若与设备端口几何接触但带口朝向不符 → 改判 turn 使端口面对接。"""
        # 建端口外侧格索引：(x, y, kind) -> [(朝向设备的边 M, dir)]
        facing = defaultdict(list)
        for eid in self.order:
            if eid in self.logi_meta:
                continue
            for p in self.entity_ports(eid):
                m_edge = EDGE_ORDER[(EDGE_ORDER.index(p["edge"]) + 2) % 4]  # 从物流格看向设备的边
                facing[(p["outside"][0], p["outside"][1], p["kind"])].append((m_edge, p["dir"], eid))
        adapted = {}  # 已接驳格 (kind,x,y) -> dev，防止二次改写覆盖
        # 逐物流节点（需要线序，重新展开）
        for node in self.bp["nodes"]:
            t = node["templateId"]
            if t not in LOGISTICS_TIDS:
                continue
            kind = LOGISTICS_TIDS[t]
            raw_pts = node["transform"].get("points") or []
            pts = [(int(p["x"]), self.zmax - int(p["z"])) for p in raw_pts]
            cells = expand_polyline(pts)
            if not cells:
                continue
            endpoints = [(0, True)] if len(cells) == 1 else [(0, True), (len(cells) - 1, False)]
            for idx, is_start in endpoints:
                cx, cy = cells[idx]
                key = (kind, cx, cy)
                eid = self.cell_owner.get(key)
                if not eid:
                    continue
                ent = self.entities[eid]
                d = ent["rotation"]  # 当前 out 流向（straight）或近似
                for (m_edge, pdir, dev) in facing.get((cx, cy, kind), []):
                    m_ang = {"E": 0, "S": 90, "W": 180, "N": 270}[m_edge]
                    if pdir == "output" and is_start:
                        # 设备输出 → 线首：带 input 边须朝设备（M）
                        if (m_ang + 180) % 360 == d:
                            continue  # 直带流出已通
                        if (d - (m_ang + 180)) % 360 in (90, 270):
                            if key in adapted:
                                self.report_notes.append(
                                    f"⚠️ 端口接驳冲突: ({cx},{cy}) 已对接 {adapted[key]}，"
                                    f"跳过 {dev}（一格多设备端口，1×1 无法同时服务）")
                                continue
                            self.swap_logi(eid, kind, cx, cy, (m_ang + 180) % 360, d, dev)
                            adapted[key] = dev
                    elif pdir == "input" and not is_start:
                        # 线末 → 设备输入：带 output 边须朝设备（M）
                        if d == m_ang:
                            continue  # 直带直入已通
                        if (m_ang - d) % 360 in (90, 270):
                            if key in adapted:
                                self.report_notes.append(
                                    f"⚠️ 端口接驳冲突: ({cx},{cy}) 已对接 {adapted[key]}，"
                                    f"跳过 {dev}（一格多设备端口，1×1 无法同时服务）")
                                continue
                            self.swap_logi(eid, kind, cx, cy, d, m_ang, dev)
                            adapted[key] = dev

    def swap_logi(self, eid, kind, x, y, d_in, d_out, dev):
        shape, rot = classify_logistics(d_in, d_out)
        new_id = f"{kind}_{shape}_1x1"
        if self.entities[eid]["definitionId"] != new_id or self.entities[eid]["rotation"] != rot:
            self.entities[eid]["definitionId"] = new_id
            self.entities[eid]["rotation"] = rot
            self.report_notes.append(
                f"端口接驳: ({x},{y}) {kind} → {new_id} rot={rot}（对接 {dev}）")

    # ----- 校验 -----
    def validate(self):
        """平台连通规则本地实现：output×input 格相邻+边互对+isPipe一致+至少一端物流族。"""
        ports_by_eid = {eid: self.entity_ports(eid) for eid in self.order}
        # 输入端口索引：key = (inside格, kind, outside格)。连接条件 source.outside==target.inside
        # 且 source.inside==target.outside → 以 source 的 (outside, kind, inside) 查此索引。
        in_index = defaultdict(list)
        all_out = []
        for eid, ps in ports_by_eid.items():
            for p in ps:
                if p["dir"] == "input":
                    in_index[(p["inside"], p["kind"], p["outside"])].append((eid, p))
                else:
                    all_out.append((eid, p))
        connections = []
        logi_eids = {eid for eid in self.order
                     if self.entities[eid]["definitionId"] in LOGISTICS_FAMILY}
        for (eid, p) in all_out:
            key = (p["outside"], p["kind"], p["inside"])
            for (tid, tp) in in_index.get(key, []):
                if tid == eid:
                    continue
                if eid not in logi_eids and tid not in logi_eids:
                    continue  # 机器↔机器直连不建连（平台规则）
                connections.append((eid, tid, p["inside"]))
        connected_pairs = {(a, b) for a, b, _ in connections}
        # 报告：设备端口外侧格有物流但朝向未连通
        problems = []
        for eid, ps in ports_by_eid.items():
            if eid in self.logi_meta:
                continue
            def_id = self.entities[eid]["definitionId"]
            for p in ps:
                occ = self.cell_owner.get((p["kind"], p["outside"][0], p["outside"][1]))
                if not occ:
                    continue
                if (eid, occ) not in connected_pairs and (occ, eid) not in connected_pairs:
                    problems.append(f"⚠️ {def_id}({eid}) 端口{p['dir']}@{p['inside']}{p['edge']} "
                                    f"与物流格{p['outside']}几何接触但未连通")
        return connections, problems

    # ----- 主流程 -----
    def run(self):
        for node in sorted(self.bp["nodes"], key=lambda x: x["nodeId"]):
            if node["templateId"] in LOGISTICS_TIDS:
                continue
            self.convert_device(node)
        self.convert_logistics()
        self.adapt_line_endpoints()
        connections, problems = self.validate()
        return connections, problems

    def emit(self, dst_path):
        xs, ys = [], []
        for eid in self.order:
            e = self.entities[eid]
            (W, H), _rc, _p = REGISTRY[e["definitionId"]]
            w, h = rotated_size(W, H, e["rotation"])
            xs += [e["position"]["x"], e["position"]["x"] + w - 1]
            ys += [e["position"]["y"], e["position"]["y"] + h - 1]
        # 包围盒中心（对齐 TS Math.round 语义：floor(x+0.5)；Python round 是银行家舍入，.5 边界会差 1）
        cx = int((min(xs) + max(xs)) / 2 + 0.5) if xs else 0
        cy = int((min(ys) + max(ys)) / 2 + 0.5) if ys else 0
        now = datetime.now(timezone.utc).isoformat()
        doc = {
            "schemaVersion": 6, "blueprintId": str(uuid.uuid4()), "version": "",
            "name": self.bp.get("name", "未命名蓝图"), "description": self.bp.get("desc", ""),
            "baseId": self.base_id, "initialGridPoint": {"x": cx, "y": cy},
            "entities": self.entities, "entityOrder": self.order,
            "slotLinks": self.slot_links, "regions": [],
            "createdAt": now, "updatedAt": now,
        }
        json.dump(doc, open(dst_path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        return doc


def render_preview(doc, out_png, title, dev_phys_rot=None):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle
    plt.rcParams["font.family"] = ["Microsoft YaHei", "SimHei", "sans-serif"]
    plt.rcParams["axes.unicode_minus"] = False

    fig, ax = plt.subplots(figsize=(14, 10))
    COLORS = {"belt": "#f5c542", "pipe": "#42a5f5"}
    max_x = max(e["position"]["x"] for e in doc["entities"].values())
    max_y = max(e["position"]["y"] for e in doc["entities"].values())
    for eid in doc["entityOrder"]:
        e = doc["entities"][eid]
        did, rot = e["definitionId"], e["rotation"]
        (W, H), _rc, _p = REGISTRY[did]
        w, h = rotated_size(W, H, rot)
        x, y = e["position"]["x"], e["position"]["y"]
        if did.startswith("belt_") or did.startswith("pipe_"):
            kind = "belt" if did.startswith("belt_") else "pipe"
            ax.add_patch(Rectangle((x + 0.08, y + 0.08), 0.84, 0.84,
                                   facecolor=COLORS[kind], edgecolor="#888", alpha=0.85))
            for (lx, ly, edge, direction, _k) in REGISTRY[did][2]:
                if direction != "output":
                    continue
                e2 = rotate_edge(edge, rot)
                dx, dy = EDGE_DELTA[e2]
                ax.arrow(x + 0.5, y + 0.5, dx * 0.3, dy * 0.3,
                         head_width=0.12, head_length=0.08, fc="#333", ec="#333",
                         length_includes_head=True)
        else:
            phys = (dev_phys_rot or {}).get(eid, rot)
            ax.add_patch(Rectangle((x, y), w, h, facecolor="#e57373", edgecolor="#333", alpha=0.75))
            ax.text(x + w / 2, y + h / 2, f"{did}\nr{phys}", ha="center", va="center", fontsize=7)
    ax.set_xlim(-1, max_x + 3)
    ax.set_ylim(-1, max_y + 3)
    ax.invert_yaxis()
    ax.set_aspect("equal")
    ax.grid(True, alpha=0.3)
    ax.set_title(title)
    fig.tight_layout()
    fig.savefig(out_png, dpi=110)
    plt.close(fig)


def main():
    ap = argparse.ArgumentParser(description="官方蓝图JSON → 仿真平台 schema-5 转换器 v5")
    ap.add_argument("src", nargs="?", default="data/bp_simple.json")
    ap.add_argument("dst", nargs="?", default="out/sim_v5.json")
    ap.add_argument("--base", default="wuling_protocol_core")
    ap.add_argument("--no-infinite", action="store_true", help="取货口不开无限供应")
    ap.add_argument("--recipes", default="recipes.json", help="配方切片（可选）")
    ap.add_argument("--preview", default=None, help="输出预览 png 路径")
    args = ap.parse_args()

    recipes = {}
    rp = Path(args.recipes)
    if rp.exists():
        recipes = json.load(open(rp, encoding="utf-8"))

    bp = load_blueprint(args.src)
    conv = Converter(bp, base_id=args.base, infinite_supply=not args.no_infinite, recipes=recipes)
    connections, problems = conv.run()
    doc = conv.emit(args.dst)

    n_logi = len(conv.logi_meta)
    print(f"转换完成: {len(doc['entities'])} 实体（设备 {len(conv.dev_meta)} / 物流节 {n_logi}），"
          f"slotLinks {len(doc['slotLinks'])}")
    print(f"拓扑连接 {len(connections)} 条")
    if conv.skipped:
        print(f"跳过(注册表不支持): {conv.skipped}")
    for note in conv.report_notes:
        print(f"  {note}")
    for p in problems:
        print(p)
    if args.preview:
        render_preview(doc, args.preview, f"{Path(args.src).stem} → v5")
        print(f"预览图: {args.preview}")


if __name__ == "__main__":
    main()
