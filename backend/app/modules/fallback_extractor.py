"""内置规则抽取器。

当 tender-extract 服务不可用时，使用正则规则从预处理后的 Markdown 中抽取
需求文档定义的 26 个核心字段，并保留文件、页码与原文证据。
"""
from __future__ import annotations

import json
import re
from pathlib import Path

FIELD_LABELS = {
    "project_name": "项目名称",
    "bid_number": "招标编号",
    "budget": "项目预算/最高限价",
    "bid_deadline": "投标截止时间",
    "bid_opening_time": "开标时间",
    "bid_location": "开标地点",
    "qualifications": "资质要求列表",
    "evaluation_criteria": "评标办法",
    "performance_requirements": "业绩要求",
    "technical_requirements": "技术要求",
    "contact_person": "联系人",
    "contact_phone": "联系电话",
    "contact_email": "联系邮箱",
    "bid_security_amount": "投标保证金金额",
    "bid_security_deadline": "保证金缴纳截止时间",
    "bid_validity_period": "投标有效期",
    "tenderer": "招标人名称",
    "tenderer_address": "招标人地址",
    "agency_name": "招标代理机构名称",
    "agency_contact": "代理机构联系人",
    "project_location": "项目地点",
    "project_scale": "项目规模",
    "delivery_period": "交付/工期要求",
    "quality_standard": "质量标准",
    "payment_terms": "付款方式",
    "bid_format_requirements": "标书格式要求",
    "warranty": "质保期/质保要求",
}

_AMOUNT_RE = r"([\d,，]+(?:\.\d+)?)\s*(万元|万|元|人民币)?"
_JUNK_RE = re.compile(
    r"&[^&\n]{1,30}&|^XX+$|^\*+$|^[-—_]+$|^待填|^（填写|^填写|^（如有）|^null$|^None$|^暂无|^未填|^（待定）",
    re.I,
)


def _normalize_amount(raw: str) -> float | None:
    match = re.search(r"([\d,，]+(?:\.\d+)?)\s*(万元|万|元)?", raw)
    if not match:
        return None
    number = float(match.group(1).replace(",", "").replace("，", ""))
    unit = match.group(2) or ""
    if unit in {"万元", "万"}:
        number *= 10000
    return round(number, 2)


def _is_junk(value: str) -> bool:
    text = str(value).strip()
    if not text:
        return True
    return bool(_JUNK_RE.search(text))


def _extract_project_name_from_title(text: str) -> str:
    """从“×××招标公告 / ×××招标文件”标题行提取项目名称。"""
    for line in text.splitlines():
        line = line.strip()
        if "__" in line or "#" in line or "/" in line or "文档" in line:
            continue
        if line.endswith("招标公告"):
            name = line[: -len("招标公告")].strip()
        elif line.endswith("招标文件"):
            name = line[: -len("招标文件")].strip()
        else:
            continue
        if 6 <= len(name) <= 80 and not _is_junk(name):
            return name
    return ""


def _normalize_datetime(raw: str) -> str:
    text = raw.strip()
    match = re.search(
        r"(\d{4})\s*[年\-/.]\s*(\d{1,2})\s*[月\-/.]\s*(\d{1,2})\s*日?号?\s*"
        r"(?:(\d{1,2})\s*[:点时]\s*(\d{1,2})\s*分?)?",
        text,
    )
    if not match:
        return text.strip(" ：:，,。")
    year, month, day = int(match.group(1)), int(match.group(2)), int(match.group(3))
    hour = int(match.group(4)) if match.group(4) else 23
    minute = int(match.group(5)) if match.group(5) else 59
    return f"{year:04d}-{month:02d}-{day:02d} {hour:02d}:{minute:02d}"


def _find_page(text: str, index: int) -> int:
    prefix = text[:index]
    matches = list(re.finditer(r"<!--\s*page:\s*(\d+)\s*-->", prefix))
    return int(matches[-1].group(1)) if matches else 1


def _evidence(text: str, match: re.Match) -> tuple[str, int]:
    start = max(match.start() - 40, 0)
    end = min(match.end() + 120, len(text))
    snippet = text[start:end].replace("\n", " ").strip()
    return snippet[:260], _find_page(text, match.start())


def _field(value, confidence: float, source_file: str, text: str, match: re.Match | None) -> dict:
    if match is None:
        evidence = {"source_file": source_file, "page": 1, "text": ""}
    else:
        snippet, page = _evidence(text, match)
        evidence = {"source_file": source_file, "page": page, "text": snippet}
    return {"primary_value": value, "confidence": round(float(confidence), 4), "evidence": evidence}


def _first(pattern: str, text: str) -> re.Match | None:
    return re.search(pattern, text, re.I)


def _section_text(text: str, trigger: str, max_chars: int = 400) -> str:
    """从触发行之后抓取一段正文，直到下一个明显的标题或空段落。"""
    lines = text.splitlines()
    for idx, line in enumerate(lines):
        if trigger in line and line.count(".") < 4:
            collected = line.strip()
            for next_line in lines[idx + 1 : idx + 80]:
                stripped = next_line.strip()
                if not stripped:
                    continue
                if re.match(
                    r"^#{1,6}\s|^第[一二三四五六七八九十\d]+[章节]|^[一二三四五六七八九十]+、|^\d+[．.]\s*[^0-9]",
                    stripped,
                ):
                    break
                collected += stripped
                if len(collected) >= max_chars:
                    break
            return collected[: max_chars + 100]
    return ""


def _collect_qualifications(text: str, trigger: str) -> list[str]:
    section = _section_text(text, trigger, max_chars=1200)
    items: list[str] = []
    keywords = ("资质", "认证", "证书", "许可证", "资格", "许可")
    for part in re.split(r"[；;\n]", section):
        part = part.strip()
        if any(kw in part for kw in keywords) and 4 <= len(part) <= 160:
            item = re.sub(r"^[·•\-—\d．.]+\s*", "", part)
            item = re.sub(rf"^{trigger}\s*[：:]\s*", "", item)
            if item not in items:
                items.append(item)
    return items[:10]


FORMAT_SECTION_KEYWORDS = [
    "商务投标文件",
    "商务文件",
    "商务标",
    "商务部分",
    "技术投标文件",
    "技术文件",
    "技术标",
    "技术部分",
    "价格投标文件",
    "价格文件",
    "报价文件",
    "报价书",
    "资格文件",
    "资格预审文件",
    "投标函",
    "开标一览表",
    "报价明细表",
    "偏差表",
    "保证金明细表",
]

FORMAT_TEMPLATE_KEYWORDS = [
    "投标函",
    "开标一览表",
    "货物清单行报价暨投标报价汇总表",
    "报价明细表",
    "分项报价表",
    "商务偏差表",
    "技术偏差表",
    "偏差表",
    "投标保证金明细表",
    "履约保函",
    "结清款保函",
    "承诺函",
]

FORMAT_REQUIREMENT_PATTERNS = [
    (r"整体电子签章|电子签章|盖章", "电子签章"),
    (r"加密", "加密上传"),
    (r"份数|正本|副本", "份数"),
    (r"装订", "装订"),
    (r"密封", "密封"),
    (r"电子投标文件|ECP2?\.0|渝电数智", "电子平台"),
    (r"目录结构|书签", "目录书签"),
    (r"投标工具", "投标工具"),
]

FORMAT_SECTION_CANONICAL = {
    "商务投标文件": "商务文件",
    "商务文件": "商务文件",
    "商务标": "商务文件",
    "商务部分": "商务文件",
    "技术投标文件": "技术文件",
    "技术文件": "技术文件",
    "技术标": "技术文件",
    "技术部分": "技术文件",
    "价格投标文件": "价格文件",
    "价格文件": "价格文件",
    "报价文件": "价格文件",
    "报价书": "价格文件",
    "资格文件": "资格文件",
    "资格预审文件": "资格文件",
    "投标函": "投标函",
    "开标一览表": "开标一览表",
    "报价明细表": "报价明细表",
    "偏差表": "偏差表",
    "保证金明细表": "保证金明细表",
}


def _extract_bid_format(text: str) -> dict:
    lines = text.splitlines()
    section_start = None
    for idx, line in enumerate(lines):
        if re.search(r"^第[一二三四五六七八九十\d]+章\s*投标文件格式|^投标文件格式|技术文件制作及递交要求|投标文件编制要求", line):
            section_start = idx
            break

    chapter_lines = lines[section_start:] if section_start is not None else lines
    commercial_raw = _slice_section(chapter_lines, "商务部分（单独成册）", ("技术部分（单独成册）",))
    technical_raw = _slice_section(
        chapter_lines,
        "技术部分（单独成册）",
        ("投标保证保险（责任要求）", "投标保证金银行保函（格式）", "投标保证保险及保函", "投标保函（格式）"),
    )

    section_lines: list[str] = []
    if section_start is not None:
        for line in lines[section_start : section_start + 300]:
            if re.match(r"^第[一二三四五六七八九十\d]+章", line) and "投标文件格式" not in line and "技术文件制作" not in line:
                break
            section_lines.append(line.strip())
            if len(section_lines) >= 260:
                break

    scope = "\n".join(section_lines) if section_lines else text
    sections = []
    for kw in FORMAT_SECTION_KEYWORDS:
        if kw in text:
            sections.append(FORMAT_SECTION_CANONICAL.get(kw, kw))
    sections = list(dict.fromkeys(sections))
    templates = [kw for kw in FORMAT_TEMPLATE_KEYWORDS if kw in text]
    requirements = [label for pattern, label in FORMAT_REQUIREMENT_PATTERNS if re.search(pattern, text)]

    seen: set[str] = set()
    sections = [s for s in sections if not (s in seen or seen.add(s))]
    seen = set()
    templates = [t for t in templates if not (t in seen or seen.add(t))]
    seen = set()
    requirements = [r for r in requirements if not (r in seen or seen.add(r))]

    chapter = ""
    for line in lines:
        match = re.search(r"(第[一二三四五六七八九十\d]+章\s*投标文件格式)", line)
        if match:
            chapter = match.group(1)
            break

    return {
        "chapter": chapter,
        "sections": sections,
        "templates": templates,
        "requirements": requirements,
        "raw": ("\n".join(section_lines))[:1800] if section_lines else "",
        "commercial_raw": commercial_raw,
        "technical_raw": technical_raw,
    }


def _slice_section(lines: list[str], start_keyword: str, end_keywords: tuple[str, ...]) -> str:
    start = next((idx for idx, line in enumerate(lines) if start_keyword in line), None)
    if start is None:
        return ""
    end = len(lines)
    for idx in range(start + 1, len(lines)):
        if any(keyword in lines[idx] for keyword in end_keywords):
            end = idx
            break
    return "\n".join(line.strip() for line in lines[start:end]).strip()


def extract_file(content: str, source_file: str) -> dict[str, dict]:
    text = content
    result: dict[str, dict] = {}

    def add(field: str, pattern: str, confidence: float = 0.9, transform=None) -> None:
        match = _first(pattern, text)
        if not match:
            return
        raw = match.group(1).strip(" ：:，,。\n")
        value = transform(raw) if transform else raw
        if value and not _is_junk(value):
            result[field] = _field(value, confidence, source_file, text, match)

    def add_multiline(field: str, label_pattern: str, confidence: float = 0.92, max_len: int = 300) -> None:
        match = _first(
            rf"(?:{label_pattern})\s*[：:]\s*"
            r"([^\n]+(?:\n(?!\s*(?:\d+[．.]|招标代理|招标人|采购人|项目单位|地址|邮编|联系人|联系电话|电话|电子邮箱|邮箱|招标编号|项目编号|项目名称|招标公告|二[○〇]|中国·北京))[^\n]+){0,10})",
            text,
        )
        if not match:
            return
        raw = re.sub(r"\s*\n\s*", "", match.group(1)).strip(" ：:，,。")
        if raw and not _is_junk(raw):
            result[field] = _field(raw[:max_len], confidence, source_file, text, match)

    add_multiline("project_name", "项目名称|工程名称|项目全称|采购项目名称", 0.96)
    if "project_name" not in result:
        title_name = _extract_project_name_from_title(text)
        if title_name:
            result["project_name"] = _field(title_name, 0.8, source_file, text, None)
    add(
        "bid_number",
        r"(?:招标编号|项目编号|采购编号|招标项目编号|采购项目编号)\s*[：:]\s*([A-Za-z0-9\-—–_（）()\u4e00-\u9fff]{3,60})",
        0.97,
    )

    budget_match = _first(
        r"(?:项目预算|采购预算|最高限价|招标控制价|预算金额|最高投标限价|采购金额)\s*[：:]\s*"
        + _AMOUNT_RE,
        text,
    )
    if budget_match:
        amount = _normalize_amount(budget_match.group(0))
        if amount is not None:
            result["budget"] = _field(amount, 0.95, source_file, text, budget_match)

    add(
        "bid_deadline",
        r"(?:投标截止时间|投标截止日期|递交投标文件截止(?:时间|日期)?|投标文件递交截止时间|投标文件递交的截止时间|投标文件提交的截止时间|投标文件提交截止时间)(?:（[^）]*）)?\s*(?:[：:]|[为是])\s*([^\n\r]{4,60})",
        0.98,
        _normalize_datetime,
    )
    add("bid_opening_time", r"(?:开标时间|开标日期)\s*[：:]\s*([^\n\r]{4,60})", 0.97, _normalize_datetime)
    add("bid_location", r"(?:开标地点|投标文件递交地点|开标会议室)\s*[：:]\s*([^\n\r]{4,300})", 0.9)

    quals_trigger = "资格要求"
    quals = _collect_qualifications(text, quals_trigger) or _collect_qualifications(text, "资质要求")
    if quals:
        match = _first(r"(?:资格要求|资质要求|投标人资格要求|资质条件)", text)
        result["qualifications"] = _field(quals, 0.88, source_file, text, match)

    eval_match = _first(r"(?:评标办法|评审办法|评标方法|评标方式)\s*[：:]\s*([^。；\n]{2,60})", text)
    if eval_match:
        result["evaluation_criteria"] = _field(eval_match.group(1).strip(), 0.92, source_file, text, eval_match)
    else:
        phrase_match = _first(r"(综合评分法|经评审的最低投标价法|最低评标价法|性价比法|单源采购|竞争性谈判)", text)
        if phrase_match:
            result["evaluation_criteria"] = _field(phrase_match.group(1), 0.85, source_file, text, phrase_match)

    add("performance_requirements", r"(?:业绩要求|类似项目业绩要求|业绩条件)\s*[：:]\s*([^。\n]{4,200})", 0.88)
    add("technical_requirements", r"(?:技术要求|技术标准|技术规格(?:要求)?)\s*[：:]\s*([^。\n]{4,300})", 0.85)
    if "technical_requirements" not in result:
        tech_match = _first(r"建设方案与建设要求|技术规范书", text)
        tech = _section_text(text, "建设方案与建设要求", max_chars=1500)
        if tech:
            result["technical_requirements"] = _field(tech[:1500], 0.75, source_file, text, tech_match)
    contact_match = _contact_person(text)
    if contact_match:
        result["contact_person"] = _field(contact_match.group(1).strip(), 0.9, source_file, text, contact_match)
    add("contact_phone", r"(?:联系电话|联系方式|联系人电话|电话)\s*[：:]\s*([0-9][\d\-— ]{6,18})", 0.92)
    add("contact_email", r"(?:电子邮箱|邮箱|电子邮件|E-?mail)\s*[：:]\s*([\w.\-]+@[\w\-]+(?:\.[\w\-]+)+)", 0.9)

    security_match = _first(r"(?:投标保证金|保证金金额|投标保证金额度)\s*[：:]\s*" + _AMOUNT_RE, text)
    if security_match:
        amount = _normalize_amount(security_match.group(0))
        if amount is not None:
            result["bid_security_amount"] = _field(amount, 0.93, source_file, text, security_match)

    add(
        "bid_security_deadline",
        r"(?:保证金(?:缴纳|递交)?(?:截止)?(?:时间|日期)|缴纳保证金(?:截止)?(?:时间|日期))\s*[：:]\s*([^\n\r]{4,60})",
        0.9,
        _normalize_datetime,
    )
    add("bid_validity_period", r"(?:投标有效期)\s*[：:]\s*([^\n\r]{2,40})", 0.9)
    add_multiline("tenderer", "招标人(?:名称)?|采购人(?:名称)?|项目单位", 0.94)
    add_multiline("tenderer_address", "招标人(?:名称)?地址|采购人地址|招标人住所|招标人地点", 0.88)
    add_multiline("agency_name", "招标代理机构(?:名称)?|采购代理机构(?:名称)?|代理机构", 0.92)
    add("agency_contact", r"(?:代理机构联系人|招标代理联系人|代理联系人)\s*[：:]\s*([^\n\r]{2,40})", 0.85)
    add("project_location", r"(?:项目地点|项目地址|项目实施地点|项目所在地|建设地点|服务地点|交货地点|建设服务地点)\s*[：:]\s*([^\n\r]{4,100})", 0.9)
    add_multiline("project_scale", "项目规模|建设规模|采购规模|项目概况", 0.85, max_len=400)
    add("delivery_period", r"(?:工期要求|交货期|交付期|服务期|服务期限|建设服务期限|实施期限|实施周期|完成期限|供货期)\s*[：:]\s*([^\n\r]{4,80})", 0.9)
    add("quality_standard", r"(?:质量标准|质量要求|验收标准|质量等级)\s*[：:]\s*([^。\n]{4,120})", 0.9)
    add("payment_terms", r"(?:付款方式|付款条件|支付方式|付款办法)\s*[：:]\s*([^。\n]{4,200})", 0.88)
    add("warranty", r"(?:质保期|质保要求|质量保证期|保修期|质保期限)\s*[：:]\s*([^\n\r]{4,200})", 0.9)

    format_lines = []
    for line in text.splitlines():
        if re.search(r"投标文件\s*(?:份数|正本|副本|装订|密封|格式|语言)", line) or re.search(r"(?:装订要求|密封要求|投标文件格式要求)", line):
            clean = line.strip()
            if clean and clean not in format_lines:
                format_lines.append(clean)
        if len(format_lines) >= 3:
            break
    if format_lines:
        match = _first(r"(?:投标文件\s*(?:份数|正本|副本|装订|密封|格式)|装订要求|密封要求)", text)
        result["bid_format_requirements"] = _field(format_lines, 0.84, source_file, text, match)

    format_data = _extract_bid_format(text)
    if format_data["sections"] or format_data["templates"] or format_data["requirements"]:
        match = _first(r"(?:投标文件格式|技术文件制作及递交要求|投标文件编制要求)", text)
        result["bid_format"] = _field(format_data, 0.86, source_file, text, match)

    return result


def _contact_person(text: str) -> re.Match | None:
    lines = text.splitlines()
    # 联系方式/招标代理段落里的“项目负责人”优先，例如“项目负责人：张工”。
    for index, line in enumerate(lines):
        if "项目负责人" not in line:
            continue
        window = "\n".join(lines[max(0, index - 25) : index])
        if "联系方式" in window or "招标代理机构" in window:
            match = re.search(r"项目负责人\s*[：:]\s*([^\s，,。\n&]{2,30})", line)
            if match:
                return match
    for line in lines:
        if "代理机构联系人" in line or "招标代理联系人" in line:
            continue
        match = re.search(r"(?<!异议)(?:项目联系人|采购人联系人|招标人联系人|联系人)\s*[：:]\s*([^\s，,。\n&]{2,30})", line)
        if match:
            return match
    return None


def merge(results: list[dict]) -> dict[str, dict]:
    merged: dict[str, dict] = {}
    for field in FIELD_LABELS:
        candidates = [r[field] for r in results if r.get(field)]
        if not candidates:
            continue
        merged[field] = max(candidates, key=lambda item: (item.get("confidence", 0), len(str(item.get("primary_value", "")))))
    format_candidates = [r["bid_format"] for r in results if r.get("bid_format")]
    if format_candidates:
        merged["bid_format"] = max(
            format_candidates,
            key=lambda item: (
                len(item.get("primary_value", {}).get("sections", [])) if isinstance(item.get("primary_value"), dict) else 0,
                item.get("confidence", 0),
            ),
        )
    return merged


def summarize(data: dict[str, dict]) -> dict:
    counts = {"high": 0, "medium": 0, "low": 0}
    for field in FIELD_LABELS:
        item = data.get(field)
        if not item:
            continue
        confidence = float(item.get("confidence", 0))
        if confidence >= 0.9:
            counts["high"] += 1
        elif confidence >= 0.7:
            counts["medium"] += 1
        else:
            counts["low"] += 1
    return counts
