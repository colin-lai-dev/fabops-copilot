"""Static definitions of the fictional fab "Fab-X".

Everything here is invented. Names, codes and numbers must not identify any real company,
site, tool vendor or process (see CLAUDE.md, "安全與權限").
"""

from dataclasses import dataclass

FABS = ["FX1", "FX2"]

DEPARTMENTS = {
    "etch": "蝕刻",
    "litho": "黃光",
    "thinfilm": "薄膜",
    "diffusion": "擴散",
    "cmp": "研磨",
}
SHARED_DEPARTMENT = "shared"  # visible to every department (ADR-0002)

CLEARANCE = {0: "public", 1: "internal", 2: "confidential", 3: "restricted"}

# Fictional equipment types and vendor models per department.
EQUIPMENT_TYPES = {
    "etch": ("ETCHER", ["Aurora-E3", "Nimbus-E5"]),
    "litho": ("SCANNER", ["Lumen-S2", "Lumen-S4"]),
    "thinfilm": ("CVD", ["Strata-C1", "Strata-C3"]),
    "diffusion": ("FURNACE", ["Ember-F2", "Ember-F6"]),
    "cmp": ("POLISHER", ["Glide-P1", "Glide-P2"]),
}


@dataclass(frozen=True)
class AlarmType:
    code: str
    department: str
    name: str
    severity: str
    parameter: str  # monitored parameter
    unit: str
    limit_low: float  # SOP threshold range used in documents
    limit_high: float


# Alarm code format: <3-letter dept>-<3-letter subsystem>-<4 digits>. Invented.
ALARM_TYPES = [
    AlarmType(
        "ETC-PRS-0412", "etch", "腔體壓力異常", "critical", "chamber pressure", "mTorr", 8, 45
    ),
    AlarmType("ETC-RFP-0230", "etch", "RF 反射功率過高", "warning", "reflected power", "W", 20, 90),
    AlarmType("ETC-EPD-0118", "etch", "終點偵測逾時", "warning", "endpoint delay", "s", 5, 30),
    AlarmType("ETC-HEL-0507", "etch", "背面氦氣洩漏", "critical", "He leak rate", "sccm", 1, 6),
    AlarmType("LIT-FOC-0301", "litho", "對焦偏移", "warning", "focus offset", "nm", 15, 60),
    AlarmType("LIT-OVL-0322", "litho", "疊對誤差超限", "critical", "overlay error", "nm", 3, 12),
    AlarmType(
        "LIT-TMP-0150", "litho", "鏡組溫度漂移", "warning", "lens temperature drift", "mK", 5, 40
    ),
    AlarmType("TFM-THK-0611", "thinfilm", "膜厚超出管制", "critical", "film thickness", "nm", 2, 9),
    AlarmType(
        "TFM-GAS-0640", "thinfilm", "製程氣體流量偏差", "warning", "gas flow deviation", "%", 2, 8
    ),
    AlarmType("TFM-PRT-0655", "thinfilm", "微粒數過高", "critical", "particle count", "ea", 10, 60),
    AlarmType(
        "DIF-TMP-0702", "diffusion", "爐管溫度偏差", "critical", "zone temperature", "°C", 1, 5
    ),
    AlarmType(
        "DIF-O2C-0715", "diffusion", "氧含量偏高", "warning", "O2 concentration", "ppm", 5, 40
    ),
    AlarmType("CMP-RMV-0803", "cmp", "移除率異常", "warning", "removal rate deviation", "%", 3, 12),
    AlarmType("CMP-PAD-0810", "cmp", "研磨墊壽命到期", "info", "pad life", "wafers", 500, 3000),
    AlarmType(
        "CMP-SLR-0822", "cmp", "研磨液流量不足", "critical", "slurry flow", "ml/min", 80, 250
    ),
]

PM_TYPES = ["週保養", "月保養", "季保養", "腔體濕式清潔", "零件更換"]

PRODUCTS = ["NX-12A", "NX-12B", "MV-28C", "PW-40D", "LG-55E"]
ROUTE_STEPS = ["STI-ETCH", "GATE-LITHO", "ILD-CVD", "ANNEAL", "W-CMP", "M1-ETCH", "VIA-LITHO"]

# Demo users covering the permission combinations in ADR-0002.
DEMO_USERS = [
    # user_id, name, fabs, departments, clearance
    ("op_fx1_etch", "FX1 蝕刻作業員", ["FX1"], ["etch"], 0),
    ("eng_fx1_etch", "FX1 蝕刻工程師", ["FX1"], ["etch"], 1),
    ("eng_fx2_litho", "FX2 黃光工程師", ["FX2"], ["litho"], 1),
    ("lead_fx1_multi", "FX1 製程主任", ["FX1"], ["etch", "thinfilm", "cmp"], 2),
    ("mgr_fx2_all", "FX2 廠務經理", ["FX2"], list(DEPARTMENTS), 2),
    ("admin_all", "系統管理員", FABS, list(DEPARTMENTS), 3),
]

# Dirty-data rules (PLAN Phase 0). Canonical term -> variants used in reports.
ABBREVIATIONS = {
    "保養": ["PM"],
    "機台": ["EQP", "tool"],
    "超出管制": ["OOC"],
    "批號": ["lot"],
    "腔體": ["chamber", "CH"],
    "復機": ["recover", "back to line"],
}

# Common Chinese typos (correct -> wrong). Applied to a fraction of incident reports.
TYPOS = {
    "再次": "在次",
    "已經": "以經",
    "步驟": "部驟",
    "確認": "確任",
    "異常": "意常",
    "暫停": "站停",
}

COLLOQUIAL_OPENERS = [
    "夜班巡機的時候發現",
    "半夜突然跳 alarm，",
    "交班前剛好看到",
    "OP 回報說",
    "跟前一班一樣又出現",
]
