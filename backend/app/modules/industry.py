"""行业自动检测。

检测规则与需求文档 4.3.4 保持一致，同时提供 BiaoShu-SKILL 行业代码映射。
"""
from __future__ import annotations

INDUSTRY_KEYWORDS: dict[str, list[str]] = {
    "IT": ["软件", "系统", "平台", "信息化", "数据", "互联网", "智能", "集成"],
    "建筑": ["工程", "施工", "建筑", "建设", "总承包", "土建", "装修", "市政"],
    "医疗": ["医疗", "设备", "器械", "医院", "健康", "药品", "康复"],
    "能源": ["电力", "新能源", "光伏", "风电", "储能", "电网", "能源"],
    "交通": ["道路", "桥梁", "交通", "公路", "铁路", "市政", "信号"],
    "环保": ["环保", "环境", "污水处理", "固废", "生态", "监测"],
    "教育": ["学校", "教育", "培训", "智慧校园", "教学", "课程"],
    "金融": ["金融", "银行", "保险", "证券", "支付", "信贷"],
}

BIAOSHU_CODE_MAP = {
    "IT": "it_information",
    "建筑": "construction",
    "医疗": "medical",
    "教育": "education",
    "通用": "general",
}


def detect_industry(text: str) -> str:
    if not text:
        return "通用"
    scores: dict[str, int] = {}
    for industry, keywords in INDUSTRY_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw in text)
        if score > 0:
            scores[industry] = score
    if not scores:
        return "通用"
    return max(scores, key=scores.get)


def biaoshu_code(industry_label: str) -> str:
    return BIAOSHU_CODE_MAP.get(industry_label, "general")
