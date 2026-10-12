"""Prompt 资源包：集中管理所有大模型 Prompt。

子模块：
- common    通用片段（版本号、防注入声明、RAG 护栏、节点/目录摘要模板）
- extraction 知识抽取
- reflection 问题生成 + 三维度评分
- avatar     数字分身对话（知识问答 + 闲聊）
- pet        宠物按等级动态升级
- ocr        图片笔记 OCR 文字识别
- brainstorm AI 辅助手绘（结构校验 / 辅助构思 / 直接生成）

约定：每个模块暴露 ``PROMPT_VERSION``；模板变量以 ``{name}`` 声明，经
``str.format()`` 注入；用户输入位置一律用三引号包围。
"""

from app.prompts import (
    avatar,
    brainstorm,
    common,
    extraction,
    ocr,
    pet,
    reflection,
)

__all__ = [
    "avatar",
    "brainstorm",
    "common",
    "extraction",
    "ocr",
    "pet",
    "reflection",
]
