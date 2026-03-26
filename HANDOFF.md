# 图表生成 MCP 交付说明

本次交付内容为一个可独立调用的图表生成 MCP，用于在 review / DeepResearch 阶段根据图表任务描述、已有参考资料和一次补充检索结果生成最终图表，并返回可直接插入报告的 Markdown 图片引用。

## 1. 仓库地址

- `https://github.com/xtxtxt01/mcp-chart-plugin.git`

## 2. MCP 用途

该 MCP 负责图表生成能力，输入为 `review_payload`，输出为：

- 图表 Markdown 引用
- 图表相对路径
- 图表类型
- 调试摘要信息

适合在 DeepResearch / review 阶段由主流程按需调用。

## 3. 启动方式

该 MCP 采用 `stdio` 方式启动。

```bash
python -m MCP_demo
```

也可使用：

```bash
python -m MCP_demo.app.server
```

## 4. 正式 Tool

正式接入时只使用以下 tool：

- `generate_chart_markdown`

## 5. 输入格式

`generate_chart_markdown` 的输入为：

```json
{
  "review_payload": {
    "request_id": "case-001",
    "chart_title": "图表标题",
    "chart_description": "图表描述",
    "write_requirement": "写作要求",
    "existing_refs": [
      {
        "id": 0,
        "content": "已有参考资料或上游抽取结果"
      }
    ],
    "base_queries": [
      "基础检索 query 1",
      "基础检索 query 2"
    ]
  }
}
```

字段说明：

- `request_id`：本次图表请求唯一标识，必填
- `chart_title`：图表标题，必填
- `chart_description`：图表绘制目标，必填
- `existing_refs`：上游已有参考资料或已抽取结果，必填
- `write_requirement`：写作要求，可选
- `base_queries`：基础检索 query，可选

## 6. 输出格式

典型输出如下：

```json
{
  "success": true,
  "markdown": "![图表标题](artifacts/charts/case-001/chart_01.png)",
  "relative_path": "artifacts/charts/case-001/chart_01.png",
  "chart_tag": "radar",
  "debug_summary": {
    "used_agg_search": false,
    "attempt_count": 1,
    "final_stage": "existing_insights_only"
  }
}
```

上游通常重点使用：

- `markdown`
- `relative_path`
- `chart_tag`

## 7. 当前核心流程

当前流程固定为两阶段：

1. 基于 `existing_refs` 直接尝试成图
2. 若首轮失败，则：
   - 做一次 query planning
   - 做一次 aggSearch 补搜
   - 选取去重后的 top3 live docs
   - 将 `existing insights + top3 live docs` 一起送入第二次图表生成

说明：

- 当前补搜轮数固定为 1 轮
- 当前不再做文档抽取
- 因此整条链路中最多只会有 2 次 LLM 调用

## 8. LLM 使用说明

当前只使用一套共享 LLM 配置。

同一套 LLM 同时用于：

- query planning
- 图表生成

支持的环境变量：

- `MCP_DEMO_LLM_BASE_URL`
- `MCP_DEMO_LLM_API_KEY`
- `MCP_DEMO_LLM_MODEL`
- `MCP_DEMO_LLM_TIMEOUT_S`
- `MCP_DEMO_REQUIRE_HTTPS`
- `MCP_DEMO_FORCE_FUNCTION_CALL`

调用方也可以在 `generate_chart_markdown` 的 `config.llm` 中传入同一套配置：

```json
{
  "config": {
    "llm": {
      "base_url": "https://a.example.com/v1",
      "api_key": "sk-xxx",
      "model": "model-name",
      "timeout_s": 90,
      "force_function_call": true
    }
  }
}
```

## 9. aggSearch 与渲染说明

- 当前仓库已经内置 aggSearch 请求逻辑，不再依赖仓库外的 `chart_search_recall_helper.py`
- 运行环境仍需能访问配置好的 aggSearch endpoint
- PNG 导出优先使用仓库内的 `vendor/echarts.min.js`
- 每次渲染前会自动清理当前 `request_id` 目录中的旧图
- 当前只保留 PNG，不再生成或保留 SVG
- 运行环境必须具备本机无头 Edge/Chrome，PNG 导出失败时该次渲染会直接报错

## 10. 运行依赖

项目依赖和环境变量见仓库内：

- `pyproject.toml`
- `.env.example`
- `README.md`

安装建议：

```bash
pip install -e .
```

## 11. 输出目录

运行后主要产物会输出到：

- `artifacts/charts/{request_id}/`
  - 最终图表图片
- `outputs/`
  - html/json/txt 结果包

## 12. 本地测试目录说明

- `data/` 仅用于本地 case 回放和测试，不属于正式交付内容
- 正式接入时不需要提供 `data/`
- 当前仓库已忽略 `data/`，本地可保留，GitHub 交付不会受影响
