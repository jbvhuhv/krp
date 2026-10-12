"""知识抽取 Prompt：从笔记文本构建「目录-知识点」树形结构。

输入变量：{text}（笔记原文，经三引号包裹）
输出格式：JSON —— book_summary / subject / categories / edges
"""

from app.prompts.common import INJECTION_GUARD

PROMPT_VERSION = "v1.1"

EXTRACTION_PROMPT = (
    INJECTION_GUARD
    + "\n\n"
    + """输出格式硬性要求：
- 只输出一段合法 JSON，不要用 ```json 包裹、不要加任何前言或解释；
- 所有 key 和字符串值都用双引号；
- type 字段只能取以下四个值之一：concept（概念）/ method（方法）/ fact（事实）/ skill（技能）；
- 若笔记文本不足 50 字或无有效知识，返回：{{"book_summary": "文本内容过少", "subject": "未分类", "categories": [], "edges": []}}。

请从以下文本中提取知识并进行归纳概括，构建"目录-知识点"的树形结构。

要求：
1. 先对文本内容进行整体归纳，生成 book_summary（一句话概括全文主题）
2. 判定全文所属学科/主题 subject：使用具体、简洁的学科名（如"高等数学"、"计算机网络"、"Python编程"、"材料力学"、"机器学习"、"大学英语"等）；严禁使用"未分类"、"其他"、"综合"这类无意义名称
3. 将知识点按主题分组，每组生成一个"目录"（category），包含 name（目录名称）和 summary（对该组知识点的归纳总结）
4. 每个目录下包含具体的 knowledge_points，每个知识点有 name、summary、type
5. 目录下可再嵌套子目录（categories），子目录同样可包含 knowledge_points 与更深层子目录，按知识体系的自然层级任意嵌套
6. 必须输出知识点之间的关系，edges 不得为空：同一目录（或同一上级）下的知识点，至少要形成"知识点数 - 1"条关系（例如某目录含 4 个知识点，则至少 3 条边）；关系类型可取"包含/依赖/对比/因果/并列/递进"等；source 与 target 必须使用已出现的知识点名称
7. 顶层目录数量控制在 2-6 个，每个末级目录下 2-8 个知识点

以 JSON 格式返回，不要包含其他内容：
{{"book_summary": "全书概括", "subject": "学科/主题名称", "categories": [{{"name": "目录名称", "summary": "该目录的归纳总结", "categories": [{{"name": "子目录名称", "summary": "子目录归纳", "knowledge_points": [{{"name": "知识点名称", "summary": "一句话摘要", "type": "concept"}}]}}], "knowledge_points": [{{"name": "知识点名称", "summary": "一句话摘要", "type": "concept"}}]}}], "edges": [{{"source": "知识点名称", "target": "知识点名称", "relation": "关系类型"}}]}}

文本：
\"\"\"{text}\"\"\""""
)
