"""模块五：知识库管理。

企业资质、历史标书、项目案例、模板库、FAQ 的统一管理；支持关键词检索与
可选 ChromaDB 向量检索的混合召回。
"""
from __future__ import annotations

import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import or_
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import KbDocument, KbType
from .preprocess import convert_to_markdown
from .vector_store import VectorIndex

logger = logging.getLogger(__name__)

VALID_TYPES = {"企业资质", "历史标书", "项目案例", "模板库", "FAQ"}
BUILTIN_KB_TYPES = {"企业资质", "历史标书", "项目案例", "模板库", "FAQ"}

TYPE_OBSIDIAN_DIR = {
    "企业资质": "01_企业资质",
    "历史标书": "02_历史标书",
    "项目案例": "02_历史标书",
    "模板库": "05_投标模板",
    "FAQ": "_system_generated",
}


def get_valid_types(db: Session) -> set[str]:
    names = {row[0] for row in db.query(KbType.name).filter(KbType.is_active.is_(True)).all()}
    return names or VALID_TYPES

COMMERCIAL_KEYWORDS = [
    "资质", "证书", "营业执照", "认证", "许可证", "保证金", "财务报表", "审计",
    "承诺函", "股权", "联合体", "法人", "授权", "银行", "税务", "社保", "开户",
]

TECHNICAL_KEYWORDS = [
    "技术方案", "技术规范", "技术参数", "产品", "设备", "工艺", "检测", "试验",
    "研发", "专利", "生产", "安装", "调试", "维护", "设计", "系统", "软件",
    "硬件", "配置", "指标", "性能", "服务方案",
]

COMMERCIAL_STRONG_KEYWORDS = ["营业执照", "资质证书", "ISO", "认证证书", "许可证", "资质", "财务", "审计"]
TECHNICAL_STRONG_KEYWORDS = ["技术方案", "技术规范", "技术参数", "设备", "产品", "工艺", "试验", "检测", "架构"]


class KnowledgeService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.vector = VectorIndex()

    def add_document(self, title: str, content: str, doc_type: str, metadata: dict | None = None, file_path: str = "") -> KbDocument:
        valid_types = get_valid_types(self.db)
        doc_type = doc_type if doc_type in valid_types else "企业资质"
        doc = KbDocument(
            title=title,
            content=content,
            doc_type=doc_type,
            metadata_json=metadata or {},
            file_path=file_path,
        )
        self.db.add(doc)
        self.db.flush()
        self.vector.upsert(doc.id, f"{title}\n{content}", {"doc_type": doc_type, "title": title})
        self.db.commit()
        self.db.refresh(doc)
        _sync_doc_to_obsidian(doc)
        return doc

    def add_attachment(
        self,
        title: str,
        content: str,
        doc_type: str,
        file_path: str,
        chapter: str,
        images: list[str] | None = None,
        page_count: int = 0,
        original_name: str = "",
        metadata_extra: dict | None = None,
    ) -> KbDocument:
        valid_types = get_valid_types(self.db)
        doc_type = doc_type if doc_type in valid_types else "企业资质"
        metadata = {
            "chapter": chapter,
            "images": images or [],
            "page_count": page_count,
            "original_name": original_name,
            "source": "attachment",
        }
        if metadata_extra:
            metadata.update(metadata_extra)
        return self.add_document(title, content, doc_type, metadata, file_path)

    def update_document(self, doc_id: str, fields: dict) -> KbDocument | None:
        doc = self.db.get(KbDocument, doc_id)
        if doc is None:
            return None
        valid_types = get_valid_types(self.db)
        if "title" in fields and fields["title"]:
            doc.title = fields["title"]
        if "content" in fields:
            doc.content = fields["content"]
        if "doc_type" in fields and fields["doc_type"] in valid_types:
            doc.doc_type = fields["doc_type"]
        if "metadata" in fields:
            doc.metadata_json = fields["metadata"]
        if "file_path" in fields:
            doc.file_path = fields["file_path"]
        doc.updated_at = datetime.now(timezone.utc)
        self.db.commit()
        self.db.refresh(doc)
        self.vector.upsert(doc.id, f"{doc.title}\n{doc.content}", {"doc_type": doc.doc_type, "title": doc.title})
        _sync_doc_to_obsidian(doc)
        return doc

    def delete_document(self, doc_id: str) -> bool:
        doc = self.db.get(KbDocument, doc_id)
        if doc is None:
            return False
        self.db.delete(doc)
        self.db.commit()
        self.vector.delete(doc_id)
        _remove_doc_from_obsidian(doc)
        return True

    def list_documents(self, doc_type: str | None = None, limit: int = 100, offset: int = 0) -> tuple[int, list[KbDocument]]:
        query = self.db.query(KbDocument)
        if doc_type:
            query = query.filter(KbDocument.doc_type == doc_type)
        total = query.count()
        items = query.order_by(KbDocument.updated_at.desc()).offset(offset).limit(limit).all()
        return total, items

    def get_document(self, doc_id: str) -> KbDocument | None:
        return self.db.get(KbDocument, doc_id)

    def search(self, query: str, top_k: int = 5) -> list[dict]:
        if not query.strip():
            return []
        keyword = f"%{query.strip()}%"
        rows = (
            self.db.query(KbDocument)
            .filter(or_(KbDocument.title.like(keyword), KbDocument.content.like(keyword)))
            .limit(50)
            .all()
        )
        scores: dict[str, dict] = {}
        for row in rows:
            text = f"{row.title} {row.content}"
            count = text.count(query.strip())
            scores[row.id] = {"id": row.id, "title": row.title, "content": row.content[:800], "doc_type": row.doc_type, "score": 1.0 + count * 0.05}

        vector_hits = self.vector.query(query, top_k=top_k * 2)
        for doc_id, score in vector_hits:
            row = self.db.get(KbDocument, doc_id)
            if row is None:
                continue
            current = scores.get(row.id, {"id": row.id, "title": row.title, "content": row.content[:800], "doc_type": row.doc_type, "score": 0.0})
            current["score"] = max(current.get("score", 0.0), float(score))
            scores[row.id] = current
        ranked = sorted(scores.values(), key=lambda item: item["score"], reverse=True)
        return ranked[:top_k]

    def retrieve_context(self, query: str, top_k: int = 5) -> str:
        hits = self.search(query, top_k=top_k)
        if not hits:
            return ""
        return "\n\n".join(f"【{hit['doc_type']}】{hit['title']}\n{hit['content']}" for hit in hits)

    def add_kb_type(self, name: str, chapter: str = "商务文件", description: str = "") -> KbType:
        chapter = chapter if chapter in {"商务文件", "技术文件", "通用"} else "商务文件"
        existing = self.db.query(KbType).filter(KbType.name == name).first()
        if existing is not None:
            return existing
        kb_type = KbType(name=name, chapter=chapter, description=description)
        self.db.add(kb_type)
        self.db.commit()
        self.db.refresh(kb_type)
        return kb_type

    def list_kb_types(self) -> list[KbType]:
        return self.db.query(KbType).filter(KbType.is_active.is_(True)).order_by(KbType.created_at).all()

    def delete_kb_type(self, kb_type_id: str) -> bool:
        kb_type = self.db.get(KbType, kb_type_id)
        if kb_type is None:
            return False
        self.db.delete(kb_type)
        self.db.commit()
        return True


def classify_document(title: str, content: str) -> tuple[str, str]:
    text = f"{title}\n{content}"
    commercial_score = sum(1 for keyword in COMMERCIAL_KEYWORDS if keyword in text) + 2 * sum(
        1 for keyword in COMMERCIAL_STRONG_KEYWORDS if keyword in text
    )
    technical_score = sum(1 for keyword in TECHNICAL_KEYWORDS if keyword in text) + 2 * sum(
        1 for keyword in TECHNICAL_STRONG_KEYWORDS if keyword in text
    )

    type_scores = {
        "企业资质": sum(1 for kw in ("资质", "认证", "证书", "营业执照", "许可证", "ISO") if kw in text),
        "历史标书": sum(1 for kw in ("投标文件", "标书", "中标", "投标") if kw in text),
        "项目案例": sum(1 for kw in ("项目", "合同", "案例", "业绩", "客户", "验收", "交付") if kw in text),
        "模板库": sum(1 for kw in ("模板", "格式", "范本", "式样") if kw in text),
        "FAQ": sum(1 for kw in ("常见问题", "问答", "FAQ", "说明") if kw in text),
    }
    doc_type = max(type_scores, key=type_scores.get) if any(type_scores.values()) else "企业资质"
    chapter = "技术文件" if technical_score > commercial_score else "商务文件"
    return doc_type, chapter


def _sync_doc_to_obsidian(doc: KbDocument) -> None:
    """资料库文档同步为 Obsidian 目录里的 Markdown 笔记，实现两套知识库共用目录。"""
    if os.environ.get("PYTEST_CURRENT_TEST"):
        return
    try:
        from ..kb_integration import get_gateway
        from ..kb_integration.file_handler import write_note

        gateway = get_gateway()
        doc_meta = doc.metadata_json if isinstance(doc.metadata_json, dict) else {}
        subdir = str(doc_meta.get("obsidian_dir") or TYPE_OBSIDIAN_DIR.get(doc.doc_type, "_system_generated"))
        title = re.sub(r'[\\/:*?"<>|\r\n\t]', "_", str(doc.title or "未命名")).strip() or "未命名"
        tags: list[str] = [doc.doc_type]
        for tag in doc_meta.get("tags") or []:
            if str(tag).strip() and str(tag).strip() not in tags:
                tags.append(str(tag).strip())
        metadata: dict = {
            "title": doc.title,
            "tags": tags,
            "source": "资料库",
            "doc_id": doc.id,
        }
        if doc_meta.get("chapter"):
            metadata["chapter"] = doc_meta["chapter"]
        write_note(gateway.root, f"{subdir}/{title}.md", doc.content or "", metadata)
    except Exception as exc:
        logger.warning("资料库文档同步到 Obsidian 目录失败：%s", exc)


def _remove_doc_from_obsidian(doc: KbDocument) -> None:
    try:
        from ..kb_integration import get_gateway
        from ..kb_integration.file_handler import list_notes, read_note, resolve_path

        gateway = get_gateway()
        for rel in list_notes(gateway.root):
            try:
                note = read_note(gateway.root, rel)
            except Exception:
                continue
            if note.metadata.get("doc_id") == doc.id:
                resolve_path(gateway.root, rel).unlink(missing_ok=True)
                return
    except Exception as exc:
        logger.warning("资料库文档从 Obsidian 目录删除失败：%s", exc)


def sync_all_docs_to_obsidian(db: Session) -> int:
    """启动时把已有资料库文档同步到 Obsidian 目录，补齐历史数据。"""
    count = 0
    for doc in db.query(KbDocument).all():
        _sync_doc_to_obsidian(doc)
        count += 1
    return count


def process_attachment(upload_path: Path, doc_id: str) -> dict:
    """解析附件内容；PDF 与图片附件同时渲染为可嵌入标书的图片。"""
    settings = get_settings()
    images: list[str] = []
    content = ""
    page_count = 0
    suffix = upload_path.suffix.lower()

    if suffix == ".pdf":
        try:
            import fitz

            with fitz.open(upload_path) as pdf:
                page_count = pdf.page_count
                parts = [page.get_text("text").strip() for page in pdf]
                content = "\n".join(part for part in parts if part)
                image_dir = settings.kb_path / "images" / doc_id
                image_dir.mkdir(parents=True, exist_ok=True)
                for index, page in enumerate(pdf):
                    if index >= 20:
                        break
                    pix = page.get_pixmap(dpi=120)
                    image_path = image_dir / f"page_{index + 1:02d}.png"
                    pix.save(image_path)
                    images.append(str(image_path))
        except Exception as exc:
            logger.warning("PDF 附件解析失败：%s", exc)
            content = ""

    elif suffix in {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff", ".webp"}:
        image_dir = settings.kb_path / "images" / doc_id
        image_dir.mkdir(parents=True, exist_ok=True)
        image_path = image_dir / upload_path.name
        import shutil

        shutil.copy2(upload_path, image_path)
        images.append(str(image_path))
        content = f"图片附件：{upload_path.name}"

    if not content:
        try:
            md_path = settings.kb_path / "converted" / f"{doc_id}.md"
            md_path.parent.mkdir(parents=True, exist_ok=True)
            convert_to_markdown(upload_path, md_path)
            content = md_path.read_text(encoding="utf-8", errors="replace")
        except Exception as exc:
            logger.warning("附件转文本失败：%s", exc)
            content = ""

    return {
        "content": content[:50000],
        "images": images,
        "page_count": page_count,
    }
