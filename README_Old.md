# arXiv Research Agent（3D Vision / Camera Localization）

一个本地运行的科研文献监测项目：定时检索 arXiv，按研究画像进行 LLM 相关性筛选，对高相关论文下载 PDF 并提取文本，生成 Markdown 文献简报。

## 1. 工作流

1. 按 `config.yaml` 中的主题组和类别调用 arXiv API。
2. 使用 SQLite 按 arXiv ID 去重并保存元数据。
3. 使用 LLM 对标题和摘要进行 0–10 分相关性评分。
4. 对评分达到阈值的论文下载 PDF，使用 PyMuPDF 提取文本。
5. 让 LLM 输出结构化技术分析：任务假设、方法、几何/优化、数据集、指标、实验、局限性和研究启发。
6. 输出 `reports/latest.md` 及按日期命名的 Markdown 报告。

## 2. 环境要求

- Python 3.10 或更高版本（推荐 Python 3.11）
- 可访问 arXiv API 的网络
- 一个支持 OpenAI-compatible Chat Completions 接口的模型服务及 API Key

## 3. 安装

### Windows PowerShell

```powershell
cd path\to\arxiv-research-agent
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
Copy-Item .env.example .env
```

如果 PowerShell 不允许激活脚本，可以不激活环境，直接使用：

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

### Ubuntu / Linux

```bash
cd /path/to/arxiv-research-agent
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
cp .env.example .env
```

## 4. 配置模型 API

编辑 `.env`：

```dotenv
LLM_BASE_URL=https://api.openai.com/v1
LLM_API_KEY=你的API_KEY
LLM_MODEL=你的模型名称
LLM_TIMEOUT=180
DISABLE_PDF_ANALYSIS=0
```

程序使用通用的 `POST {LLM_BASE_URL}/chat/completions` 接口。若使用其他厂商，请按该厂商文档填写兼容地址和准确模型名称。若使用阿里云百炼，兼容地址会因地域和业务空间而不同；请查阅 [百炼 OpenAI 兼容接口说明](https://help.aliyun.com/zh/model-studio/compatibility-of-openai-with-dashscope)，不要直接照抄其他地域的地址。用于 Codex 的 Coding Plan 专用 Key/端点可能仅面向交互式编程工具，不应默认拿来作为后台论文 Agent 的服务凭证。

不要把 `.env` 提交到 Git，也不要把 API Key 写进 `config.yaml` 或 Python 源码。

## 5. 配置研究方向

编辑 `config.yaml`：

- `research_profile`：描述你的研究背景和优先问题。
- `topic_groups`：维护分类与关键词。
- `lookback_days`：每次检索回看的首次提交日期范围，建议保留 7–14 天，避免定时任务偶尔失败后漏文献。
- `high_relevance_threshold`：默认 7 分，达到后才下载 PDF 并做全文分析。
- `max_fulltext_chars`：发送给 LLM 的论文文本上限。第一版默认 50,000 字符，后续可按模型上下文和费用调整。
- `max_screening_per_run`：每次运行最多初筛多少篇，默认 60；超出的论文留在数据库中等待下次运行。
- `max_fulltext_per_run`：每次最多全文分析多少篇，默认 5；避免短时间产生过高模型费用。

arXiv API 查询按主题组逐次请求，代码在请求之间留出 3.2 秒间隔。不要为了追求实时性而高频轮询 API。

## 6. 测试与运行

先测试模型连接：

```powershell
python main.py test-llm
```

成功后执行一次完整任务：

```powershell
python main.py run
```

如果暂时只想测试检索、评分和报告，不下载 PDF：

```dotenv
DISABLE_PDF_ANALYSIS=1
```

然后运行 `python main.py run`。

输出位置：

- `data/papers.db`：论文元数据、评分和分析结果。
- `data/pdfs/`：高相关论文 PDF。
- `reports/latest.md`：最近生成的报告。
- `reports/daily/`：按运行日期保存的报告。

## 7. 定时运行

### Windows Task Scheduler

建议先手动运行成功，再建立任务：

1. 打开“任务计划程序”。
2. 选择“创建基本任务”。
3. 名称填写 `arXiv Research Agent`。
4. 触发器选择“每天”，设置期望时间。
5. 操作选择“启动程序”。
6. 程序填写项目虚拟环境的 Python 路径，例如 `D:\\arxiv-research-agent\\.venv\\Scripts\\python.exe`。
7. 参数填写项目 `main.py` 的绝对路径后加 `run`，例如 `D:\\arxiv-research-agent\\main.py run`。
8. “起始于”填写项目目录，例如 `D:\\arxiv-research-agent`。
9. 保存后右键任务，选择“运行”测试。

注意：任务运行账户必须能读取 `.env`、写入 `data/` 和 `reports/`，且运行时机器需要联网。

### Ubuntu / Linux cron

执行 `crontab -e`，添加以下示例（每天早上 08:30）：

```cron
30 8 * * * cd /path/to/arxiv-research-agent && /path/to/arxiv-research-agent/.venv/bin/python main.py run >> logs/cron.log 2>&1
```

先创建日志目录：`mkdir -p logs`。cron 使用机器本地时区；请先检查系统时区。

## 8. 当前版本边界

- 当前是可扩展的 MVP，不是自动化学术审稿系统。
- 初筛依赖标题和摘要，可能漏掉摘要未提及关键方法的论文。
- PDF 文本抽取基于 PyMuPDF 的文本层和启发式选页，复杂双栏、公式、表格和图示可能丢失结构；关键论文必须回看原 PDF。
- 本版会在后续运行中重试未完成的初筛和全文分析；`--force` 可以对本次检索到的论文重新分析。已存在论文的 arXiv 新版本检测和人工反馈闭环尚未实现。
- LLM 评分不是论文质量评价，也不代表同行评审结论。

## 9. 建议的后续迭代

1. 加入 `--since`、`--dry-run` 和人工重新分析命令。
2. 增加 arXiv 版本更新检测与 Cross-list 去重策略。
3. 对高相关论文增加章节级分块分析，减少长文截断。
4. 加入 Semantic Scholar/OpenAlex 引用关系追踪。
5. 将人工标注的相关/不相关样本用于调整评分提示词。
6. 报告加入 BibTeX、Zotero 导入和 GitHub 代码仓库检测。

## 10. Codex 开发建议

把本项目目录交给 Codex。建议先让它审查并修复 MVP，再按阶段扩展：

```text
请先完整阅读 README.md、config.yaml 和 src/ 下的代码。
第一阶段：检查代码正确性、异常处理、arXiv Atom 解析、SQLite 幂等性和跨平台路径。
第二阶段：补充 pytest 单元测试，特别是 arXiv ID 解析、日期过滤、去重、JSON 解析和报告生成。
第三阶段：实现已有论文版本更新检测、失败任务重试和分析状态恢复。
不要一次性引入多 Agent、向量数据库或复杂 RAG；先保证单机定时任务稳定运行。
```
