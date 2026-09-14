"""解析抽取结果里的引用占位值。

招标文件抽取结果中常见“见投标人须知前附表”“详见招标公告”等占位描述。
本模块从任务已转换的 Markdown 正文里查找对应章节/表格，尽量还原真实内容。
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from ..database import get_session_factory
from ..models import Task
from . import fallback_extractor

_REFERENCE_PATTERNS = [
    re.compile(r"见投标人须知前附表"),
    re.compile(r"见招标公告"),
    re.compile(r"见招标文件"),
    re.compile(r"详见招标公告"),
    re.compile(r"详见招标文件"),
    re.compile(r"详见\s*[^。；;\n]{0,24}附表"),
    re.compile(r"同投标文件递交截止时间"),
    re.compile(r"同投标(?:文件)?(?:递交)?截止时间"),
    re.compile(r"以招标文件为准"),
]

_FIELD_KEYWORDS: dict[str, list[str]] = {
    "qualifications": ["资质要求", "资格要求", "资格条件", "资质"],
    "performance_requirements": ["业绩要求", "业绩条件", "类似项目业绩", "销售业绩", "业绩"],
    "quality_standard": ["质量标准", "质量要求"],
    "technical_requirements": ["技术要求", "技术规格"],
    "evaluation_criteria": ["评标办法", "评标方法", "评审办法"],
    "bid_security_amount": ["投标保证金", "保证金金额"],
    "bid_security_deadline": ["保证金", "缴纳截止"],
    "delivery_period": ["交付期", "供货期", "交货期", "工期", "交付时间"],
    "payment_terms": ["付款方式", "支付方式", "结算方式"],
    "project_location": ["项目地点", "交货地点", "服务地点", "实施地点"],
    "tenderer_address": ["招标人地址", "联系地址"],
    "agency_contact": ["代理机构联系人", "招标代理联系人", "联系方式", "招标代理机构"],
    "contact_person": ["项目联系人", "采购人联系人", "联系人"],
    "contact_phone": ["联系电话", "电话"],
    "contact_email": ["联系邮箱", "电子邮箱"],
    "budget": ["最高限价", "预算金额", "项目预算"],
    "project_scale": ["项目规模", "建设规模"],
    "bid_location": ["开标地点", "开标会议室", "投标文件递交地点"],
    "warranty": ["质保期", "质保要求", "质量保证期", "保修期", "质保期限", "质保", "售后服务"],
    "bid_deadline": ["投标文件递交截止时间", "投标截止时间"],
    "bid_opening_time": ["开标时间"],
    "tenderer": ["招标人名称", "采购人名称", "招标人"],
    "agency_name": ["招标代理机构", "代理机构"],
}

_ITEM_NO_RE = re.compile(r"^\d+(?:\.\d+)+$")
_TOP_HEADING_RE = re.compile(r"^\d+\.(?!\d)")
_DEEP_ITEM_RE = re.compile(r"^\d+\.\d+\.\d+")
_PAGE_MARK_RE = re.compile(r"^<!--\s*page|^\d{1,3}$")

_text_cache: dict[str, tuple[int, str]] = {}

_REPLACE_IF_LONGER = {
    "project_name",
    "tenderer",
    "agency_name",
    "project_scale",
    "bid_location",
    "project_location",
}


def _load_combined_text(task_id: str) -> str:
    with get_session_factory()() as db:
        task = db.get(Task, task_id)
        if task is None or not task.work_dir:
            return ""
        work_dir = Path(task.work_dir)
    combined = work_dir / "combined.md"
    if combined.exists():
        stat = combined.stat()
        cached = _text_cache.get(task_id)
        if cached and cached[0] == stat.st_mtime_ns:
            return cached[1]
        text = combined.read_text(encoding="utf-8", errors="replace")
        if len(_text_cache) > 40:
            _text_cache.clear()
        _text_cache[task_id] = (stat.st_mtime_ns, text)
        return text
    parts: list[str] = []
    with get_session_factory()() as db:
        task = db.get(Task, task_id)
        manifest = (task.manifest or {}) if task else {}
    for entry in manifest.get("files", []):
        md_path = entry.get("md_path")
        if md_path and Path(md_path).exists():
            parts.append(Path(md_path).read_text(encoding="utf-8", errors="replace"))
    return "\n\n".join(parts)


def _extract_bid_location(text: str) -> str | None:
    """只取开标地点标签后的真实地点，避免把整个前附表抓进来。"""
    for match in re.finditer(r"(?:开标地点|投标文件递交地点|开标会议室)\s*[：:]\s*([^|\n]{2,400})", text):
        value = re.sub(r"\s+", " ", match.group(1)).strip(" ：:，,。")
        for stop in ("本项目开标过程", "参加开标的方法", "投标人于开标后", "开标过程全程", "具体操作方式"):
            index = value.find(stop)
            if index > 0:
                value = value[:index].strip(" ：:，,。")
                break
        if "。" in value and len(value) > 60:
            value = value.split("。", 1)[0] + "。"
        value = value.strip()
        if len(value) >= 2 and not _contains_reference(value):
            return _truncate(value)
    return None


def _task_package_names(task_id: str) -> set[str]:
    with get_session_factory()() as db:
        task = db.get(Task, task_id)
        if task is None or not task.work_dir:
            return set()
        packages_json = Path(task.work_dir) / "packages.json"
    if not packages_json.exists():
        return set()
    try:
        packages_data = json.loads(packages_json.read_text(encoding="utf-8"))
    except Exception:
        return set()
    names: set[str] = set()
    for package in packages_data.get("packages", []):
        name = str(package.get("subproject_dir") or package.get("分标名称") or "").strip()
        if name and name not in {"", "，包名称", "未分组"}:
            names.add(name)
    return names


def _cell(row: list[str], columns: dict[str, int], *names: str) -> str:
    for name in names:
        if name in columns and columns[name] < len(row):
            return row[columns[name]]
    return ""


def _parse_special_qualification_table(text: str, task_id: str = "") -> list[dict[str, str]]:
    """解析专用资格要求表（兼容山东/重庆等不同表头），供资质/业绩关键信息使用。"""
    lines = text.splitlines()
    header_index = None
    header_cells: list[str] = []
    for index, line in enumerate(lines):
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        if "分标名称" in cells and "业绩要求" in cells and ("厂商类型" in cells or "投标人类别" in cells):
            header_index = index
            header_cells = cells
            break
    if header_index is None:
        return []
    columns = {name: idx for idx, name in enumerate(header_cells) if name}
    required = ("分标名称", "业绩要求")
    if not all(key in columns for key in required):
        return []

    rows: list[dict[str, str]] = []
    for line in lines[header_index + 1 :]:
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        if len(cells) <= max(columns.values()):
            continue
        name = cells[columns["分标名称"]]
        if not name or name in {"分标名称", "---"} or "---" in name:
            continue
        rows.append(
            {
                "分标名称": name,
                "包号": _cell(cells, columns, "包号"),
                "投标人类别": _cell(cells, columns, "厂商类型", "投标人类别"),
                "业绩要求": cells[columns["业绩要求"]],
                "检测报告": _cell(
                    cells,
                    columns,
                    "产品型式试验报告或检测报告或鉴定报告",
                    "试验报告",
                    "检测报告",
                ),
                "认证证书": _cell(cells, columns, "3C认证证书", "认证证书"),
                "许可证": _cell(
                    cells,
                    columns,
                    "生产许可证或检测合格证(入网许可证)",
                    "许可证（生产许可证、入网许可证或CCC等）",
                    "许可证",
                ),
                "生产设备": _cell(cells, columns, "生产设备"),
                "试验设备": _cell(cells, columns, "试验设备"),
                "其他资质要求": _cell(cells, columns, "其他资质要求", "备注"),
            }
        )
    if task_id:
        names = _task_package_names(task_id)
        if names:
            rows = [row for row in rows if row["分标名称"] in names]
    return rows


def _required_cell(value: str) -> str:
    cleaned = str(value or "").strip()
    return "未要求" if cleaned in {"", "/", "-", "--"} else cleaned


def _qualification_summary(rows: list[dict[str, str]]) -> list[str]:
    result: list[str] = []
    for row in rows:
        label = row["分标名称"]
        if row.get("包号"):
            label += f"（{row['包号']}）"
        result.append(
            f"{label}：投标人类别：{_required_cell(row['投标人类别'])}；"
            f"许可证：{_required_cell(row['许可证'])}；"
            f"检测/试验报告：{_required_cell(row['检测报告'])}；"
            f"认证证书：{_required_cell(row['认证证书'])}；"
            f"生产设备：{_required_cell(row['生产设备'])}；"
            f"试验设备：{_required_cell(row['试验设备'])}；"
            f"其他资质要求：{_required_cell(row['其他资质要求'])}"
        )
    return result


def _performance_summary(rows: list[dict[str, str]]) -> list[str]:
    result: list[str] = []
    for row in rows:
        label = row["分标名称"]
        if row.get("包号"):
            label += f"（{row['包号']}）"
        result.append(f"{label}：{row['业绩要求']}")
    return result


def _extract_contact_person(text: str) -> str | None:
    """从招标公告联系方式中提取简洁联系人，优先项目负责人/业务咨询经理。"""
    for match in re.finditer(r"项目负责人\s*[：:]\s*([^\s，,。；;|&]{1,20})", text):
        value = match.group(1).strip()
        if value and "&" not in value:
            return value
    for match in re.finditer(r"(?:业务咨询|联系电话|联系方式)\s*[：:]\s*([^\n]{2,400})", text):
        block = match.group(1)
        if "异议" in block:
            continue
        names = re.findall(r"[\u4e00-\u9fff]{1,6}(?:经理|工程师|负责人|工)", block)
        if names:
            return "、".join(dict.fromkeys(names))
    for match in re.finditer(
        r"(?<!异议)(?:项目联系人|招标人联系人|采购人联系人|联系人)\s*[：:]\s*([^\s，,。；;|&]{1,20})",
        text,
    ):
        value = match.group(1).strip()
        if value and "&" not in value:
            return value
    return None


def _extract_contact_phone(text: str) -> str | None:
    for match in re.finditer(r"(?:业务咨询|联系电话|联系人电话|联系方式)\s*[：:]\s*([^\n]{2,300})", text):
        block = match.group(1)
        if "异议" in block:
            continue
        numbers = re.findall(r"((?:0\d{2,3}-)?\d{7,8})", block)
        if numbers:
            return "、".join(dict.fromkeys(numbers))
    return None


def _extract_bidder_qualification_items(text: str) -> list[str]:
    """按原文条目完整提取招标公告3.投标人资格要求。"""
    lines = text.splitlines()
    start = next(
        (
            index
            for index, line in enumerate(lines)
            if re.match(r"^\s*3[.、]\s*投标人资格要求", line)
        ),
        None,
    )
    if start is None:
        return ["详见招标公告3.投标人资格要求"]
    end = next(
        (index for index in range(start + 1, len(lines)) if re.match(r"^\s*4[.、]", lines[index])),
        len(lines),
    )
    section_lines = lines[start:end]
    items: list[str] = []
    current_label = ""
    current = ""
    in_general = False
    for line in section_lines:
        stripped = line.strip()
        if not stripped or _PAGE_MARK_RE.match(stripped):
            continue
        top = re.match(r"^(3\.\d+)\s*(.*)$", stripped)
        sub = re.match(r"^（(\d+)）\s*(.*)$", stripped)
        if top:
            if current:
                items.append(re.sub(r"\s+", " ", f"{current_label} {current}").strip())
            current_label = top.group(1)
            current = top.group(2).strip()
            in_general = current_label == "3.5"
            continue
        if sub and in_general:
            if current and current_label == "3.5" and "通用资格要求" in current:
                current = ""
            elif current:
                items.append(re.sub(r"\s+", " ", f"{current_label} {current}").strip())
            current_label = f"3.5（{sub.group(1)}）"
            current = sub.group(2).strip()
            continue
        if current:
            current += stripped
    if current:
        items.append(re.sub(r"\s+", " ", f"{current_label} {current}").strip())
    return [item for item in items if item]


def _extract_enterprise_qualifications(task_id: str, text: str, bidder_items: list[str]) -> list[str]:
    """全文搜索企业资质要求：只搜招标公告/招标文件/投标格式，排除技术规范与合同模板。"""
    enterprise_keywords = (
        "营业执照",
        "ISO",
        "质量管理体系",
        "生产许可证",
        "注册资本",
        "审计",
        "财务会计报告",
        "企业信用",
        "信用信息",
        "失信",
        "经营异常",
        "法定代表人",
        "控股",
        "关联",
        "财务状况",
        "商业信用",
        "不良行为",
        "生产场地",
        "生产设备",
        "生产人员",
        "检测能力",
        "工艺文件",
        "作业指导书",
        "出厂检测",
        "合并",
        "分立",
        "破产",
    )
    product_blockers = (
        "试验报告",
        "检测报告",
        "型式试验",
        "3C",
        "入网许可证",
        "产品有效",
    )
    result: list[str] = []
    seen: set[str] = set()
    enterprise_bidder_labels = {
        "3.5（1）",
        "3.5（3）",
        "3.5（4）",
        "3.5（5）",
        "3.5（6）",
        "3.5（7）",
        "3.5（8）",
        "3.5（11）",
        "3.5（14）",
        "3.5（15）",
    }
    for item in bidder_items:
        if any(item.startswith(label) for label in enterprise_bidder_labels):
            if item not in seen:
                seen.add(item)
                result.append(item)
    strong_keywords = (
        "营业执照",
        "ISO",
        "质量管理体系",
        "生产许可证",
        "注册资本",
        "审计",
        "财务会计报告",
        "企业信用",
        "信用信息公示",
        "高新技术企业",
        "软件企业",
        "CMMI",
        "安全生产许可证",
    )
    noise_markers = (
        "支持",
        "应支持",
        "审计管理员",
        "审计员",
        "审计分析",
        "日志审计",
        "运维审计",
        "审计记录",
        "权限",
        "角色",
        "技术参数",
        "元件名称",
        "填写规定",
        "投标人填写",
        "USB",
        "Agent",
        "工单",
        "导航菜单",
        "设备运行日志",
        "审计事件",
        "关联事件",
        "安全管理员",
        "系统管理员",
        "卖方应积极配合",
        "特授权",
        "评审得分",
        "评分因素",
        "此处粘帖",
        "我公司未被",
        "被市场监督管理机关在国家企业信用信息公示系统中列入严重违法失信企业名单或列入经营异常名录信息的",
    )

    def scan_lines(content: str) -> None:
        for line in content.splitlines():
            stripped = line.strip()
            if len(stripped) < 8 or len(stripped) > 500:
                continue
            if "&" in stripped or stripped.startswith(("|", "#")):
                continue
            if any(marker in stripped for marker in noise_markers):
                continue
            if re.match(r"^（\d+）", stripped) and "营业执照" not in stripped and "财务会计" not in stripped:
                continue
            if any(keyword in stripped for keyword in strong_keywords) and not any(
                blocker in stripped for blocker in product_blockers
            ):
                cleaned = re.sub(r"\s+", " ", stripped).strip()
                if cleaned not in seen and not any(cleaned in item for item in result):
                    seen.add(cleaned)
                    result.append(cleaned)

    if task_id:
        with get_session_factory()() as db:
            task = db.get(Task, task_id)
            work_dir = Path(task.work_dir) if task is not None and task.work_dir else None
        if work_dir is not None:
            markdown_dir = work_dir / "markdown"
            if markdown_dir.exists():
                for path in sorted(markdown_dir.glob("*.md")):
                    name = path.name
                    if any(
                        skip in name
                        for skip in (
                            "技术规范书",
                            "合同",
                            "货物清单",
                            "报价",
                            "评分",
                            "保证金",
                            "履约保函",
                            "附表7",
                            "附表8",
                            "附表9",
                            "附表10",
                        )
                    ):
                        continue
                    try:
                        scan_lines(path.read_text(encoding="utf-8", errors="replace"))
                    except OSError:
                        continue
    else:
        scan_lines(text)
    return result[:60]


def _build_qualifications_payload(rows: list[dict[str, str]], text: str, task_id: str = "") -> dict:
    """资质要求结构化：产品资质表格 / 企业资质全文条目 / 投标人资格原文条目。"""
    columns = [
        "分标名称",
        "包号",
        "投标人类别",
        "检测/试验报告",
        "认证证书",
        "许可证",
        "生产设备",
        "试验设备",
        "其他资质要求",
    ]
    column_keys = {
        "分标名称": "分标名称",
        "包号": "包号",
        "投标人类别": "投标人类别",
        "检测/试验报告": "检测报告",
        "认证证书": "认证证书",
        "许可证": "许可证",
        "生产设备": "生产设备",
        "试验设备": "试验设备",
        "其他资质要求": "其他资质要求",
    }
    table_rows = [[row.get(column_keys[column], "") for column in columns] for row in rows]
    bidder_items = _extract_bidder_qualification_items(text)
    enterprise_items = _extract_enterprise_qualifications(task_id, text, bidder_items)
    return {
        "product_table": {"columns": columns, "rows": table_rows},
        "enterprise": enterprise_items,
        "bidder": bidder_items,
    }


def _build_qualification_groups(rows: list[dict[str, str]], text: str, task_id: str = "") -> list[str]:
    payload = _build_qualifications_payload(rows, text, task_id)
    return [
        f"产品资质：{len(payload['product_table']['rows'])}个分标，详见专用资格要求表",
        f"企业资质：{len(payload['enterprise'])}项",
        f"投标人资格要求：{len(payload['bidder'])}项",
    ]


def _collect_warranty_summary(task_id: str) -> str | None:
    """从各包合同专用条款提取质保期，返回按包汇总结果。"""
    with get_session_factory()() as db:
        task = db.get(Task, task_id)
        if task is None or not task.work_dir:
            return None
        work_dir = Path(task.work_dir)

    name_by_stem: dict[str, str] = {}
    packages_json = work_dir / "packages.json"
    if packages_json.exists():
        try:
            packages_data = json.loads(packages_json.read_text(encoding="utf-8"))
            for package in packages_data.get("packages", []):
                source = str(package.get("source_archive") or "")
                stem = Path(source).stem
                name = str(package.get("subproject_dir") or package.get("分标名称") or stem)
                name_by_stem[stem] = name
        except Exception:
            pass

    mapping: dict[str, set[int]] = {}
    root = work_dir / "packages_md"
    if root.exists():
        for folder in root.iterdir():
            if not folder.is_dir():
                continue
            months: set[int] = set()
            for md_path in folder.rglob("*.md"):
                try:
                    text = md_path.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    continue
                months.update(
                    int(value)
                    for value in re.findall(r"质量保证期为从合同货物通过验收后(\d+)个月", text)
                )
            if months:
                mapping[name_by_stem.get(folder.name, folder.name)] = months

    if not mapping:
        combined = _load_combined_text(task_id)
        months = [int(value) for value in re.findall(r"质量保证期为从合同货物通过验收后(\d+)个月", combined)]
        if not months:
            return None
        mapping = {"本项目": set(months)}

    all_months = {month for values in mapping.values() for month in values}
    if len(all_months) == 1:
        month = next(iter(all_months))
        return f"{month}个月（从合同货物通过验收后起算，以合同专用条款为准）"

    groups: dict[int, list[str]] = {}
    for name, months in mapping.items():
        for month in months:
            groups.setdefault(month, []).append(name)
    parts = [
        f"{month}个月（{'、'.join(sorted(set(groups[month])))}）"
        for month in sorted(groups, reverse=True)
    ]
    return "；".join(parts) + "；以各包合同专用条款为准"


def looks_like_reference(value: Any) -> bool:
    if value is None:
        return False
    text = str(value).strip()
    if not text or len(text) > 160:
        return False
    return any(pattern.search(text) for pattern in _REFERENCE_PATTERNS)


def _contains_reference(value: str) -> bool:
    return any(pattern.search(value) for pattern in _REFERENCE_PATTERNS)


def resolve_references(task_id: str, data: dict) -> dict:
    """就地解析 data 中的引用占位值，返回解析后的数据。"""
    if not data:
        return data
    text = _load_combined_text(task_id)
    if not text:
        return data
    for field, item in data.items():
        if not isinstance(item, dict) or "primary_value" not in item:
            continue
        value = item["primary_value"]
        if isinstance(value, list):
            resolved = [
                _resolve_value(field, part, text, data, task_id) if looks_like_reference(part) else part
                for part in value
            ]
            if resolved != value:
                item["primary_value"] = resolved
                item["reference_resolved"] = True
        elif looks_like_reference(value):
            new_value = _resolve_value(field, value, text, data, task_id)
            if new_value != value:
                item["primary_value"] = new_value
                item["reference_resolved"] = True
    return data


def enrich_missing_fields(task_id: str, data: dict) -> dict:
    """用改进后的规则抽取补充缺失/占位字段，不覆盖已有真实值。"""
    if not data:
        return data
    text = _load_combined_text(task_id)
    if not text:
        return data
    raw = fallback_extractor.extract_file(text, "combined.md")
    for field in fallback_extractor.FIELD_LABELS:
        item = data.get(field)
        current = item.get("primary_value") if isinstance(item, dict) else None
        candidate = raw.get(field)
        if not candidate:
            continue
        value = candidate.get("primary_value")
        if value is None or str(value).strip() == "" or looks_like_reference(value):
            continue
        # 已有内容（包括引用占位）不覆盖，引用值交给 resolve_references 解析；
        # 机构/名称类字段允许用更长的完整值修复 PDF 换行造成的截断。
        if current is not None and str(current).strip():
            if fallback_extractor._is_junk(str(current)):
                data[field] = candidate
                continue
            if field in _REPLACE_IF_LONGER and len(str(value)) > len(str(current)) + 5:
                data[field] = candidate
            continue
        data[field] = candidate
    current_tech = data.get("technical_requirements", {}).get("primary_value") if isinstance(data.get("technical_requirements"), dict) else None
    if current_tech is None or not str(current_tech).strip():
        tech = _extract_technical_spec(task_id)
        if tech:
            data["technical_requirements"] = {
                "primary_value": tech,
                "confidence": 0.78,
                "reference_resolved": True,
                "evidence": {"source_file": "技术规范书", "page": 1, "text": ""},
            }
    current_warranty = data.get("warranty", {}).get("primary_value") if isinstance(data.get("warranty"), dict) else None
    warranty_text = str(current_warranty) if current_warranty is not None else ""
    if len(warranty_text) < 60:
        warranty = _extract_warranty(text)
        if warranty and len(warranty) > len(warranty_text) + 10:
            data["warranty"] = {
                "primary_value": warranty,
                "confidence": 0.85,
                "reference_resolved": True,
                "evidence": {"source_file": "技术规范书/招标文件", "page": 1, "text": ""},
            }
    warranty_summary = _collect_warranty_summary(task_id)
    if warranty_summary and (
        len(warranty_text) < 60
        or "个月" not in warranty_text
        or "指合同货物验收后" in warranty_text
    ):
        data["warranty"] = {
            "primary_value": warranty_summary,
            "confidence": 0.9,
            "reference_resolved": True,
            "evidence": {"source_file": "合同专用条款", "page": 1, "text": ""},
        }
    current_contact = data.get("contact_person", {}).get("primary_value") if isinstance(data.get("contact_person"), dict) else None
    contact_text = str(current_contact or "")
    if not contact_text or "&" in contact_text or contact_text.startswith("|"):
        contact = _extract_contact_person(text)
        if contact:
            data["contact_person"] = {
                "primary_value": contact,
                "confidence": 0.9,
                "reference_resolved": True,
                "evidence": {"source_file": "招标公告联系方式", "page": 1, "text": ""},
            }
    current_phone = data.get("contact_phone", {}).get("primary_value") if isinstance(data.get("contact_phone"), dict) else None
    phone_text = str(current_phone or "")
    if not phone_text or "&" in phone_text:
        phone = _extract_contact_phone(text)
        if phone:
            data["contact_phone"] = {
                "primary_value": phone,
                "confidence": 0.9,
                "reference_resolved": True,
                "evidence": {"source_file": "招标公告联系方式", "page": 1, "text": ""},
            }
    agency_item = data.get("agency_name")
    if isinstance(agency_item, dict):
        agency_value = str(agency_item.get("primary_value") or "")
        if "项目负责人" in agency_value or "联系人" in agency_value:
            data["agency_name"] = {
                "primary_value": re.split(r"项目负责人|联系人|地址", agency_value)[0].strip(" ：:，,。"),
                "confidence": 0.9,
                "reference_resolved": True,
                "evidence": {"source_file": "招标公告联系方式", "page": 1, "text": ""},
            }
    _enrich_from_appendices(task_id, data)
    _refresh_long_fields(task_id, data, text)
    rows = _parse_special_qualification_table(text, task_id)
    if rows:
        qualification_item = data.get("qualifications")
        if isinstance(qualification_item, dict):
            qualification_item["structured"] = _build_qualifications_payload(rows, text, task_id)
            if not isinstance(qualification_item.get("primary_value"), list):
                qualification_item["primary_value"] = _build_qualification_groups(rows, text, task_id)
    return data


_LONG_FIELD_THRESHOLDS = {
    "qualifications": 300,
    "performance_requirements": 300,
    "technical_requirements": 300,
    "bid_location": 100,
    "project_location": 100,
    "delivery_period": 120,
    "project_scale": 200,
    "warranty": 200,
}

_ALLOW_REF_IN_LONG = {"qualifications", "performance_requirements", "bid_location"}


def _refresh_long_fields(task_id: str, data: dict, text: str) -> None:
    """长文本字段识别过短时，从招标公告/前附表重新抓完整内容替换截断值。"""
    quality = data.get("quality_standard", {}).get("primary_value") if isinstance(data.get("quality_standard"), dict) else None
    if quality and any(token in str(quality) for token in ("（盖章）", "采购项目编号", "____", "年月日")):
        data.pop("quality_standard", None)
    for field, threshold in _LONG_FIELD_THRESHOLDS.items():
        item = data.get(field)
        current = item.get("primary_value") if isinstance(item, dict) else None
        parts = current if isinstance(current, list) else ([current] if current is not None else [])
        current_text = "".join(str(part) for part in parts if part is not None)
        if field == "bid_location":
            resolved = _extract_bid_location(text)
            if resolved:
                data[field] = {
                    "primary_value": resolved,
                    "confidence": 0.9,
                    "reference_resolved": True,
                    "evidence": {"source_file": "招标文件/招标公告", "page": 1, "text": ""},
                }
                continue
        if field in {"qualifications", "performance_requirements"}:
            rows = _parse_special_qualification_table(text, task_id)
            if rows:
                resolved = (
                    _performance_summary(rows)
                    if field == "performance_requirements"
                    else _build_qualification_groups(rows, text, task_id)
                )
                data[field] = {
                    "primary_value": resolved,
                    "confidence": 0.9,
                    "reference_resolved": True,
                    "evidence": {"source_file": "招标公告附件2：专用资格要求", "page": 1, "text": ""},
                }
                continue
        if field == "warranty" and "个月" in current_text:
            continue
        if len(current_text) >= threshold:
            continue
        keywords = _FIELD_KEYWORDS.get(field)
        if not keywords:
            continue
        resolved = _resolve_from_annotation_table(text, keywords)
        if not resolved:
            resolved = _find_announcement_content(text, keywords)
        if not resolved:
            resolved = _find_paragraph_content(text, keywords)
        if not resolved or len(resolved) <= len(current_text) + 20:
            continue
        if field not in _ALLOW_REF_IN_LONG and _contains_reference(resolved):
            continue
        if field == "performance_requirements":
            resolved = _post_process_performance(resolved)
        data[field] = {
            "primary_value": resolved,
            "confidence": 0.85,
            "reference_resolved": True,
            "evidence": {"source_file": "招标文件/招标公告", "page": 1, "text": ""},
        }


def _enrich_from_appendices(task_id: str, data: dict) -> None:
    text = _load_combined_text(task_id)
    if not text:
        return
    current_security = data.get("bid_security_amount", {}).get("primary_value") if isinstance(data.get("bid_security_amount"), dict) else None
    if current_security is None or not str(current_security).strip():
        rows: list[str] = []
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped.startswith("|"):
                continue
            cells = [cell.strip() for cell in stripped.strip("|").split("|")]
            if (
                len(cells) >= 4
                and re.match(r"^\d+$", cells[0])
                and re.match(r"^[\u4e00-\u9fff][\u4e00-\u9fffA-Za-z0-9\-（）()]{1,30}$", cells[2])
                and cells[2] != "分标名称"
                and not re.match(r"^包\d", cells[2])
                and cells[3]
            ):
                if re.match(r"^[\d.]+$", cells[3]):
                    rows.append(f"{cells[2]}：{cells[3]}万元")
        if rows:
            data["bid_security_amount"] = {
                "primary_value": "；".join(rows[:12]),
                "confidence": 0.85,
                "reference_resolved": True,
                "evidence": {"source_file": "附表5：保证金", "page": 1, "text": ""},
            }
    current_budget = data.get("budget", {}).get("primary_value") if isinstance(data.get("budget"), dict) else None
    if current_budget is None or not str(current_budget).strip():
        total = 0.0
        found = False
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped.startswith("|") or "行限价" in stripped:
                continue
            cells = [cell.strip() for cell in stripped.strip("|").split("|")]
            if len(cells) >= 8:
                match = re.match(r"^([\d.]+)$", cells[7])
                if match:
                    total += float(match.group(1))
                    found = True
        if found:
            data["budget"] = {
                "primary_value": f"总最高限价约 {total:.2f} 万元（详见附表4）",
                "confidence": 0.85,
                "reference_resolved": True,
                "evidence": {"source_file": "附表4：最高限价", "page": 1, "text": ""},
            }


def _extract_technical_spec(task_id: str) -> str | None:
    with get_session_factory()() as db:
        task = db.get(Task, task_id)
        manifest = (task.manifest or {}) if task else {}
    for entry in manifest.get("files", []):
        md_path = entry.get("md_path") or ""
        if "技术规范书" not in md_path and "技术规范" not in md_path:
            continue
        path = Path(md_path)
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        marker = text.find("技术参数特性表")
        start = marker if marker >= 0 else text.find("技术规范书")
        if start < 0:
            continue
        body = text[start : start + 2600]
        lines = [
            line.strip()
            for line in body.splitlines()
            if line.strip() and not re.match(r"^<!--\s*page|^\d{1,3}$", line.strip())
        ]
        joined = re.sub(r"\s+", " ", " ".join(lines)).strip()
        if joined:
            return joined[:1200]
    return None


def _extract_warranty(text: str) -> str | None:
    """从技术规范书/招标文件中提取质保期、售后服务等具体内容。"""
    lines = text.splitlines()
    candidates: list[str] = []
    for index, line in enumerate(lines):
        stripped = line.strip()
        if "质保" not in stripped and "保修" not in stripped:
            continue
        if "&warr_period&" in stripped or "质保期：指" in stripped or "质量保证期：指" in stripped:
            continue
        if re.search(r"不低于.{0,8}(?:年|月|日)", stripped) or re.search(r"(?:质量保证期|质保期|保修期)\s*[：:为]", stripped):
            candidates.append((index, stripped))
    if not candidates:
        for index, line in enumerate(lines):
            stripped = line.strip()
            if ("质保" in stripped or "保修" in stripped) and re.search(r"(?:年|月)", stripped) and "&warr_period&" not in stripped:
                candidates.append((index, stripped))
    if not candidates:
        return None
    index, first = candidates[0]
    collected = [first]
    for next_line in lines[index + 1 : index + 14]:
        stripped = next_line.strip()
        if not stripped or re.match(r"^第[一二三四五六七八九十\d]+[章节]", stripped):
            break
        if re.match(r"^<!--|^\d{1,3}$", stripped):
            continue
        collected.append(stripped)
    joined = re.sub(r"\s+", " ", " ".join(collected)).strip()
    return joined[:700] if joined else None


def _resolve_value(field: str, value: Any, text: str, data: dict, task_id: str = "") -> Any:
    raw = str(value)
    if field == "bid_location":
        resolved_location = _extract_bid_location(text)
        if resolved_location:
            return resolved_location
    if field in {"qualifications", "performance_requirements"}:
        rows = _parse_special_qualification_table(text, task_id)
        if rows:
            return (
                _performance_summary(rows)
                if field == "performance_requirements"
                else _build_qualification_groups(rows, text, task_id)
            )
    if "同投标" in raw and "截止时间" in raw:
        deadline = _resolve_same_deadline(data, text)
        if deadline:
            return deadline
    keywords = _FIELD_KEYWORDS.get(field)
    if not keywords:
        return value
    resolved = _resolve_from_annotation_table(text, keywords)
    if resolved:
        if field == "tenderer":
            trimmed = _trim_tenderer(resolved)
            if trimmed:
                return trimmed
        if field == "performance_requirements":
            resolved = _post_process_performance(resolved)
        return resolved
    resolved = _find_paragraph_content(text, keywords)
    if not resolved or _contains_reference(resolved):
        resolved = _find_table_row_content(text, keywords)
    if resolved and (
        "评审" in resolved
        or "否决" in resolved
        or "评分" in resolved
        or "不能接受" in resolved
        or "不满足招标文件要求" in resolved
    ):
        return value
    if field == "performance_requirements" and resolved:
        resolved = _post_process_performance(resolved)
    return resolved or value


_PERF_KEYWORDS = ("业绩", "案例", "经验", "合同", "供货", "销售")


def _post_process_performance(resolved: str) -> str:
    """从资格要求段落里只保留真正属于业绩/案例/供货的子条目。"""
    if not resolved:
        return resolved
    parts = re.split(r"(?=\d+\.\d+\.\d+\.)", resolved)
    selected = [
        part.strip()
        for part in parts
        if re.match(r"^\d+\.\d+\.\d+\.", part.strip()) and any(keyword in part for keyword in _PERF_KEYWORDS)
    ]
    if selected:
        return " ".join(selected)
    return resolved


def _resolve_from_annotation_table(text: str, keywords: list[str]) -> str | None:
    blocks = _parse_annotation_blocks(text) + _parse_annotation_table_blocks(text)
    # 1) 条目名称匹配且内容为真实值。
    for block in blocks:
        if not _name_matches(block["name"], keywords):
            continue
        content = _join_block_content(block["content"])
        if content and not _contains_reference(content):
            return _truncate(content)
    # 2) 条目名称匹配但内容是引用时，继续去正文找真实内容。
    for block in blocks:
        if not _name_matches(block["name"], keywords):
            continue
        content = _join_block_content(block["content"])
        if content and _contains_reference(content):
            followed = _follow_reference(content, text, keywords)
            if followed and not _contains_reference(followed):
                return followed
    # 3) 名称未命中但条目内容里出现关键词且本身是引用（如代理机构联系方式）。
    for block in blocks:
        if _name_matches(block["name"], keywords):
            continue
        content = _join_block_content(block["content"])
        if content and _contains_reference(content) and any(keyword in content for keyword in keywords):
            followed = _follow_reference(content, text, keywords)
            if followed and not _contains_reference(followed):
                return followed
    return None


def _name_matches(name: str, keywords: list[str]) -> bool:
    for keyword in keywords:
        if name == keyword:
            return True
        if name.startswith(keyword) or name.endswith(keyword):
            return True
        if keyword in name and len(name) <= 12:
            return True
    return False


def _parse_annotation_blocks(text: str) -> list[dict[str, Any]]:
    start = text.find("投标人须知前附表")
    if start < 0:
        return []
    body = text[start : start + 60000]
    blocks: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    for line in body.splitlines():
        stripped = line.strip()
        if _ITEM_NO_RE.match(stripped):
            if current:
                blocks.append(current)
            current = {"no": stripped, "name": "", "content": []}
            continue
        if current is None:
            continue
        if not current["name"]:
            if stripped and not stripped.startswith(("条款号", "条款名称", "编列内容", "<!--", "■", "□")):
                current["name"] = stripped
            continue
        if stripped and not _PAGE_MARK_RE.match(stripped) and not stripped.startswith(("条款号", "条款名称", "编列内容", "<!--")):
            current["content"].append(stripped)
    if current:
        blocks.append(current)
    return blocks


def _parse_annotation_table_blocks(text: str) -> list[dict[str, Any]]:
    start = text.find("投标人须知前附表")
    if start < 0:
        return []
    blocks: list[dict[str, Any]] = []
    for line in text[start : start + 60000].splitlines():
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        if len(cells) < 3 or not _ITEM_NO_RE.match(cells[0]):
            continue
        blocks.append({"no": cells[0], "name": cells[1], "content": cells[2:]})
    return blocks


def _join_block_content(lines: list[str]) -> str:
    cleaned: list[str] = []
    for line in lines:
        if line.startswith(("■", "□")) and cleaned and cleaned[-1].endswith(("：", ":")):
            cleaned[-1] = f"{cleaned[-1]}{line}"
        else:
            cleaned.append(line)
    return " ".join(cleaned).strip()


def _follow_reference(reference: str, text: str, keywords: list[str]) -> str | None:
    if "招标公告" in reference or "公告" in reference:
        return _find_announcement_content(text, keywords)
    return _find_paragraph_content(text, keywords)


def _find_announcement_content(text: str, keywords: list[str]) -> str | None:
    if keywords and keywords[0] in ("代理机构联系人", "招标代理联系人", "联系方式", "招标代理机构"):
        return _find_agency_contact(text)
    start = _find_announcement_start(text)
    if start < 0:
        return None
    end_match = re.search(r"^第二章", text[start:], re.M)
    end = start + (end_match.start() if end_match else min(30000, len(text) - start))
    return _find_paragraph_content(text[start:end], keywords)


def _find_announcement_start(text: str) -> int:
    offset = 0
    for line in text.splitlines(keepends=True):
        stripped = line.strip()
        if (
            stripped.endswith("招标公告")
            and len(stripped) >= 12
            and "__" not in stripped
            and "#" not in stripped
            and "/" not in stripped
            and not re.match(r"^第[一二三四五六七八九十\d]+章", stripped)
        ):
            return offset
        offset += len(line)
    matches = list(re.finditer(r"^第一章\s*招标公告\s*$", text, re.M))
    if matches:
        return matches[-1].start()
    return text.find("招标公告")


def _find_agency_contact(text: str) -> str | None:
    lines = text.splitlines()
    contact_start = 0
    for index, line in enumerate(lines):
        stripped = line.strip()
        if re.match(r"^\d+\.", stripped) and "联系" in stripped:
            contact_start = index
            break
    for index in range(contact_start, len(lines)):
        line = lines[index]
        if "招标代理机构" not in line or "名称" in line:
            continue
        collected = [line.strip()]
        for next_line in lines[index + 1 : index + 12]:
            stripped = next_line.strip()
            if not stripped or _TOP_HEADING_RE.match(stripped) or stripped.startswith("<!--"):
                break
            if any(key in stripped for key in ("地址", "邮编", "负责人", "电话", "邮箱", "电子邮箱")):
                collected.append(stripped)
        content = " ".join(collected)
        if content and not looks_like_reference(content):
            return _truncate(content)
    return None


def _find_paragraph_content(text: str, keywords: list[str]) -> str | None:
    lines = text.splitlines()
    candidates: list[tuple[int, str]] = []
    for index, line in enumerate(lines):
        stripped = line.strip()
        if len(stripped) <= 4 or _PAGE_MARK_RE.match(stripped):
            continue
        if any(keyword in stripped for keyword in keywords):
            candidates.append((index, stripped))
    if not candidates:
        return None
    candidates.sort(key=lambda item: (0 if _is_label_line(item[1], keywords) else 1, _item_rank(item[1]), item[0]))
    for index, _ in candidates[:6]:
        collected: list[str] = []
        for next_line in lines[index : index + 60]:
            stripped = next_line.strip()
            if not stripped:
                continue
            if _PAGE_MARK_RE.match(stripped):
                continue
            if _TOP_HEADING_RE.match(stripped) and collected:
                break
            collected.append(stripped)
        content = " ".join(collected)
        if content and not looks_like_reference(content):
            return _truncate(content)
    return None


def _is_label_line(line: str, keywords: list[str]) -> bool:
    match = re.split(r"[:：]", line, maxsplit=1)
    if len(match) < 2:
        return False
    label = match[0].strip()
    if "其他" in label or "异议" in label:
        return False
    return bool(label) and len(label) <= 12 and any(keyword in label for keyword in keywords)


def _find_table_row_content(text: str, keywords: list[str]) -> str | None:
    header_like = {"交货期", "交货地点", "交货方式", "货物名称", "货物描述", "单位", "数量", "税率", "单价", "备注", "说明"}
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        if len(cells) < 2:
            continue
        for index, cell in enumerate(cells):
            if any(keyword in cell for keyword in keywords) and index < len(cells) - 1:
                candidates = cells[index + 1 :]
                value = next(
                    (item.strip() for item in candidates if item.strip() and item.strip() not in header_like),
                    "",
                )
                if value and not _contains_reference(value) and len(value) >= 2:
                    return _truncate(value)
    return None


def _trim_tenderer(resolved: str) -> str | None:
    match = re.search(r"招标人\s*[:：]\s*([^：:\n]{2,120})", resolved)
    if not match:
        return None
    name = re.split(r"\s+(?:地址|招标代理|联系人)|招标代理机构", match.group(1))[0].strip(" ，,、")
    return name or None


def _resolve_same_deadline(data: dict, text: str) -> str | None:
    deadline = data.get("bid_deadline")
    if isinstance(deadline, dict):
        pv = deadline.get("primary_value")
        if pv and str(pv).strip() and not looks_like_reference(pv):
            return str(pv).strip()
    match = re.search(r"投标文件递交(?:的)?截止时间(?:（[^）]*）)?[为是]?\s*[：:]*\s*([^\n|]{4,80})", text)
    if match:
        return _clean_cell(match.group(1))
    return None


def _item_rank(line: str) -> int:
    if _DEEP_ITEM_RE.match(line):
        return 0
    if re.match(r"^\d+\.\d+\.?", line):
        return 1
    if re.match(r"^\d+\.", line):
        return 2
    return 3


def _truncate(value: str) -> str:
    value = re.sub(r"\s+", " ", value).strip()
    return value[:5000]


def _clean_cell(value: str) -> str | None:
    cleaned = value.strip().strip("|").strip()
    cleaned = re.sub(r"^[（(]\d+[)）][、.]?\s*", "", cleaned)
    cleaned = re.sub(r"^\d+[、.]\s*", "", cleaned)
    cleaned = re.sub(r"^[：:]\s*", "", cleaned)
    cleaned = cleaned.rstrip("；;。").strip()
    if not cleaned or cleaned in {"/", "-", "--", "无", "略"}:
        return None
    return cleaned
