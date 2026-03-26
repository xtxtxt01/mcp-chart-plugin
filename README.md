# Chart Plugin MCP

用于 `review -> chart generation` 场景的标准 `stdio` 型 MCP。

它接收上游直接传入的 `review_payload`，优先基于已有 `existing_refs` 直接成图；如果首轮失败，则最多补搜 1 轮，并将 `existing insights + top3 live docs` 一起送入第二次图表生成。最终返回可直接插入报告的 Markdown 图片引用、PNG 相对路径，以及调试信息。

## 1. 当前能力边界

- 只暴露一个正式 tool：`generate_chart_markdown`
- 只暴露一个 schema resource：`resource://schemas/plan_chart_retrieval`
- 整条链路最多两次 LLM 调用
  - query planning
  - chart generation
- 只使用一套共享 LLM 配置
- 补搜轮数固定为 1 轮
- 第二轮只保留去重后的 top3 live docs
- 不再做 live docs 文档抽取
- 最终产物只保留 PNG，不再保留 SVG
- 非空图表会尽量显式标出数值，便于直接插入报告

## 2. MCP 暴露内容

### Tool

- `generate_chart_markdown`

### Resource

- `resource://schemas/plan_chart_retrieval`

## 3. 运行方式

### 直接启动 MCP server

```powershell
python -m MCP_demo
```

也可以使用：

```powershell
python -m MCP_demo.app.server
```

### 安装为本地命令

```powershell
pip install -e .
```

安装后可直接运行：

```powershell
chart-plugin-mcp
```

## 4. 运行前提

运行这版 MCP 需要：

1. 一套可用的共享 LLM 配置
2. 可访问的 aggSearch endpoint
3. 本机可用的无头 Edge/Chrome，用于将图表截图导出为 PNG

说明：

- aggSearch endpoint 通过环境变量配置
- PNG 导出依赖本机浏览器可执行文件

## 5. 环境变量

### LLM

- `MCP_DEMO_LLM_BASE_URL`
- `MCP_DEMO_LLM_API_KEY`
- `MCP_DEMO_LLM_MODEL`
- `MCP_DEMO_LLM_TIMEOUT_S`
- `MCP_DEMO_REQUIRE_HTTPS`
- `MCP_DEMO_FORCE_FUNCTION_CALL`

### aggSearch

- `MCP_DEMO_AGG_HOST`
- `MCP_DEMO_AGG_HOST_HEADER`
- `MCP_DEMO_AGG_PIPELINE`
- `MCP_DEMO_AGG_TIMEOUT_MS`
- `MCP_DEMO_AGG_TOP_K`

### 其他

- `MCP_DEMO_MAX_QUERIES`
- `MCP_DEMO_LIVE_DOCS_QUOTA`
- `MCP_DEMO_RENDER_TIMEOUT_S`
- `MCP_DEMO_RENDER_VIRTUAL_TIME_BUDGET_MS`

示例可参考：

- `.env.example`

## 6. 输入契约

正式接入时，上游必须直接传入 `review_payload`。

### 必填字段

- `request_id`
- `chart_title`
- `chart_description`
- `existing_refs`

### 可选字段

- `write_requirement`
- `base_queries`
- `language`

### `existing_refs` 格式

```json
[
  {
    "id": 0,
    "content": "已有参考资料或上游抽取结果"
  }
]
```

### `base_queries` 格式

```json
[
  "基础检索 query 1",
  "基础检索 query 2"
]
```

### 最小输入示例

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
    ],
    "language": "zh"
  }
}
```

## 7. 输出契约

典型输出中的核心字段如下：

```json
{
  "success": true,
  "markdown": "![图表标题](artifacts/charts/case-001/chart_01.png)",
  "relative_path": "artifacts/charts/case-001/chart_01.png",
  "chart_tag": "radar",
  "should_insert": true,
  "empty_reason": "",
  "debug_summary": {
    "query_count": 0,
    "live_hits_count": 0,
    "selected_live_docs_count": 0,
    "used_agg_search": false,
    "attempt_count": 1,
    "final_stage": "existing_insights_only"
  }
}
```

### 上游通常重点使用

- `markdown`
- `relative_path`
- `chart_tag`
- `should_insert`
- `empty_reason`
- `debug_summary`

### `empty` 语义

- 当 `chart_tag == "empty"` 时，MCP 不再返回可插入图片
- 此时：
  - `markdown == ""`
  - `relative_path == ""`
  - `should_insert == false`
  - `empty_reason` 会返回不成图原因
- 上游应据此跳过插图，而不是插入说明性占位图

### 常见调试字段

- `retrieval_plan`
- `queries`
- `live_search_overview`
- `selected_live_docs`
- `docs_for_generation`
- `knowledges`
- `chart_decision_debug`
- `generation_attempts`
- `retry_gap_report`

## 8. 当前主流程

### 第一轮

1. 上游传入 `review_payload`
2. 将 `existing_refs` 视为已有 insights
3. 直接调用图表生成 LLM
4. 若图表有效，直接渲染输出

### 第二轮

仅当首轮结果为 `empty` 或图表数据无效时触发：

1. 基于图表任务和首轮失败原因做一次 query planning
2. 调用 aggSearch 做一次补搜
3. 对 live docs 去重后仅保留 top3
4. 将 `existing insights + top3 live docs` 一起送入第二次图表生成
5. 输出最终 PNG 图表

## 9. `used_agg_search` 与补搜命中语义

`debug_summary.used_agg_search` 的含义是：

- 是否触发了第二轮补搜流程

它不代表：

- 一定搜到了文档

真正表示补搜是否拿回新文档的是：

- `debug_summary.live_hits_count`
- `debug_summary.selected_live_docs_count`
- `live_search_overview[*].document_count`

也就是说，完全可能出现：

- `used_agg_search = true`
- 但 `live_hits_count = 0`

这表示“补搜流程触发了，但没有拿到任何新文档”。

## 10. LLM 配置

当前只使用一套共享 LLM 配置。

同一套 LLM 同时用于：

- query planning
- chart generation

### 运行时通过 `config.llm` 覆盖

```json
{
  "review_payload": { "...": "..." },
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

兼容说明：

- `config.llm` 可以直接传一套共享配置
- 如果调用方仍传旧的分阶段结构，当前实现会取其中第一套可用配置作为共享 LLM 使用

## 11. aggSearch 配置

aggSearch 请求由：

- `clients/agg_search.py`

直接发往配置好的 endpoint。


## 12. 渲染与产物

### 渲染方式

- 非空图表会先生成 ECharts option
- 再通过本机无头 Edge/Chrome 打开临时 HTML 并截图成 PNG
- `outputs/*.html` 主要用于调试和预览
- 正式插入报告时，以上游消费 `markdown` / `relative_path` 为准

### 输出目录

- `outputs/`
  - html/json/txt 结果包
- `artifacts/charts/{request_id}/`
  - 最终图表图片 `chart_01.png`

## 13. 本地测试说明

- `data/` 目录仅用于本地 CSV 回放和 case 调试
- 正式接入不依赖 `data/`
- 仓库默认不会上传 `data/`、`outputs/`、`artifacts/`

## 14. 主要目录

```text
MCP_demo/
  app/
    server.py
  clients/
    agg_search.py
    llm.py
  core/
    chart_plugin.py
    baseline_decider.py
    renderer.py
  schemas/
    function_schemas.py
    plan_chart_retrieval.tools.json
  assets/
    baseline_chart_prompt.txt
    query_planning_prompt.txt
  vendor/
    echarts.min.js
    render_utils.py
    md2html.py
  config.py
  .env.example
  README.md
  HANDOFF.md
```

## 15. 建议重点查看的调试字段

- `debug_summary.final_stage`
  - 看最终停在哪一轮
- `debug_summary.live_hits_count`
  - 看补搜总共拿回多少 live docs
- `debug_summary.selected_live_docs_count`
  - 看第二轮实际用了多少 live docs
- `generation_attempts`
  - 看每一轮的图表决策和上下文快照
- `chart_decision_debug`
  - 看最终 LLM 图表决策输出
