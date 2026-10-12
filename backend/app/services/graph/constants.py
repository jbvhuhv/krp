NODE_LABEL = "KnowledgeNode"
RELATED_TO = "RELATED_TO"
CHILD_OF = "CHILD_OF"

NODE_TYPE_BOOK = "book"
NODE_TYPE_CATEGORY = "category"
NODE_TYPE_KNOWLEDGE = "knowledge"

DEFAULT_RELATION = "related_to"
DEFAULT_VECTOR_INDEX = "knowledge_node_embedding"
UNCLASSIFIED_SUBJECT = "未分类"
NOISE_SUBJECTS = frozenset({UNCLASSIFIED_SUBJECT, "默认", "其他", "综合"})
