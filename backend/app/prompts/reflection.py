"""反思模块 Prompt：苏格拉底式问题生成 + 三维度评分。

QUESTION_GENERATION_PROMPT 输入变量：{node_name} / {node_summary}
EVALUATION_PROMPT 输入变量：{node_name} / {question} / {answer}（answer 经三引号包裹）
"""

from app.prompts.common import INJECTION_GUARD

PROMPT_VERSION = "v1.0"

QUESTION_GENERATION_PROMPT = (
    INJECTION_GUARD
    + "\n\n"
    + """你是一位苏格拉底式教学法专家。请基于以下知识点生成一个反思问题。

知识点名称：{node_name}
知识点摘要：{node_summary}

要求：
1. 使用苏格拉底式提问，不直接给出答案
2. 引导学生从不同角度深入思考
3. 关注对概念本质的理解而非记忆
4. 问题简洁明了，一段话即可

只返回问题文本，不要包含其他内容。"""
)

EVALUATION_PROMPT = (
    INJECTION_GUARD
    + "\n\n"
    + """你是一位严格的学习评估专家。请从以下三个维度评估学生对反思问题的回答。

知识点：{node_name}
问题：{question}
学生回答：
\"\"\"{answer}\"\"\"

请从以下三个维度各打分（0-100 整数）：
1. concept_accuracy（概念准确性）：回答中对核心概念的理解是否准确
2. logic_completeness（逻辑完整性）：回答的逻辑是否连贯、论证是否完整
3. example_reasonableness（举例合理性）：回答中的举例是否恰当、能否有效支撑论点

评分锚点（每个维度独立打分）：
- 90-100：定义精准，逻辑严密，例证贴切有力
- 75-89：定义准确，逻辑清晰，例证合理
- 60-74：理解基本正确，存在局部偏差
- 40-59：概念混淆，逻辑跳跃，举例牵强
- 0-39：严重错误，或答非所问，或回答为空

补充约束：
- weak_points 最多 3 条，每条不超过 20 字；
- resources 最多 3 条，只列资料名称不列链接；
- 若学生回答为空或纯"不知道"，三个维度均给 0-10 分，weak_points 写 ["未作答"]。

同时给出：
- weak_points：薄弱点列表（字符串数组）
- suggestion：改进建议（一段话）
- resources：推荐补充资料（字符串数组）

以 JSON 格式返回，不要包含其他内容：
{{"concept_accuracy": 85, "logic_completeness": 70, "example_reasonableness": 60, "weak_points": ["薄弱点1"], "suggestion": "改进建议", "resources": ["资料1"]}}"""
)
