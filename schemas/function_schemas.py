from __future__ import annotations

import json

from ..config import SCHEMAS_ROOT


def plan_chart_retrieval_tools() -> list[dict]:
    return [
        {
            "type": "function",
            "function": {
                "name": "plan_chart_retrieval",
                "description": "分析图表任务，规划补充检索意图，并返回可直接执行的搜索 queries。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "intent": {
                            "type": "object",
                            "properties": {
                                "comparison_mode": {
                                    "type": "string",
                                    "description": "图表任务的主要对比/表达模式。",
                                    "enum": [
                                        "compare",
                                        "trend",
                                        "share",
                                        "flow",
                                        "hierarchy",
                                        "funnel",
                                        "multidim",
                                        "other",
                                    ],
                                },
                                "entities": {
                                    "type": "array",
                                    "description": "任务中明确出现的核心实体。",
                                    "items": {"type": "string"},
                                },
                                "metrics": {
                                    "type": "array",
                                    "description": "任务中需要补齐的指标。",
                                    "items": {"type": "string"},
                                },
                                "dimensions": {
                                    "type": "array",
                                    "description": "任务中的类别、阶段、年份、区域等维度。",
                                    "items": {"type": "string"},
                                },
                                "chart_type_hints": {
                                    "type": "array",
                                    "description": "如果任务本身已经明显指向某类图，可给出提示。",
                                    "items": {
                                        "type": "string",
                                        "enum": [
                                            "empty",
                                            "radar",
                                            "bar-line",
                                            "sankey",
                                            "pie",
                                            "treemap",
                                            "sunburst",
                                            "funnel",
                                        ],
                                    },
                                },
                                "must_have_fields": {
                                    "type": "array",
                                    "description": "成图前必须补齐的字段。",
                                    "items": {"type": "string"},
                                },
                                "time_hints": {
                                    "type": "array",
                                    "description": "检索中应重点关注的时间提示。",
                                    "items": {"type": "string"},
                                },
                                "region_hints": {
                                    "type": "array",
                                    "description": "检索中应重点关注的地域提示。",
                                    "items": {"type": "string"},
                                },
                                "query_language": {
                                    "type": "string",
                                    "description": "建议检索语言，如 zh、en、mixed。",
                                },
                            },
                            "required": ["comparison_mode", "entities", "metrics"],
                        },
                        "queries": {
                            "type": "array",
                            "description": "3 到 8 条聚焦的检索 query。",
                            "items": {"type": "string"},
                        },
                        "notes": {
                            "type": "string",
                            "description": "必要时补充简短规划说明。",
                        },
                    },
                    "required": ["intent", "queries"],
                },
            },
        }
    ]


def extract_chart_facts_tools() -> list[dict]:
    return [
        {
            "type": "function",
            "function": {
                "name": "extract_chart_facts",
                "description": "从参考资料中提取知识点，严格返回 knowledges 数组。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "knowledges": {
                            "type": "array",
                            "description": "基于原文抽取的知识点列表。",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "insight": {
                                        "type": "string",
                                        "description": "基于片段提炼的知识点，无效内容不输出。",
                                    },
                                    "snippets": {
                                        "type": "array",
                                        "description": "引用的原始文档编号，如 \"0\"、\"3\"。",
                                        "items": {"type": "string"},
                                    },
                                },
                                "required": ["insight", "snippets"],
                            },
                        }
                    },
                    "required": ["knowledges"],
                },
            },
        }
    ]


def schema_file_path(name: str) -> str:
    return (SCHEMAS_ROOT / name).as_posix()


def schema_file_text(name: str) -> str:
    schema_map = {
        "extract_chart_facts.tools.json": extract_chart_facts_tools(),
        "plan_chart_retrieval.tools.json": plan_chart_retrieval_tools(),
    }
    return json.dumps(schema_map[name], ensure_ascii=False, indent=2)
