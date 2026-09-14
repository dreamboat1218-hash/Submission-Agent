from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from .models import IndustryTemplate, KbDocument, KbType, User
from .security import hash_password

logger = logging.getLogger(__name__)

DEFAULT_USERS = [
    ("admin", "admin123", "管理员"),
    ("auditor", "audit123", "审核员"),
    ("demo", "demo123", "普通用户"),
]

DEFAULT_KB = [
    (
        "XX科技有限公司企业简介",
        "企业资质",
        "XX科技有限公司成立于2015年，注册资本5000万元，现有员工260人，其中研发人员占比45%。"
        "公司专注于信息化系统集成与软件开发，拥有电子与智能化工程专业承包二级资质、"
        "ISO9001质量管理体系认证、ISO27001信息安全管理体系认证、CMMI3级软件能力成熟度认证，"
        "连续三年获评省级高新技术企业。",
    ),
    (
        "ISO9001质量管理体系认证",
        "企业资质",
        "证书名称：质量管理体系认证证书；编号：00124Q30001R2M；"
        "标准：GB/T 19001-2016/ISO 9001:2015；覆盖范围：信息系统集成服务、软件开发与运维服务；"
        "发证机构：北京中经科环质量认证有限公司；有效期至2027年6月。",
    ),
    (
        "智慧交通项目案例（2024）",
        "项目案例",
        "项目名称：某市智慧交通信号控制平台建设项目；合同金额：1260万元；"
        "实施周期：2024年3月至2024年10月；项目内容：交通信号联网控制、视频分析、指挥调度大屏；"
        "客户评价：项目按期交付，系统运行稳定，获得业主单位表扬信。",
    ),
    (
        "公司常见问题应答",
        "FAQ",
        "公司规模：现有员工260人，其中高级工程师32人、项目经理15人；"
        "本地化服务：在项目所在省份设有常驻服务团队，7×24小时响应；"
        "财务状况：近三年年均营收超过2亿元，无重大诉讼与失信记录。",
    ),
]

DEFAULT_KB_TYPES = [
    ("企业资质", "商务文件", "营业执照、资质证书、ISO认证等"),
    ("历史标书", "商务文件", "过往完整投标文件"),
    ("项目案例", "商务文件", "已实施项目详情与客户评价"),
    ("模板库", "通用", "各类投标模板"),
    ("FAQ", "通用", "常见问题应答"),
]

DEFAULT_TEMPLATES = [
    ("通用", "通用投标书模板", "适用于未指定行业的投标文件初稿"),
    ("IT", "IT/信息化投标书模板", "面向软件开发、系统集成、信息化平台项目"),
    ("建筑", "建筑工程投标书模板", "面向施工总承包、市政工程、装饰装修项目"),
    ("医疗", "医疗健康投标书模板", "面向医疗设备、医疗器械、健康服务项目"),
    ("教育", "教育服务投标书模板", "面向智慧校园、教育信息化、培训服务项目"),
]


def seed_data(db: Session) -> None:
    for username, password, role in DEFAULT_USERS:
        if db.query(User).filter(User.username == username).first() is None:
            db.add(User(username=username, password_hash=hash_password(password), role=role))

    for title, doc_type, content in DEFAULT_KB:
        exists = db.query(KbDocument).filter(KbDocument.title == title).first()
        if exists is None:
            db.add(KbDocument(title=title, doc_type=doc_type, content=content))

    for name, chapter, description in DEFAULT_KB_TYPES:
        exists = db.query(KbType).filter(KbType.name == name).first()
        if exists is None:
            db.add(KbType(name=name, chapter=chapter, description=description))

    for industry, name, description in DEFAULT_TEMPLATES:
        exists = db.query(IndustryTemplate).filter(IndustryTemplate.industry == industry).first()
        if exists is None:
            db.add(IndustryTemplate(industry=industry, name=name, description=description))

    db.commit()
