# chart_plugin_mcp

## 项目说明
`chart_plugin_mcp` 是面向深度研究报告场景的图表增强服务。  
该服务以 MCP 工具方式对外提供图表生成能力，供上游报告系统在“增强”阶段调用。系统会结合当前章节内容、段落上下文以及对应章节的知识文件，自动判断是否需要插入图表；满足成图条件时，生成图表图片并返回可直接插入报告的 Markdown 引用。

本组件当前主要服务于 `deep-report-go` 主流程，也可作为独立的图表增强模块进行部署与复用。

## 核心能力
- 面向报告正文自动识别适合图表表达的内容
- 结合章节知识文件 `knowledge/chN.json` 提升成图质量与稳定性
- 在现有上下文不足时进行补充检索
- 自动选择图表类型并生成 ECharts 图表
- 将图表渲染为 PNG 图片并返回 Markdown 图片引用
- 支持与 `deep-report-go` 的增强阶段无缝集成

## 适用场景
- 深度研究报告
- 行业研究与市场分析
- 公司研究与竞品分析
- 政策、规模、结构、趋势类报告增强
- 需要在正文中自动插入图表的报告生成系统

## 对外工具
当前服务对外提供一个工具：

### `chart_generate`
用于为当前报告段落生成图表。

上游直接传入的主要字段包括：
- `query`：整篇深度研究任务的原始问题
- `chapter_title`：当前章节标题
- `paragraph_text`：当前待增强段落内容
- `paragraph_id`：当前段落编号
- `chapter_context`：当前章节的补充上下文
- `output_path`：可选，指定输出图片路径
- `language`：语言参数，默认 `zh`

服务内部会自动补充的上下文包括：
- 当前报告目录中的 `chapters.json`
- 当前章节对应的 `knowledge/chN.json`
- 必要时触发的补充检索结果

典型输出包括：
- 是否成功成图
- 图表类型
- 图表图片路径
- 可直接插入报告的 Markdown 内容
- 调试摘要与补充检索信息

## 工作流程
1. 上游报告系统在增强阶段选定某一章节、某一段落
2. 通过 MCP 调用 `chart_generate`
3. 服务根据 `chapter_title` 匹配对应章节，并优先加载该章节的 `knowledge/chN.json`
4. 结合段落正文、章节上下文和知识文件构造图表任务
5. 基于现有信息判断是否适合成图
6. 如关键信息不足，则执行补充检索
7. 选择合适图表类型并生成 PNG 图表
8. 返回 Markdown 图片引用，供上游插入最终报告

## 目录结构
- `deepreport_stdio.py`
  - MCP stdio 服务入口，供上游通过子进程方式启动
- `clients/`
  - 大模型与检索客户端
- `core/`
  - 图表任务构造、图表决策、渲染与落盘主逻辑
- `schemas/`
  - 工具 schema 定义
- `assets/`
  - 图表决策 prompt 资源
- `vendor/`
  - ECharts 及渲染相关依赖
- `config.py`
  - 配置与环境变量读取
- `.env.example`
  - 环境变量示例

## 运行要求
建议部署前确认以下环境条件：
- Python 3.11 及以上
- 可用的大模型服务地址与 API Key
- 可用的检索服务配置
- Windows 环境下建议安装 Edge 或 Chrome，用于无头截图渲染

## 环境变量
本项目统一使用 `CHART_PLUGIN_*` 环境变量。

常用配置如下：

### 模型配置
- `CHART_PLUGIN_LLM_BASE_URL`
- `CHART_PLUGIN_LLM_API_KEY`
- `CHART_PLUGIN_LLM_MODEL`
- `CHART_PLUGIN_LLM_TIMEOUT_S`
- `CHART_PLUGIN_REQUIRE_HTTPS`
- `CHART_PLUGIN_FORCE_FUNCTION_CALL`

### 检索配置
- `CHART_PLUGIN_SEARCH_BACKEND`
- `CHART_PLUGIN_IFLY_APP_ID`
- `CHART_PLUGIN_IFLY_API_KEY`
- `CHART_PLUGIN_IFLY_API_SECRET`
- `CHART_PLUGIN_IFLY_ENDPOINT`
- `CHART_PLUGIN_IFLY_PIPELINE_NAME`
- `CHART_PLUGIN_IFLY_USER_ID`

### 图表生成配置
- `CHART_PLUGIN_MAX_QUERIES`
- `CHART_PLUGIN_LIVE_DOCS_QUOTA`
- `CHART_PLUGIN_RENDER_TIMEOUT_S`
- `CHART_PLUGIN_RENDER_VIRTUAL_TIME_BUDGET_MS`


## 启动方式
推荐启动方式如下：

### 方式一：模块启动
```powershell
python -m chart_plugin_mcp
```

上述方式会启动 MCP stdio 服务，供上游以子进程方式拉起和调用。

## 与 deep-report-go 的集成方式
如需与 `deep-report-go` 主流程联动，建议按以下方式配置：

### 1. 安装本服务
在 `chart_plugin_mcp` 目录执行：

```powershell
pip install -e .
```

### 2. 在 `deep-report-go` 中配置增强服务
在 `deep-report-go/config.yaml` 的 `mcp_enhancement_servers` 中增加或替换图表增强服务：

```yaml
- name: chart-plugin
  command: py
  args:
    - -m
    - chart_plugin_mcp.deepreport_stdio
  env:
    PYTHONPATH: C:/Users/xtyu9/Desktop/日志报告
    CHART_PLUGIN_SEARCH_BACKEND: ifly_public
    CHART_PLUGIN_IFLY_APP_ID: ${IFLY_APP_ID}
    CHART_PLUGIN_IFLY_API_KEY: ${IFLY_API_KEY}
    CHART_PLUGIN_IFLY_API_SECRET: ${IFLY_API_SECRET}
    CHART_PLUGIN_IFLY_ENDPOINT: https://cbm-search-api.cn-huabei-1.xf-yun.com/biz/search
    CHART_PLUGIN_IFLY_PIPELINE_NAME: pl_map_agg_search
    CHART_PLUGIN_IFLY_USER_ID: user001
    CHART_PLUGIN_AGG_TIMEOUT_MS: "30000"
    CHART_PLUGIN_AGG_TOP_K: "10"
    CHART_PLUGIN_LLM_BASE_URL: https://maas-api.cn-huabei-1.xf-yun.com/v1
    CHART_PLUGIN_LLM_API_KEY: ${MAAS_API_KEY}
    CHART_PLUGIN_LLM_MODEL: xopdeepseekv32
    CHART_PLUGIN_LLM_TIMEOUT_S: "90"
    CHART_PLUGIN_REQUIRE_HTTPS: "1"
    CHART_PLUGIN_FORCE_FUNCTION_CALL: "1"
    CHART_PLUGIN_RENDER_TIMEOUT_S: "45"
    CHART_PLUGIN_RENDER_VIRTUAL_TIME_BUDGET_MS: "12000"
```

### 3. 准备主流程环境变量
确保 `deep-report-go` 运行环境中已经配置：
- `MAAS_API_KEY`
- `IFLY_APP_ID`
- `IFLY_API_KEY`
- `IFLY_API_SECRET`

### 4. 运行深度研究主流程
在 `deep-report-go` 目录中执行：

```powershell
.\deep-report.exe run --query "深度分析中国各家大模型厂商的竞争格局、技术路线与商业化进展" --mode deep --domain "行业研究"
```

在 `deep` 模式下，`deep-report-go` 会自动完成：
- 工具发现
- 工具参数注入
- 图表调用
- 图表结果插回报告

## 输出结果
成图成功时，服务会产出：
- 图表 PNG 图片
- 图表渲染相关中间结果
- 可直接插入报告的 Markdown 图片引用

在深度研究场景下，图表会优先复制到当前报告目录下的 `charts/` 子目录，便于与报告正文统一管理和交付。

