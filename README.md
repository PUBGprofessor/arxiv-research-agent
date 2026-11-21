# arXiv Research Agent

面向三维视觉、视觉定位与相机位姿估计研究的本地文献监测工具。程序按主题检索 arXiv，使用兼容 OpenAI Chat Completions 的模型对标题和摘要做相关性初筛；可选地下载高相关论文 PDF、提取文本并生成技术分析，最后写出 Markdown 简报。

## 项目流程

1. 读取 `config.yaml` 的研究画像、主题组、关键词和 arXiv 查询参数。
2. 按主题组调用 arXiv Atom API。每组请求间隔由 `request_interval_seconds` 控制；只保留 `lookback_days` 内首次提交的论文。
3. 以 arXiv ID 在 SQLite 中去重并保存论文元数据。未处理记录会在后续运行中继续处理。
4. 对待处理论文的标题和摘要调用 LLM，生成 0–10 相关度分数、主题标签及判断依据。
5. 默认对达到高相关阈值且允许全文阅读的论文下载 PDF，使用 PyMuPDF 提取有限页数/字符数，再调用 LLM 生成结构化技术分析。
6. 生成中文 Markdown 报告：`reports/latest.md`、按日期保存的日报及按 ISO 周保存的周报。

## 环境与安装

需要 Python 3.10+（建议 3.11）、可访问 arXiv API 的网络，以及一个 OpenAI-compatible Chat Completions 服务的 API Key。PDF 全文分析依赖 PyMuPDF（`requirements.txt` 已包含）。

Windows PowerShell：

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
notepad .env
```

若 PowerShell 禁止激活脚本，可直接用虚拟环境中的解释器：

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Linux/macOS：

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
touch .env
nano .env
```

## 配置

编辑项目根目录 `.env`，填入服务商提供的兼容端点、密钥和模型名称：

```dotenv
LLM_BASE_URL=https://api.openai.com/v1
LLM_API_KEY=替换为你的密钥
LLM_MODEL=替换为可用模型名称
LLM_TIMEOUT=180
DISABLE_PDF_ANALYSIS=0
```

程序请求 `{LLM_BASE_URL}/chat/completions`。使用其他厂商时，按厂商文档填写正确的兼容地址和模型名。不要提交 `.env`，也不要把密钥写入 YAML 或源码。

按需编辑 `config.yaml`：

- `research_profile` 描述研究背景、重点和排除方向，供模型评估相关性。
- `topic_groups` 定义 arXiv 分类和关键词；可以增删主题组以控制检索范围。
- `arxiv.lookback_days` 是首次提交日期回看窗口，建议至少 7 天，便于定时任务漏跑后补回。
- `arxiv.max_results_per_topic` 限定每个主题组的 API 返回上限；请求之间会按配置等待，避免高频访问。
- `screening.high_relevance_threshold` 控制全文分析门槛；`max_screening_per_run` 和 `max_fulltext_per_run` 限制单次模型调用量。
- `screening.max_fulltext_chars`、`max_pdf_pages` 限制送入模型的提取文本规模；`analyze_full_text_for_high_relevance` 可关闭全部全文分析。
- `storage` 下的数据库、PDF 和报告目录可使用相对项目根目录的路径，也可填写绝对路径。

要仅运行检索、摘要初筛和报告生成，在 `.env` 设置 `DISABLE_PDF_ANALYSIS=1`。这会跳过 PDF 下载和全文分析，但仍会使用 LLM 做摘要初筛。也可将 `screening.analyze_full_text_for_high_relevance` 设为 `false`；环境变量开关优先用于临时禁用。重新启用时设回 `0`。

## 使用命令

先检查模型服务连通性：

```powershell
python main.py test-llm
```

运行一次监测流程（不带子命令时默认也是 `run`）：

```powershell
python main.py run
```

强制重新处理本次检索到的记录：

```powershell
python main.py run --force
```

`--force` 会清除对应记录已有的初筛/全文分析结果并重新调用模型，可能增加 API 费用。Windows 若未激活虚拟环境，将命令中的 `python` 换为 `\.venv\Scripts\python.exe`。

## 数据与报告

- `data/papers.db`：SQLite 论文元数据、处理状态、评分及分析结果。
- `data/pdfs/`：已下载的高相关论文 PDF（全文分析启用时）。
- `reports/latest.md`：最近一次生成的报告。
- `reports/daily/YYYY-MM-DD.md`：按本地日期保存的日报。
- `reports/weekly/YYYY-Www.md`：按 ISO 年/周保存的周报。

程序会自动创建数据库和报告所需目录。报告中的模型评分是初筛参考，不代表论文质量或同行评审结论；PDF 文本提取可能遗漏公式、表格、图像及双栏排版信息，关键结果应回看原文。

## 测试

在项目根目录执行：

```powershell
在 Windows PowerShell 中：

```powershell
$env:PYTHONPATH = "src"
python -m pytest
```

在 Linux/macOS 中：

```bash
PYTHONPATH=src python -m pytest
```
```

若尚未激活虚拟环境，使用 `\.venv\Scripts\python.exe -m pytest`。测试不应需要真实模型 API Key；`test-llm` 是在线连通性检查，不属于离线单元测试。

## 运行注意事项

- 首次运行前先成功执行 `test-llm`，确认端点、密钥、模型名和余额/权限有效。
- arXiv API 和模型服务均需网络连接。失败的主题请求会记录日志；未完成的筛选/全文分析记录可在后续运行中重试。
- 任务计划程序或 cron 应使用虚拟环境 Python，并将工作目录设为项目根目录，确保能读取 `.env`、`config.yaml` 并写入数据/报告目录。
- 当前主题组以 `config.yaml` 中未注释的配置为准；调整主题组会改变每次检索覆盖的 arXiv 分类和关键词。
- 避免过短周期轮询；保持合理回看窗口和 API 请求间隔。模型调用、PDF 下载可能产生费用或消耗带宽。
- 当前工具是研究监测 MVP；初筛受标题摘要信息和提示词影响，结果需要研究者核验。
