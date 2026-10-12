"""AI 辅助手绘 Prompt：结构校验 / 辅助构思 / 直接生成。

- 校验：对整本书结构给出总评、问题清单、缺失知识点建议；
- 辅助构思：无初步想法时给出可展开的子节点建议；有想法时给出引导性问题；
- 直接生成：为某节点系统性生成一棵下级子树。

所有模板首个变量为经三引号包裹的用户内容，统一置于 INJECTION_GUARD 之后。
"""

from app.prompts.common import INJECTION_GUARD

PROMPT_VERSION = "v1.0"

_JSON_RULE = (
    "输出格式硬性要求：\n"
    "- 只输出一段合法 JSON，不要用 ```json 包裹、不要加任何前言或解释；\n"
    "- 所有 key 和字符串值都用双引号；\n"
    "- reason 字段控制在 20 字以内。"
)

_NODE_TYPE_RULE = (
    "字段语义要求：\n"
    "- node_type 只能输出英文 category（目录/分组）或 knowledge（知识点），必须是这两个值之一，"
    "禁止输出中文、空格或其他词；\n"
    "- type 描述知识点类型，仅 knowledge 需要，取 concept / fact / skill / method 之一；category 无需 type。"
)

BRAINSTORM_VERIFY_PROMPT = (
    INJECTION_GUARD
    + "\n\n"
    + _JSON_RULE
    + "\n"
    + _NODE_TYPE_RULE
    + """

你是知识结构校对专家。下面是用户绘制的一本知识书的目录结构（缩进表示父子层级）：

\"\"\"{tree_text}\"\"\"

请检查该结构的合理性：
1. 是否存在归类错误的知识点（放错了父级）；
2. 是否存在表述错误或不恰当的节点；
3. 相比该主题，缺失了哪些必要的知识点或目录。

以 JSON 返回，不要包含其他内容：
{{"overall": "两三句话的整体评价", "issues": [{{"node_name": "节点名称", "status": "error", "reason": "问题原因"}}], "missing": [{{"name": "缺失节点名称", "summary": "一句话摘要", "node_type": "knowledge", "type": "concept", "reason": "为什么需要", "parent_name": "建议挂靠的节点名称"}}]}}

说明：status 只能取 error（内容错误）或 misplaced（位置不当）或 correct（正常，无需列出）。issues 只列出有问题的节点；若结构合理，issues 与 missing 可为空数组。当缺失的是一个成组主题时，将其 node_type 设为 category，并可附带 children 子知识点。"""
)

BRAINSTORM_HINT_PROMPT = (
    INJECTION_GUARD
    + "\n\n"
    + _JSON_RULE
    + "\n"
    + _NODE_TYPE_RULE
    + """

你是思维导图引导助手。用户正在为知识点「{node_name}」发散思考，该节点当前摘要：{node_summary}

请围绕该主题，给出 3-5 个值得继续展开的子内容建议（可以是子目录或具体知识点），帮助用户打开思路。

要求：
1. 若该主题覆盖多个方面，优先给出 1-2 个 category 目录建议，并在其 children 中附带具体 knowledge 知识点，形成「目录 → 知识点」的分级结构；
2. 每个建议都要有 name、node_type、summary，knowledge 需带 type；
3. 不要直接替用户补全成完整结构，只给下一步值得思考的方向。

以 JSON 返回，不要包含其他内容：
{{"suggestions": [{{"name": "建议的子内容名称", "node_type": "knowledge", "type": "concept", "summary": "一句话摘要", "reason": "为什么建议这个", "children": []}}]}}

说明：node_type 只能取 knowledge 或 category；叶子节点的 children 为空数组。"""
)

BRAINSTORM_GUIDE_PROMPT = (
    INJECTION_GUARD
    + "\n\n"
    + _JSON_RULE
    + """

你是思维导图引导助手。用户正在为知识点「{node_name}」补充内容，他目前的初步想法是：

\"\"\"{user_idea}\"\"\"

请不要直接给出答案或替他补全节点，而是提出 2-3 个引导性问题或思考方向，帮助他把这个想法想得更清楚、更完整。

以 JSON 返回，不要包含其他内容：
{{"guidance": "引导文字，分点陈述，语气鼓励"}}"""
)

BRAINSTORM_GENERATE_PROMPT = (
    INJECTION_GUARD
    + "\n\n"
    + _JSON_RULE
    + "\n"
    + _NODE_TYPE_RULE
    + """

你是知识结构化专家。请为知识点「{node_name}」系统性地生成下级内容，形成一棵完整的子树。
该节点当前摘要：{node_summary}

要求：
1. 顶层优先用 1-3 个 category 目录对内容分组，形成「目录 → 知识点」的分级结构；只有主题确实不可再分时，才用扁平的知识点；
2. 每个目录下挂 2-4 个 knowledge 知识点，整棵子树共 5-10 个节点，最多嵌套两层；
3. 内容需与主题紧密相关，覆盖该主题的主要方面；
4. 每个节点都要有 name、node_type、summary，knowledge 需带 type。

以 JSON 返回，不要包含其他内容：
{{"nodes": [{{"name": "目录名称", "node_type": "category", "summary": "一句话摘要", "children": [{{"name": "知识点名称", "node_type": "knowledge", "type": "concept", "summary": "一句话摘要", "children": []}}]}}]}}

说明：node_type 只能取 category 或 knowledge；叶子节点的 children 为空数组。"""
)
