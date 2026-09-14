"""Obsidian + Pinakes 双知识库集成。

提供统一知识网关，封装 Markdown/Frontmatter 文件读写、标签检索、
Pinakes 语义检索与关键词降级、标书知识上下文构建。
"""
from .gateway import UnifiedKnowledgeGateway, get_gateway

__all__ = ["UnifiedKnowledgeGateway", "get_gateway"]
