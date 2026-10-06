# 平台注册表切片 —— 源：hsyhhssyy/IndustrialPlanner src/registry/entity-definition.ts (v6/main, commit 106657fa)
# 经三份官方蓝图 33+ 锚点样本与 18 个端口邻接样本实证校准。
#
# 坐标系（平台）：y 轴向下，rotation 顺时针为正；position = 旋转后 footprint 的左上角。
# 端口表为 rotation=0 基准（v6 语义）；ports 元组 = (localX, localY, edge, direction, kind)
#   edge ∈ {N,E,S,W}（边增量 N=(0,-1) E=(1,0) S=(0,1) W=(-1,0)）
#   direction ∈ {input, output}；kind ∈ {belt, pipe}
#
# rot_class（schema 5 线上时代的旋转映射，v5_rot = (官方rot + offset) % 360）：
#   "machine"   → offset +180（5→6 迁移对 37 台机器 +180，v5 注册表与 v6 相差 180）
#   "admission" → offset +90 （5→6 迁移对准入口 +270）
#   "identity"  → offset 0   （带/管节、分流/汇流/连接器、装卸货口、电扩、总线等）

# 官方 templateId → 平台 definitionId（对齐仓库 device-building-aliases.mjs）
ID_MAP = {
    "component_mc_1": "cmpt_mc_1",
    "tools_assebling_mc_1": "tools_asm_mc_1",
    "power_station_1": "power_sta_1",
    "log_conditioner": "log_admission",
    "log_pipe_conditioner": "pipe_admission",
    "power_diffuser_2": "power_diffuser_1",   # 降级：布局一致，仅供电范围差异
    "log_pipe_splitter": "pipe_splitter",
    "log_pipe_converger": "pipe_converger",
    "log_pipe_connector": "pipe_connector",
    "seedcollector_1": "seedcol_1",
}

# definitionId → (footprint(w,h), rot_class, ports)
# ports: (lx, ly, edge, dir, kind)
def _n_in_s_out(w, h, kind="belt"):
    """标准机器端口：w 个 N 进（y=0 行）+ w 个 S 出（y=h-1 行）"""
    ports = []
    for x in range(w):
        ports.append((x, 0, "N", "input", kind))
    for x in range(w):
        ports.append((x, h - 1, "S", "output", kind))
    return ports

REGISTRY = {
    # —— 机器类（v5 时代 rot_class=machine +180；v6 语义旋转恒等，rot_class 仅作历史参照）——
    "furnance_1":       ((3, 3), "machine", _n_in_s_out(3, 3)),
    # 熔炉液体模式变体（官方 furnance_1 + formulaMan.curMode="liquid"）。
    # v6 注册表实体名 furnance_1_liquid（v5 名 liquid_furnance_1 已弃用）。
    # 端口（v6 furnance_1_liquid rot=0 基准）：3N带输入 + W管输入@(0,1) + E管输出@(2,1) + 3S带输出
    "furnance_1_liquid": ((3, 3), "machine", _n_in_s_out(3, 3) + [
        (0, 1, "W", "input", "pipe"), (2, 1, "E", "output", "pipe")]),
    "storager_1":       ((3, 3), "machine", _n_in_s_out(3, 3)),
    "grinder_1":        ((3, 3), "machine", _n_in_s_out(3, 3)),
    "cmpt_mc_1":        ((3, 3), "machine", _n_in_s_out(3, 3)),
    "shaper_1":         ((3, 3), "machine", _n_in_s_out(3, 3)),
    "tools_asm_mc_1":   ((6, 4), "machine", _n_in_s_out(6, 4)),
    "thickener_1":      ((6, 4), "machine", _n_in_s_out(6, 4)),   # 增稠机
    "winder_1":         ((6, 4), "machine", _n_in_s_out(6, 4)),   # 绕线机
    "seedcol_1":        ((5, 5), "machine", _n_in_s_out(5, 5)),   # 采种机（官方 seedcollector_1）
    "planter_1":        ((5, 5), "machine", _n_in_s_out(5, 5)),   # 种植机
    # 水培种植机（官方 planter_1 + mode=liquid）：v6 注册表实体名（v5 名 hydro_planter_1 已弃用）
    # 端口（v6 planter_1_liquid rot=0 基准）：5N带输入 + 5S带输出 + W管输入@(0,2)
    "planter_1_liquid":  ((5, 5), "machine", _n_in_s_out(5, 5) + [(0, 2, "W", "input", "pipe")]),
    # 提纯机：全管端口，W 进 ×2、E 出 ×2（左右出口白名单不同）
    "liquid_purifier_1": ((5, 5), "machine", [
        (0, 1, "W", "input", "pipe"), (0, 3, "W", "input", "pipe"),
        (4, 1, "E", "output", "pipe"), (4, 3, "E", "output", "pipe")]),
    # 反应池：N 边带输入 + S 边带输出 + W 边管输入 + E 边管输出
    "mix_pool_1": ((5, 5), "machine", [
        (3, 0, "N", "input", "belt"), (1, 0, "N", "input", "belt"),
        (3, 4, "S", "output", "belt"), (1, 4, "S", "output", "belt"),
        (0, 3, "W", "input", "pipe"), (0, 1, "W", "input", "pipe"),
        (4, 3, "E", "output", "pipe"), (4, 1, "E", "output", "pipe")]),
    "mix_pool_2": ((6, 5), "machine", [
        (4, 0, "N", "input", "belt"), (3, 0, "N", "input", "belt"),
        (2, 0, "N", "input", "belt"), (1, 0, "N", "input", "belt"),
        (4, 4, "S", "output", "belt"), (3, 4, "S", "output", "belt"),
        (2, 4, "S", "output", "belt"), (1, 4, "S", "output", "belt"),
        (0, 3, "W", "input", "pipe"), (0, 1, "W", "input", "pipe"),
        (5, 3, "E", "output", "pipe"), (5, 1, "E", "output", "pipe")]),
    "power_sta_1":      ((2, 2), "machine", [(1, 0, "N", "input", "belt"), (0, 0, "N", "input", "belt")]),
    "liquid_cleaner_1": ((3, 3), "machine", [(0, 1, "W", "input", "pipe")]),
    # —— 准入口（rot_class=admission, v5 +90）——
    "log_admission":  ((1, 1), "admission", [(0, 0, "N", "input", "belt"), (0, 0, "S", "output", "belt")]),
    "pipe_admission": ((1, 1), "admission", [(0, 0, "N", "input", "pipe"), (0, 0, "S", "output", "pipe")]),
    # —— 恒等类（rot_class=identity）——
    "unloader_1":       ((3, 1), "identity", [(1, 0, "S", "output", "belt")]),
    "loader_1":         ((3, 1), "identity", [(1, 0, "N", "input", "belt")]),
    "power_diffuser_1": ((2, 2), "identity", []),
    "log_splitter":  ((1, 1), "identity", [(0, 0, "N", "input", "belt"), (0, 0, "E", "output", "belt"),
                                            (0, 0, "W", "output", "belt"), (0, 0, "S", "output", "belt")]),
    "log_converger": ((1, 1), "identity", [(0, 0, "N", "input", "belt"), (0, 0, "E", "input", "belt"),
                                            (0, 0, "W", "input", "belt"), (0, 0, "S", "output", "belt")]),
    "log_connector": ((1, 1), "identity", [(0, 0, "N", "input", "belt"), (0, 0, "S", "input", "belt"),
                                            (0, 0, "N", "output", "belt"), (0, 0, "S", "output", "belt"),
                                            (0, 0, "W", "input", "belt"), (0, 0, "E", "input", "belt"),
                                            (0, 0, "W", "output", "belt"), (0, 0, "E", "output", "belt")]),
    "pipe_splitter":  ((1, 1), "identity", [(0, 0, "N", "input", "pipe"), (0, 0, "E", "output", "pipe"),
                                             (0, 0, "W", "output", "pipe"), (0, 0, "S", "output", "pipe")]),
    "pipe_converger": ((1, 1), "identity", [(0, 0, "N", "input", "pipe"), (0, 0, "E", "input", "pipe"),
                                             (0, 0, "W", "input", "pipe"), (0, 0, "S", "output", "pipe")]),
    "pipe_connector": ((1, 1), "identity", [(0, 0, "N", "input", "pipe"), (0, 0, "S", "input", "pipe"),
                                             (0, 0, "N", "output", "pipe"), (0, 0, "S", "output", "pipe"),
                                             (0, 0, "W", "input", "pipe"), (0, 0, "E", "input", "pipe"),
                                             (0, 0, "W", "output", "pipe"), (0, 0, "E", "output", "pipe")]),
    # 物流节（由转换器展开生成，不直接出现在官方节点里）
    "belt_straight_1x1":  ((1, 1), "identity", [(0, 0, "W", "input", "belt"), (0, 0, "E", "output", "belt")]),
    "belt_turn_cw_1x1":   ((1, 1), "identity", [(0, 0, "E", "input", "belt"), (0, 0, "N", "output", "belt")]),
    "belt_turn_ccw_1x1":  ((1, 1), "identity", [(0, 0, "N", "input", "belt"), (0, 0, "E", "output", "belt")]),
    "pipe_straight_1x1":  ((1, 1), "identity", [(0, 0, "W", "input", "pipe"), (0, 0, "E", "output", "pipe")]),
    "pipe_turn_cw_1x1":   ((1, 1), "identity", [(0, 0, "E", "input", "pipe"), (0, 0, "N", "output", "pipe")]),
    "pipe_turn_ccw_1x1":  ((1, 1), "identity", [(0, 0, "N", "input", "pipe"), (0, 0, "E", "output", "pipe")]),
    # 洪斯总线（valley4 基地内置同款定义；摆放型实体）
    "log_hongs_bus":        ((4, 8), "identity", []),
    "log_hongs_bus_source": ((4, 4), "identity", []),
}

# 物流族（isGeneralLogisticsDevice：连通规则中"至少一端须为物流族"）
LOGISTICS_FAMILY = {
    "belt_straight_1x1", "belt_turn_cw_1x1", "belt_turn_ccw_1x1",
    "pipe_straight_1x1", "pipe_turn_cw_1x1", "pipe_turn_ccw_1x1",
    "log_splitter", "log_converger", "log_connector", "log_admission",
    "pipe_splitter", "pipe_converger", "pipe_connector", "pipe_admission",
}

ROT_OFFSET_V5 = {"machine": 180, "admission": 90, "identity": 0}

# —— 官方侧锚点表（实证）：官方 rot → 锚点在占地中的角落 ——
# rot=0: (minX,minZ)  90: (minX,maxZ)  180: (maxX,maxZ)  270: (maxX,minZ)
# 由 (ax,az,rot,W,H) 还原官方占地左上角 (x0,z0)；W/H 为注册表基准尺寸，
# 官方 rot∈{90,270} 时占地为 H×W（宽高互换，与平台 getRotatedGridFootprint 同构）。
def official_footprint_origin(ax, az, rot, W, H):
    w = W if rot in (0, 180) else H
    h = H if rot in (0, 180) else W
    if rot == 0:
        x0, z0 = ax, az
    elif rot == 90:
        x0, z0 = ax, az - h + 1
    elif rot == 180:
        x0, z0 = ax - w + 1, az - h + 1
    else:  # 270
        x0, z0 = ax - w + 1, az
    return x0, z0, w, h

# —— 平台侧旋转数学（与 compiler.ts 同构）——
EDGE_DELTA = {"N": (0, -1), "E": (1, 0), "S": (0, 1), "W": (-1, 0)}
EDGE_ORDER = ["N", "E", "S", "W"]  # 顺时针

def rotate_edge(edge, rot):
    return EDGE_ORDER[(EDGE_ORDER.index(edge) + rot // 90) % 4]

def rotate_local_cell(x, y, W, H, rot):
    """端口局部格旋转（用 rotation=0 基准 footprint W×H）"""
    if rot == 0:
        return x, y
    if rot == 90:
        return H - 1 - y, x
    if rot == 180:
        return W - 1 - x, H - 1 - y
    return y, W - 1 - x  # 270

def rotated_size(W, H, rot):
    return (H, W) if rot in (90, 270) else (W, H)

# 平台流向角：0=E 90=S 180=W 270=N（屏幕坐标，与 rotation 同语义）
def dir_angle(dx, dy):
    if dx > 0: return 0
    if dy > 0: return 90
    if dx < 0: return 180
    if dy < 0: return 270
    return None

# —— turn 终版规则（D 表）：(d_in 行进方向, d_out 行进方向) → (shape_suffix, rotation) ——
def classify_logistics(d_in, d_out):
    """返回 ('straight'|'turn_cw'|'turn_ccw', rotation)。d: 0=E,90=S,180=W,270=N"""
    if d_in == d_out:
        return "straight", d_out
    if (d_out - d_in) % 360 == 90:
        return "turn_cw", (d_in + 180) % 360
    return "turn_ccw", (d_in + 270) % 360
