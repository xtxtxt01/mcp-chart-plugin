# Chart Plugin MCP Demo

一个面向 `review -> chart plugin` 场景整理过的 MCP Demo。  
它的目标是：

- 在 review 阶段接收图表任务
- 优先利用上游已经沉淀好的 `existing_refs`
- 如果第一次无法成图，再补做 aggSearch
- 用 LLM 完成检索规划、insight 抽取、图表决策
- 返回可直接插入报告的 markdown 图片引用

当前 MCP tool 的典型输出是：

```md
![图表标题](artifacts/charts/{request_id}/chart_01.png)
```

说明：

- `relative_path` / `markdown` 返回的是相对 `MCP_demo/` 根目录的路径
- 如果本机可用无头 Edge/Chrome，会优先导出 `chart_01.png`
- 如果浏览器导出失败，会回退到静态 `chart_01.svg`

## 当前主流程

现在的真实流程不是“一次检索一次出图”，而是两阶段尝试：

### 第一轮：只用上游已有 insights

1. 从 csv/log 回放里拿到：
   - `chart_title`
   - `chart_description`
   - `write_requirement`
   - `existing_refs`
   - `base_queries`
2. 把 `existing_refs` 直接视为上游已有 insight
3. 不重新抽取这批 `existing_refs`
4. 直接调用 baseline prompt + LLM 生成图表

### 第二轮：失败后再补检索

只有第一轮结果是 `empty` 或图表数据无效时，才进入第二轮：

1. 基于以下信息做 LLM retrieval planning：
   - 图表描述
   - `base_queries`
   - 第一轮失败原因
   - 已有 insight 预览
2. 调 aggSearch
3. 保留：
   - 全部 `existing_refs`
   - live docs top 10
4. 只对新搜到的 live docs 做 LLM 抽取
5. 合并：
   - existing insights
   - live insights
6. 再调用一次 baseline prompt + LLM 生成图表
7. 渲染出最终图片、html 预览和 markdown

可以概括成：

```text
csv/log replay
-> first pass: existing_refs only
-> chart generation
-> if empty:
   -> LLM gap-aware query planning
   -> aggSearch
   -> live-doc insight extraction
   -> existing insights + live insights
   -> chart generation again
-> render
-> markdown
```

## 目录结构

```text
MCP_demo/
  app/
    server.py
    demo_runner.py
  clients/
    agg_search.py
    llm.py
  core/
    chart_plugin.py
    baseline_decider.py
    renderer.py
  data/
    csv_cases.py
    review_payloads.py
  schemas/
    function_schemas.py
    extract_chart_facts.tools.json
    plan_chart_retrieval.tools.json
  assets/
    baseline_chart_prompt.txt
  vendor/
    render_utils.py
    md2html.py
  artifacts/
  outputs/
  config.py
  pyproject.toml
  .env.example
```

## 各层职责

### `app/`

- `server.py`
  - MCP server 入口
  - 注册 tools / resources
- `demo_runner.py`
  - 本地单 case 回放入口

### `clients/`

- `agg_search.py`
  - aggSearch 客户端
- `llm.py`
  - LLM 客户端
  - 优先 function calling
  - 模型不兼容时退到文本 JSON 解析

### `core/`

- `chart_plugin.py`
  - 整个插件主流程
  - 两阶段尝试逻辑
  - insight 合并
  - gap-aware retrieval planning
- `baseline_decider.py`
  - 直接加载原始 `baseline_chart_prompt.txt`
  - 用 LLM 输出 XML 图表决策
- `renderer.py`
  - 生成 `.txt/.json/.html`
  - 生成最终图片
  - 优先基于同一份 ECharts option 用无头浏览器导出 PNG
  - 浏览器不可用时回退到静态 SVG

### `data/`

- `csv_cases.py`
  - 从日志 csv 中回放 case
- `review_payloads.py`
  - 组装 demo 用的 review payload

### `schemas/`

- `function_schemas.py`
  - function calling schema 定义
- `plan_chart_retrieval.tools.json`
  - 查询规划 schema
- `extract_chart_facts.tools.json`
  - insight 抽取 schema

### `assets/`

- `baseline_chart_prompt.txt`
  - 原始图表生成 prompt
  - 当前直接作为图表生成 LLM prompt 使用

### `vendor/`

- `render_utils.py`
  - ECharts option 和 html 预览链
- `md2html.py`
  - html 渲染辅助

## MCP 暴露内容

### Tools

- `generate_chart_markdown`
  - 输入：review 阶段图表任务 payload
  - 输出：
    - `markdown`
    - `relative_path`
    - `chart_tag`
    - `debug_summary`
    - `generation_attempts`
    - `retry_gap_report`
    - 以及调试字段

- `build_review_payload_demo`
  - 输入：`file_name` + `row_id`
  - 输出：本地回放用的 review payload

### Resources

- `resource://schemas/plan_chart_retrieval`
- `resource://schemas/extract_chart_facts`

## LLM 使用方式

当前有 3 个 LLM 环节：

1. `plan_chart_retrieval`
   - 做 query planning
   - 输入包含图表任务和 gap report
   - function calling 优先

2. `extract_chart_facts`
   - 实际输出结构现在是：
     - `knowledges[]`
   - prompt 采用你前链路的信息提取专家中文版式
   - function calling 优先

3. 图表生成
   - 直接使用 `assets/baseline_chart_prompt.txt`
   - 输出 XML
   - 再解析为图表 spec

## 渲染行为

现在有两类输出：

### 1. `outputs/*.html`

- 这是 ECharts 真预览
- 使用 `vendor/render_utils.py` 里的 option 生成

### 2. `artifacts/charts/{request_id}/chart_01.png|svg`

- 这是最终 markdown 引用的图片
- 现在优先走：
  - 同一份 ECharts option
  - 无头 Edge/Chrome 截图导出 PNG
- 浏览器不可用时才回退到 SVG

因此：

- 新跑出来的 case，`html` 和最终图片应该尽量保持一致
- 如果你看到旧的 `chart_01.svg` 和 html 不一致，通常是历史产物，需要重新跑该 case

## 运行方式

### 1. 本地 demo

先开 SSH 隧道：

```powershell
ssh -L 18080:dx-cbm-ocp-agg-search-inner.xf-yun.com:80 awmao@172.16.154.251
```

再在 `C:\Users\xtyu9\Desktop\日志报告` 下运行：

```powershell
python -m MCP_demo.app.demo_runner
```

指定 csv 和 row：

```powershell
python -m MCP_demo.app.demo_runner --file-name "会计专科岗位_discover search.csv" --row-id 150
```

### 2. MCP server 模式

```powershell
python -m MCP_demo
```

或：

```powershell
python -m MCP_demo.app.server
```

### 3. 作为可安装项目使用

在 `MCP_demo/` 目录下：

```powershell
pip install -e .
```

安装后可用：

```powershell
chart-plugin-mcp
chart-plugin-mcp-demo --file-name "会计专科岗位_discover search.csv" --row-id 150
```

## 配置

统一配置在 `config.py`，主要环境变量如下：

### aggSearch

- `MCP_DEMO_AGG_HOST`
- `MCP_DEMO_AGG_HOST_HEADER`
- `MCP_DEMO_AGG_PIPELINE`
- `MCP_DEMO_AGG_TIMEOUT_MS`
- `MCP_DEMO_AGG_TOP_K`

### retrieval / extraction

- `MCP_DEMO_MAX_QUERIES`
- `MCP_DEMO_MAX_DOCS`
- `MCP_DEMO_EXISTING_REFS_QUOTA`
- `MCP_DEMO_LIVE_DOCS_QUOTA`

说明：

- 当前主流程实际采用的是：
  - existing refs 全保留
  - live docs top 10
- `MCP_DEMO_MAX_DOCS` 目前更多是保留字段

### LLM

- `MCP_DEMO_LLM_BASE_URL`
- `MCP_DEMO_LLM_API_KEY`
- `MCP_DEMO_LLM_MODEL`
- `MCP_DEMO_LLM_TIMEOUT_S`
- `MCP_DEMO_REQUIRE_HTTPS`
- `MCP_DEMO_FORCE_FUNCTION_CALL`

参考：

- `.env.example`

## 输出目录

### 最终图片

在：

```text
artifacts/charts/{request_id}/chart_01.png
```

或浏览器导出失败时：

```text
artifacts/charts/{request_id}/chart_01.svg
```

### 调试产物

在 `outputs/` 下：

- `demo-{case}__demo_summary.json`
  - 整次运行摘要
- `mcp_demo_chart__{request_id}.txt`
  - 原始 XML
- `mcp_demo_chart__{request_id}.json`
  - 结构化图表结果
- `mcp_demo_chart__{request_id}.html`
  - ECharts 真预览

## 最值得看的调试字段

在 `demo_summary.json` 里，优先看：

- `retrieval_plan`
- `knowledges`
- `docs_for_extraction`
- `docs_for_generation`
- `generation_attempts`
- `retry_gap_report`
- `chart_decision_debug`
- `debug_summary`

其中：

- `generation_attempts`
  - 能看出第一轮是不是只用 existing insights
  - 第二轮是不是补了 aggSearch
- `retry_gap_report`
  - 能看出第一次没成图的原因
- `debug_summary.final_stage`
  - 能看出最终停在哪一轮

## 当前项目状态

这套 demo 现在已经满足：

- 以 MCP tool 形式对外提供图表插件能力
- review 阶段可调用
- 返回 markdown 图片引用
- 图片路径为相对路径
- 支持本地 demo 回放
- 支持 aggSearch + LLM + baseline prompt 的完整链路


