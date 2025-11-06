# AutoWriter 项目

**R2-Tag｜本轮完成标记**
- [x] 逐行注释覆盖率≥90%，重点模块均补齐中文说明
- [x] README 扩写 11 大章节并包含 ASCII 架构草图
- [x] 未提交任何二进制产物，保持仓库纯文本
- [x] 可通过 `python app/main.py --topic` 或 `make run` 本地运行

## 1. 项目简介（AutoWriter 是什么）
AutoWriter 是一套自动写作骨架，目标是每天根据计划生成约 2000 字的文章，并将草稿投递到多个平台。系统内置调度、去重、日志与适配器机制，为未来接入真实平台 API 打好基础。

### 核心技术栈速览
- **编程语言**：Python 3.11（核心逻辑与 CLI），部分自动化脚本基于 Playwright。
- **依赖管理**：`pip + requirements.txt` 与 Poetry/uv 双轨支持，便于在 CI 或桌面环境安装。
- **任务调度**：APScheduler 负责 cron 级计划任务，另有系统 cron 兼容方案。
- **数据库**：SQLite 作为默认演示环境，可无缝切换至 PostgreSQL/MySQL。
- **大模型/推理**：Ollama、Groq、Fireworks、Hugging Face Inference、vLLM 等提供统一抽象。
- **日志与监控**：Structlog 输出 JSON 日志；Prometheus 指标与 Alertmanager 告警脚本提供观测性。
- **自动化与导出**：Playwright + Pyperclip 实现半自动送稿与剪贴板助手；打包导出依赖 zipfile/CSV/JSON 工具集。

### 运行环境概览
| 分类 | 推荐配置 | 说明 |
| --- | --- | --- |
| 操作系统 | macOS / Linux / Windows 10+ | 全部流程均在 Python 用户态运行，无系统专属依赖 |
| Python 版本 | ≥ 3.11 | 低版本会导致类型注解与 dataclass 功能缺失 |
| 浏览器 | Chrome 113+ | 供 Playwright 自动化与 CDP 调试使用 |
| 虚拟环境 | `python -m venv .venv` | 避免污染系统包，便于隔离依赖 |
| Node.js（可选） | 18+ | 仅在需要扩展前端 Dashboard 时使用 |
| 额外工具 | `make`、`zip`、`sqlite3` | 常见 Unix 工具，便于调试与导出 |

### 功能要点
- **定时调度**：基于 APScheduler，每日固定时间自动生成并投递内容。
- **去重检查**：以关键词集合和数据库记录避免重复发文。
- **草稿投递**：通过可插拔适配器，将文章推送到 Medium、WordPress、微信公众号等草稿箱（当前为占位实现）。
- **结构化日志**：使用 structlog 输出 JSON 日志，便于统一采集。
- **可配置性**：统一配置中心，可通过 .env 或环境变量控制密钥、数据库、时区等。
- **VPS 生命周期脚本占位**：保留创建/销毁云主机的接口，后续可接入云商 API。

## 2. 最终愿景与产品形象
AutoWriter 的长期目标是实现「全自动、零干预」的内容生产流水线：系统按日程生成高质量文章，进入人工审核草稿箱，避免重复并支持主题可控。

### Prompt 迭代历程（回顾）
| Prompt 轮次 | 目标 | 主要产出 |
| --- | --- | --- |
| 第 1 轮（R1 骨架） | 打通最小可运行流程 | `app/main.py` 完成生成→去重→投递链路，占位平台适配器就绪 |
| 第 2 轮（R2 文档/注释） | 强化可维护性 | 代码文件补充逐行中文注释；README 扩写结构化章节与架构草图 |
| 第 3 轮（当前） | 归档知识与零基础入门 | 汇总技术栈、环境准备、历史 Prompt，补充端到端运行说明并整理操作手册 |

### 愿景亮点
- 持续生成高质量、可审稿后发布的草稿。
- 支持主题矩阵、A/B Prompt 策略与质量度量（预留接口）。
- 提供审核工作流与失败回滚机制，保障内容安全。

### 演进路线图（Roadmap）
1. **R1 骨架**：打通生成、去重、投递的最小链路。
2. **R2 注释/文档**：本轮完成，补齐逐行注释与完整 README。
3. **R3 内容 Prompt 体系**：引入主题库、文章大纲、风格模板、反重复校验、元数据打标。
4. **R4 平台适配完善**：接入各平台正式 API，完善鉴权与回调。
5. **R5 质量评估/回退**：落地质量评分、人工审核与内容回滚机制。
6. **R6 多租户/队列**：支持多账号与任务排队，保障资源隔离。
7. **R7 观测性与看板**：构建指标、日志与可视化看板。

### ASCII 架构草图
```
+-----------+     +---------------+     +--------------------+
| Scheduler | --> | Article Gen   | --> | Dedup (DB)         |
+-----------+     +---------------+     +--------------------+
                            |                 |
                            v                 v
                    +---------------+   +--------------------+
                    | Delivery Hub  |-->| Platform Adapters |
                    +---------------+   +--------------------+
                            |
                            v
                      Structured Log
```

## 3. 系统架构与模块说明
- **generator/**：文章生成占位模块。当前从模板读取文本，后续将在 R3 引入主题库、大纲、风格模板和反重复 Prompt。
- **dedup/**：去重逻辑，基于关键词集合与数据库历史记录判断重复，同时预留语义相似度/嵌入接口。
- **delivery/**：投递中心，包含抽象基类与各平台适配器；真实实现需填充 REST/自动化调用。
- **db/**：数据库层，包含 ORM 模型、迁移脚本和 schema.sql（articles、keywords、runs 等表）。
- **config/**：集中配置与日志初始化，支持 .env 与结构化日志。
- **utils/**：通用工具方法（分组、时间等）。
- **infra/**：若部署在 VPS，可在 `app/vps_manager.py` 扩展创建/销毁脚本，遵循最小权限原则。

## 4. 安装与环境准备
### 依赖管理方案一：pip + requirements.txt
```bash
python -m venv .venv
source .venv/bin/activate  # Windows 使用 .venv\Scripts\activate
pip install -r requirements.txt
```

### 依赖管理方案二：Poetry（或兼容的 uv）
```bash
curl -sSL https://install.python-poetry.org | python -
poetry install
```

### Python 与初始化要求
- Python 3.11 及以上版本。
- 推荐在虚拟环境中运行，避免污染系统环境。
- 首次拉取后执行 `make init`（安装依赖 + 初始化数据库）。
- 配置 `.env` 文件，可参考 `.env.example`。

### `.env.example` 字段说明
```dotenv
DB_URL=sqlite:///./local.db        # 仅示例；请勿提交实际 .db 文件
LOG_LEVEL=INFO
TIMEZONE=Asia/Tokyo
WORDPRESS_BASE_URL=
WORDPRESS_USERNAME=
WORDPRESS_APP_PASSWORD=
MEDIUM_INTEGRATION_TOKEN=
WECHAT_APP_ID=
WECHAT_APP_SECRET=
GROQ_API_KEY=
FIREWORKS_API_KEY=
HF_API_TOKEN=
VLLM_BASE_URL=
OLLAMA_BASE_URL=
```
> 提醒：不要提交真实密钥；生产环境建议接入密钥管理服务（如 AWS Secrets Manager、Vault）。

### 快速上手任务清单（TL;DR）
1. **复制环境变量模版**：`cp .env.example .env` 并按照下表填写必填项。
2. **准备依赖与数据库**：创建虚拟环境 → 安装依赖 → `make init` 生成基础表结构。
3. **验证生成链路**：执行 `python app/main.py --topic "示例主题"` 查看命令行输出。
4. **批量导出草稿**（可选）：按需运行 `python cli.py export wechat --date YYYY-MM-DD` 等命令产出素材包。
5. **自动化送稿**（可选）：提前登录浏览器后执行 `python cli.py auto wechat --date YYYY-MM-DD`。
6. **生产化调度**：配置 cron 或运行 `python -m app.scheduler`，并在 `.env` 中设置 `SCHEDULE_CRON` 与每日产量。

### LLM 推理配置（Meta/Llama）
- **本地优先（推荐）**：安装 [Ollama](https://ollama.com/download)，执行 `ollama pull llama3.1:8b` 拉取模型，在 `autowriter_text/config.yaml` 中保持 `provider=ollama` 即可使用本地推理。必要时可通过 `.env` 中的 `OLLAMA_BASE_URL` 覆盖服务地址。
- **云端可选**：若选择 Groq、Fireworks 或 Hugging Face Inference Endpoints，请在 `.env` 中填入对应的 `GROQ_API_KEY`、`FIREWORKS_API_KEY`、`HF_API_TOKEN` 等凭据，并在配置文件中设置合适的 `llm.provider` 与 `llm.model`。自建 vLLM 服务可通过 `VLLM_BASE_URL` 指定地址。

> 提示：Meta Llama 模型遵循非开源许可，仅允许在许可范围内进行推理。本项目仅调用已安装的权重，不包含任何模型文件，请在生产环境中确保合规使用。

### 首次运行完整步骤
1. `git clone https://github.com/.../auto-writer.git`
2. 进入目录：`cd auto-writer`
3. 创建并激活虚拟环境（见上文）。
4. 安装依赖（pip 或 poetry）。
5. 复制 `.env.example` 为 `.env` 并填入占位/真实值。
6. 执行 `make init` 以初始化数据库结构。
7. 运行一次：`python app/main.py --topic "示例主题"` 或 `make run`。
8. 查看日志：命令行输出为 JSON，包含 run_id、platform、status 等字段。

### 环境变量填写与调整对照表
| 分类 | 变量 | 是否必填 | 作用 | 需要执行的操作 |
| --- | --- | --- | --- | --- |
| 核心运行 | `DB_URL` / `DATABASE_URL` | 可选 | 设置数据库连接，默认使用本地 SQLite | 使用云端数据库时修改；本地演示可保持默认 |
| 核心运行 | `LOG_LEVEL` | 可选 | 控制日志级别 | 根据排障需求调高/调低 |
| 核心运行 | `TIMEZONE` | 建议填写 | 控制调度与日志所使用的时区 | 根据团队所在地区修改 |
| 调度策略 | `DAILY_ARTICLE_COUNT` | 建议填写 | 每日目标产稿数（默认 3） | 根据生产计划调整 |
| 调度策略 | `KEYWORD_RECENT_COOLDOWN_DAYS` | 可选 | 关键词冷却窗口 | 若需更快复用关键词则调小 |
| 调度策略 | `POSTRUN_ENRICH_GROUP_SIZE` | 可选 | 事后补充分组阈值 | 保持默认或按批量需求调整 |
| 调度策略 | `ENABLE_POSTRUN_ENRICH` | 可选 | 是否开启补充逻辑 | 不需要补充时改为 `false` |
| Cron 调度 | `SCHEDULE_CRON` | 必填（生产） | APScheduler/cron 的表达式 | 在自动化部署时填写 |
| VPS Worker | VPS_*（SSH_HOST/SSH_USER/SSH_PORT/SSH_KEY_PATH/WORKDIR） | 可选 | 定义远程 worker 登录信息 | 启用 VPS 模式时填写 |
| 平台凭据 | WordPress_*（BASE_URL/USERNAME/APP_PASSWORD） | 可选 | WordPress 凭据 | 启用 WordPress 投递时填写 |
| 平台凭据 | `MEDIUM_INTEGRATION_TOKEN` | 可选 | Medium API Token | 投递 Medium 时填写 |
| 平台凭据 | WeChat_*（APP_ID/APP_SECRET） | 可选 | 微信公众号草稿接口凭据 | 启用公众号 API 时填写 |
| LLM/推理 | `OLLAMA_BASE_URL` / `LLM_BASE_URL` | 可选 | 本地或统一大模型服务地址 | 变更默认端口或远程推理时修改 |
| LLM/推理 | `GROQ_API_KEY`、`FIREWORKS_API_KEY`、`HF_API_TOKEN`、`VLLM_BASE_URL` | 可选 | 各云端推理凭据 | 选择对应云厂商时填写 |
| 历史兼容 | `OPENAI_API_KEY` | 可选 | 兼容旧逻辑的占位字段 | 如需切换到 OpenAI 模型再填写 |

> 建议将 `.env` 仅保存在本地开发环境或密钥管理系统中，生产环境通过 CI/CD 动态注入，避免凭据泄露。

### Dashboard OIDC 单点登录配置
- **默认关闭**：`OIDC_ENABLE=false`，仍然保留用户名/密码登录；仅当企业 IdP 已准备就绪时才建议开启。
- **配置步骤**：
  1. 设置以下环境变量并重启 Dashboard：
     - `OIDC_ENABLE=true`
     - `OIDC_ISSUER=https://id.example.com`（IdP Issuer，支持 `.well-known/openid-configuration`）
     - `OIDC_CLIENT_ID=`、`OIDC_CLIENT_SECRET=`（在 IdP 上注册的客户端；密钥必须通过环境变量注入，不要写入仓库或日志）
     - `OIDC_REDIRECT_PATH=/auth/oidc/callback`（可改为企业门户统一路径，但需同步更新 IdP 回调列表）
     - `OIDC_AUTO_CREATE_VIEWER=true`（默认开启首次登录自动创建 viewer 账号，可按需改为 `false`）
  2. 确认 Dashboard 仍然绑定回环地址（例如 `DASHBOARD_BIND=127.0.0.1:8787`），通过反向代理/隧道对外发布，确保 OIDC 回调仅在受控网络中暴露。
  3. 在 IdP 后台将 `https://<dashboard-host>/auth/oidc/callback`（或自定义路径）加入白名单，scope 建议包含 `openid email profile`。
- **登录流程**：用户可选择“使用企业登录 / SSO 登录”跳转 IdP，验证成功后系统会将 email/sub 映射到本地账号；首登时可自动创建 viewer 角色，也可在禁用自动创建时预先建号。
- **安全注意事项**：
  - OIDC 客户端密钥仅通过环境变量读取，系统不会在日志或配置导出中展示。
  - 回调页面仅负责下发本地 JWT，推荐依旧限制 Dashboard 的公网暴露，必要时结合 VPN 或零信任代理。
  - 若需停用 OIDC，重置 `OIDC_ENABLE=false`，原有本地账号仍可使用。

### 需要调整的本地配置文件
- `autowriter_text/config.yaml`：控制生成模型 (`llm.provider`、`llm.model`、`llm.base_url`)、批量大小 (`batch.count`) 与去重范围 (`dedup.scope`)，如需切换到云端推理或增减每日草稿，可在此修改后重启任务。
- `app/generator/prompts/article_prompt_template.txt`：定义文章写作模板与语气，若要适配新风格或不同语言，请在保证结构完整的情况下修改该文件。
- `jobs/job.schema.json`（仅 orchestrator + VPS 模式使用）：若需扩展下发字段（如新增渠道参数），请遵循 JSON Schema 更新并同步 orchestrator/worker。

## 5. 运行与调度
### 项目使用方式概览
- **一次性生成并投递**：`python app/main.py --topic "示例主题"`，适用于快速验证端到端链路。
- **批量生成与自动导出**：`python main.py`（交互式向导）按步骤配置 Provider、批量大小、送稿参数，随后调用 `autowriter_text` 管道生成素材。
- **导出与送稿辅助**：`python cli.py export|copy|auto ...` 对应生成素材包、手动剪贴板和自动化草稿录入三类场景。
- **守护式调度**：`python -m app.scheduler` 或系统 cron 按计划运行 `app/main.py`。

### 本地一次性运行
```bash
python app/main.py --topic "示例主题"
# 或
make run
```

### 定时运行方式一：内置 APScheduler
- 配置 `TIMEZONE` 与 `SCHEDULE_CRON`（如 `0 9 * * *`）。
- 运行 `python -m app.scheduler`（可在独立进程中执行）。

### 定时运行方式二：系统 cron
```cron
0 9 * * * /usr/bin/python /path/to/app/main.py --topic "今日热点" >> /var/log/autowriter.log 2>&1
```
- 建议将日志重定向到专用文件并配合 logrotate。

### 幂等与失败重试
- `runs` 表记录每次执行状态，可在调度前检查是否已有成功记录。
- `platform_logs`（预留）可写入投递结果，用于判断是否需要重试。
- 结合 `articles`/`keywords` 唯一约束，避免重复写入同一篇文章。

### 从启动到完成的端到端流程拆解
以下步骤解释 `python app/main.py --topic "示例主题"` 时后台具体调用链，适合零基础读者对照源码理解：
1. **命令行入口**（`app/main.py`）
   1. `argparse` 解析 `--topic` 参数，默认值为 “AI 技术趋势”。
   2. `main()` 函数写入结构化日志并调用 `init_database()` 确保 SQLite/外部数据库存在所需表结构。
2. **文章生成阶段**
   1. 构造 `ArticleGenerator`（`app/generator/article_generator.py`），传入 `.env` 中配置的 LLM 凭据。
   2. `generate_article()` 读取 Prompt 模板、合成标题/摘要/正文并返回字典，若 LLM 不可用则返回示例内容。
3. **重复检测阶段**
   1. `ArticleDeduplicator.is_unique()`（`app/dedup/deduplicator.py`）比对标题、关键词与历史记录。
   2. 若命中重复则记录日志并停止流程；否则继续下一步。
4. **平台投递阶段**
   1. 根据配置构建 `MediumDeliveryAdapter`、`WordPressDeliveryAdapter`、`WeChatMPDeliveryAdapter` 列表（`app/delivery/*.py`）。
   2. 循环执行 `adapter.deliver(article_payload)`：当前为占位实现，实际部署时应填充 REST API 或浏览器自动化逻辑。
   3. 每个平台调用结束后写入 `delivery_success` / `delivery_failed` 日志，并在混沌注入启用时测试限速与异常场景。
5. **运行收尾**
   1. 生成器返回的数据会写入 `articles`/`keywords` 表，供 CLI 导出或 Dashboard 展示。
   2. `main()` 末尾打印“流程结束”日志，调度器据此判断该任务是否成功。

如需深入了解“批量生成→导出→自动送稿”流程，可在完成一次 `app/main.py` 运行后按顺序执行：`python main.py`（交互式批量）、`python cli.py export all`、`python cli.py auto all`，每一步在终端提示所调用的模块和函数，便于逐一对照。

## 6. 半自动导入（公众号/知乎）
基于 V7.2 半自动导出方案，可在不调用平台 API 的情况下完成公众号与知乎草稿导入：

### 公众号导入 SOP
- 执行 `python cli.py export wechat --date YYYY-MM-DD`（默认为当天），在 `exports/wechat/YYYY-MM-DD/` 下生成 5 篇素材包。
- 每篇目录包含 `title.txt`、`digest.txt`、`article.html`、`article.md`、`paste_wechat.txt`、`images/` 与 `README_IMPORT.md`。
- 后台草稿操作：
  1. 复制 `title.txt` 到标题输入框；
  2. 复制 `digest.txt` 到摘要栏（系统会自动截断至 **≤120 汉字**）；
  3. 打开 `article.html`，使用源码粘贴模式填入正文；
  4. 按 `images/` 目录内文件顺序手动上传配图（若目录为空可跳过）；
  5. 若需要一键粘贴，可使用 `paste_wechat.txt`（首行标题、次行摘要、剩余为 HTML 正文）。
- 导出完成后会额外生成 `exports/wechat/YYYY-MM-DD/index.csv`、`index.json` 以及 `exports/wechat_{YYYY-MM-DD}.zip` 方便归档。

### 知乎导入 SOP
- 执行 `python cli.py export zhihu --date YYYY-MM-DD`（默认为当天），在 `exports/zhihu/YYYY-MM-DD/` 下获得 5 篇草稿素材。
- 每篇目录包含 `title.txt`、`article.md`、`article.html`、`paste_zhihu.txt`、`images/` 与 `README_IMPORT.md`。
- 写作页操作：
  1. 复制 `title.txt` 到知乎标题；
  2. 复制 `article.md`，选择“Markdown 粘贴”或使用 `Ctrl+Shift+V` 粘贴；
  3. 按需参考 `README_IMPORT.md` 上传图片并核对元信息；
  4. `paste_zhihu.txt` 可在紧急情况下一次粘贴标题 + 正文。
- 导出完成后同样生成 `index.csv`、`index.json` 与 `exports/zhihu_{YYYY-MM-DD}.zip`。

### 一键打包与剪贴板助手
- 使用 `python cli.py export all --date YYYY-MM-DD` 可同时生成两个平台的目录，并在 `exports/bundle_all_{YYYY-MM-DD}.zip` 输出合并包交付助手。
- 若需要逐段复制，可运行 `python cli.py copy wechat --date YYYY-MM-DD --index N` 或 `python cli.py copy zhihu --date YYYY-MM-DD --index N`，系统会依次将标题、摘要/正文放入剪贴板，每一步按回车继续。

## 7. 自动送草稿（本机浏览器自动化，无需 API）
1. 启动本机 Chrome：退出所有实例后以 `chrome --remote-debugging-port=9222` 或等效方式重新打开，并在该窗口中提前登录「公众号后台」与「知乎写作页」。
2. 运行命令：
   - `python cli.py auto wechat --date YYYY-MM-DD [--limit 5] [--cdp http://127.0.0.1:9222]`
   - `python cli.py auto zhihu  --date YYYY-MM-DD [--limit 5] [--cdp http://127.0.0.1:9222]`
   - `python cli.py auto all    --date YYYY-MM-DD [--limit 5]`
   CLI 会按顺序读取当日导出包的前 N 篇文章，通过 Playwright 连接到已登录的浏览器并自动创建草稿。
3. 关注输出：每篇文章都会打印成功/失败状态；异常时会在 `automation_logs/YYYY-MM-DD/` 生成截图，便于排查。
4. 若检测到登录或验证码拦截，命令行会提示“请在该浏览器完成登录后按 Enter 继续”，请切换到对应标签页完成后再回车。
5. 每次运行会在 `automation_logs/<DATE>/summary.json` 写入结构化结果，记录成功/跳过/失败原因与截图路径。

### 常见问题
- **页面元素找不到或保存失败**：平台 UI 改版时请参考 `automation_logs/` 内的截图，更新 `automation/` 下的选择器或流程。
- **登录过期/出现验证码**：脚本会提示人工处理，请在对应浏览器标签页完成验证后重新执行命令。
- **操作节奏过快**：可通过 `--min-interval` 与 `--max-interval` 参数控制跨篇等待区间（默认 6-12 秒），`--max-retries` 指定单篇重试次数。
- **公众号 HTML 支持范围**：正文粘贴前会执行白名单清洗，保留 `p/br/strong/em/h1-h4/blockquote/ul/ol/li/img/a/code/pre/span` 标签；`img` 仅接受 http/https 链接，若存在相对路径会插入 “TODO 请上传图片” 提示。
- **重复保护**：自动以 RapidFuzz 对比近 14 天标题，相似度 ≥ 85 将标记为 `similar to <历史标题>` 并跳过；阈值与窗口可在 `pipeline/postprocess.py` 调整。
- **DRY-RUN**：传入 `--dry-run` 可只验证选择器与粘贴流程，不执行保存，终端会显示 `DRY RUN ✓`。

> 说明：该功能仅用于本机辅助提效，不会采集或存储账号口令。请在遵守平台服务条款与使用规范的前提下使用，避免高频、批量或异常自动化行为。

## 8. 平台草稿投递（占位实现说明）
- **WordPress（REST）**：POST `https://<site>/wp-json/wp/v2/posts`，需 Basic Auth 或 Application Password，body 包含 `status: draft`、`title`、`content`、`categories`、`tags`。建议使用 HTTPS，处理 401/403/429 等状态码。
- **Medium 草稿**：POST `https://api.medium.com/v1/users/{userId}/posts`，Header `Authorization: Bearer <token>`，body 包括 `title`、`contentFormat`、`content`、`tags`、`publishStatus: draft/unlisted`。若草稿 API 受限，可退化为未公开发布并记录返回 URL。
- **微信公众号草稿**：
  - 开放平台接口：POST `https://api.weixin.qq.com/cgi-bin/draft/add?access_token=...`，body 提供图文数组、digest、评论开关等。
  - 后台 Web 流程：POST `/cgi-bin/operate_appmsg`，需 Cookie、token、XSRF 参数，涉及素材上传与审核。
  - 注意内容合规、审核延时与调用频率限制。
- **Playwright 无头备选**：适用于无开放接口的平台。占位函数说明了启动浏览器、登录、填表、上传、提交的推荐步骤，同时强调不生成持久缓存。

## 9. 数据库与去重策略
- 表结构：
  - `articles`：标题、正文、创建时间。
  - `keywords`：文章外键 + 关键词文本。
  - `runs`：运行状态、详情、时间戳。未来可扩展 `platform_logs` 表记录平台结果。
- 当前去重：
  - 先查标题是否重复。
  - 再以关键词集合扫描历史记录，存在交集即视为重复。
  - 事务原则：“执行前扫描 + 生成后回写”，可通过唯一索引与事务避免竞态。
- 扩展方向：
  - 预留 `# TODO` 接口，引入 MinHash/SimHash、TF-IDF 或向量嵌入比对。
  - 在关键词库中记录权重、主题标签以提升精度。

## 10. 日志、监控与排障
- 结构化日志字段建议：`run_id`、`platform`、`status`、`latency_ms`、`error`。
- 常见错误：
  - **网络超时**：建议在请求层增加重试与退避。
  - **鉴权失败**：检查 token 是否过期，避免在日志中输出敏感凭证。
  - **限流/非 2xx**：记录响应 body，必要时触发报警。
- 监控建议：接入 ELK / Loki / CloudWatch，并结合 metrics 统计成功率、耗时、重复率。

### Prometheus 指标导出
- Dashboard 默认在 `http://127.0.0.1:8787/metrics` 暴露 Prometheus 指标（可通过 `PROMETHEUS_ENABLED` 开关控制）。
- 可在 `prometheus.yml` 中追加抓取配置：
  ```yaml
  scrape_configs:
    - job_name: autowriter_dashboard
      metrics_path: /metrics
      static_configs:
        - targets: ["127.0.0.1:8787"]
  ```
- 指标包含运行总数、生成次数、按平台投递结果、作业耗时直方图与插件错误计数，便于构建成功率与耗时趋势图。
- **生产环境注意**：仅在本机或内网暴露 `/metrics`，建议结合反向代理、mTLS 或防火墙限制访问来源，避免指标接口被滥用。

### 告警规则与通知脚本
- 目录 `ops/alerts/` 提供 Prometheus/Alertmanager 配置模板与脚本：
  - `prometheus.rules.yml` 定义 Dashboard 宕机、队列积压、死信激增、Worker 心跳超时与投递失败率等告警，默认阈值可按业务规模调整。
  - `alertmanager.yml.example` 演示如何按严重级别路由到飞书、Slack、通用 Webhook 与 SMTP 邮件，所有凭据通过环境变量注入（启动 Alertmanager 时需加 `--config.expand-env`）。
  - `webhook/notify_*.py` 与 `smtp/send_mail.py` 基于 FastAPI + httpx/smtplib，支持重试、从标准输入触发，以及通过 `uvicorn ops.alerts.webhook.notify_feishu:APP --reload` 等方式运行成 Webhook 服务。
- 将 `prometheus.rules.yml` 挂载到 Prometheus 容器示例：
  ```bash
  docker run -v "$(pwd)/ops/alerts/prometheus.rules.yml:/etc/prometheus/rules/autowriter.yml" \
    -v "$(pwd)/config/prometheus.yml:/etc/prometheus/prometheus.yml" prom/prometheus
  ```
  在主配置内追加 `rule_files: ['/etc/prometheus/rules/*.yml']` 即可加载该规则。
- 使用 `alertmanager.yml.example` 启动 Alertmanager：
  ```bash
  export ALERT_FEISHU_WEBHOOK_URL=https://open.feishu.cn/...
  export ALERT_SLACK_WEBHOOK_URL=https://hooks.slack.com/services/...
  docker run --env-file .env.alerts \
    -v "$(pwd)/ops/alerts/alertmanager.yml.example:/etc/alertmanager/alertmanager.yml" \
    prom/alertmanager --config.expand-env
  ```
  也可在本地执行 `./alertmanager --config.file=ops/alerts/alertmanager.yml.example --config.expand-env` 进行快速测试。
- Webhook/SMTP 脚本接入方式：
  - Webhook：在 Alertmanager 中将 `url` 指向 `http://<host>:<port>/webhook`，通过环境变量设置下游地址和 Token；脚本自带 CLI，可 `cat payload.json | python ops/alerts/webhook/notify_generic.py` 验证。
  - 邮件：`smtp/send_mail.py` 读取 `ALERT_SMTP_HOST/PORT/USERNAME/PASSWORD` 等变量，支持纯文本 + HTML，同时支持 `ALERT_SMTP_USE_SSL`、`ALERT_SMTP_USE_STARTTLS` 控制传输安全。
- Dashboard 新增 `/alerts` 只读页面，`ALERTS_PULL_ENDPOINT` 环境变量可指向 Alertmanager `api/v2/alerts` 或自建聚合服务，用于在内网浏览当前 firing/pending 告警。
- **合规提示**：Alertmanager Webhook/SMTP 凭据必须存放在内网与密钥管理系统中，脚本默认不写入硬编码密钥；请限制告警接口只在公司 VPN 或受控子网中暴露。

### 人工复核工作流
- Dashboard 新增 `/review` 页面，需具备 `operator` 及以上角色方可访问。页面分为待审核列表与详情区，支持快速查看质量分、Prompt Variant 与命中规则。
- 复核节点可对标题、摘要、标签与正文做小幅编辑，提交后会记录差异（字段、字符偏移、编辑人与时间）写回 `ReviewQueue.diffs_json`。
- 操作按钮：
  - **保存修改**：调用 `POST /review/{id}/patch`，仅允许白名单字段；
  - **通过**：`POST /review/{id}/approve`，回写审核人、时间，并依据配置决定是否自动投递；
  - **驳回**：`POST /review/{id}/reject`，记录原因并将草稿状态更新为 `rejected`。
- 所有审核动作会同步至 `ContentAudit`，并调用 Prompt 反馈模块微调 Variant 权重，避免优劣 Prompt 权重震荡。

### 抽检比例与自动投递配置
- `QA_SAMPLING_RATE`：控制质量闸门通过后进入人工复核队列的抽检比例（默认 `0.2`，即 20%）。
- `QA_EDIT_ALLOW_FIELDS`：逗号分隔或在配置文件中覆盖的字段白名单，默认 `title,tags,summary,body`。
- `QA_APPROVE_AUTODELIVER`：布尔值，开启后复核通过会立即调用投递流程。
- 修改上述环境变量后重新启动服务即可生效；如需运行时观测当前配置，可在 Dashboard 登录后访问 `/review` 顶部的提示或调用 `/review/queue` API。

## 11. 开发、测试与质量
- 常用命令：
  - `make lint`：运行 Ruff 检查与格式化。
  - `make test` 或 `pytest -q`：执行测试。
  - `make run`：快速手动验证流程。
- 新平台适配器开发步骤：
  1. 在 `app/delivery/` 复制 `base.py` 提供的接口模板。
  2. 实现 `deliver()`，构造真实 API 请求或自动化脚本。
  3. 在 `app/main.py` 注册适配器实例。
  4. 在 `.env` 中补充新平台所需的密钥/URL。
  5. 编写测试模拟 API 响应，确保异常路径覆盖。
- 代码规范：遵循 PEP8、使用类型标注、统一中文注释说明，异常需明确抛出或记录。

## 12. 安全与合规
- 密钥管理：使用环境变量或密钥服务，避免硬编码；日志中勿输出敏感值。
- 速率限制：对接平台 API 时遵守限流规则，可结合队列/重试策略。
- 内容合规：生成 Prompt 与素材需遵循版权、平台政策及隐私要求，必要时接入人工审核。
- 仓库约束：禁止提交二进制文件（数据库、截图、缓存等）。
- 使用自动化脚本时仅针对本人账号操作，严格遵守各平台服务条款与使用边界。

## 13. FAQ 与未来计划
- **运行后数据库在哪里？** 默认使用 SQLite 文件，可通过 `DATABASE_URL` 切换 PostgreSQL 等；推荐将生产数据库放在托管服务。
- **如何避免重复生成？** 去重服务在生成前扫描历史记录，投递成功后应写入 `articles/keywords` 表。
- **是否支持多语言？** 当前模板为中文；可在 R3 之后扩展多语言 Prompt 与翻译流水线。
- **开源计划？** 后续将根据路线图开放贡献指南，欢迎提交 Issue 与 PR。

## 14. 文章生成规范（R3）
- **生成目标**：文章需融合影评风格与学术分析，约 2000 字，整体语调冷静理性。
- **禁止事项**：严格禁止使用第一人称、呼吁性措辞以及引用影视作品台词，确保文本客观中立。
- **选题范围**：每次生成从数据库 `psychology_themes` 表抽取未使用的「心理学关键词 × 影视角色」组合，覆盖动画、电影与各类剧集中的心理、悬疑、存在主义等主题。
- **模板与流程**：`app/generator/prompts/article_prompt_template.txt` 定义了文章结构（概念引入→角色切入→深入剖析→学术讨论→冷静收尾）及标题格式，`ArticleGenerator` 会在加载模板后注入关键词、定义、角色与剧名并回写使用状态。

### 角色库管理
- **数据位置**：`app/generator/characters.json` 以 JSON 数组存放角色条目，每个对象包含 `name`（角色名）、`work`（作品名）、`traits`（心理学特质列表）。
- **扩展方法**：新增角色时请保持 UTF-8 编码，补全上述三个字段，`traits` 建议至少包含 3 个能够支撑心理分析的关键描述。
- **唯一性约束**：确保 `(name, work)` 组合全局唯一，避免因角色重名导致随机选择或检索出现混淆。

---
如需更多帮助，请在 Issue 中反馈或加入后续讨论。
## 15. 本轮架构更新（本机持久库 + VPS 无状态）
### 架构概览
- **本机常驻**：持久化数据库仅存在于本机（默认 SQLite，可切换 PostgreSQL）。负责选题规划、used_pairs 去重、runs 统计与关键词池维护。
- **VPS 临时实例**：每日临时创建，仅读取传入的 `job.json` 与 `.env.runtime`，执行完立刻销毁或由本机回收，不持久化任何密钥。

### 数据流
1. 本机 orchestrator 读取数据库与配置，计算当日目标篇数。
2. Planner 选取「未用或冷却窗外」关键词，并根据角色 traits 匹配角色。
3. Preflight 去重：优先检查 `used_pairs` 当日重复，其次预留相似度哈希占位。
4. 生成 `job.json` 与 `.env.runtime`（纯文本）并通过 SSH 传至 VPS 临时目录。
5. VPS 执行 `app/worker/remote_worker.py` 渲染草稿并投递草稿箱，返回 `result.json` 与 `worker.log.txt`。
6. 本机回收结果，落库更新 runs/used_pairs/platform_logs，并触发 “3 消耗 3 补齐” 的热度补全。

### 密钥生命周期与最小暴露
- 所有长期密钥仅保存在本机 `.env` 中。
- 打包阶段生成一次性的 `.env.runtime`，只包含当次投递所需的凭据。
- VPS worker 运行结束后主动删除 `.env.runtime`，orchestrator 也会在回收阶段触发删除。

### 失败重试与容错
- 若 VPS 执行失败，可在本机保留 `job.json` 并重新触发；未成功的 run 仍标记为 `scheduled` 方便次日继续。
- 日志与 `result.json` 全部回传，本机可根据 `runs.status` 与 `platform_logs` 判断是否需要补投。

### 运行示例
```bash
# 本机一次性执行
python app/orchestrator/orchestrator.py --date 2025-10-02 --articles 3

# 或使用 Makefile（支持 DATE/ARTICLES 环境变量）
make run-local-orchestrator DATE=2025-10-02 ARTICLES=3
```

### 数据与仓库约束
- 仓库保持纯文本，严禁提交 `.db`、缓存或其他二进制产物。
- `jobs/job.schema.json` 提供统一 Schema，所有作业必须遵循。

### SSH 最小权限说明
- 建议为 orchestrator 使用仅限目标 IP 的密钥对，并限制命令执行范围。
- VPS 临时目录（默认为 `/home/ubuntu/autowriter_run`）需具备最小读写权限，执行完成后应清理残留文件。

## 16. 验收清单
- 同一批次触发幂等键后，第二次执行会被拒绝并在日志中记入审计信息。
- 模拟平台接口失败可观察到自动重试；超过上限后任务进入死信状态并将草稿移动到隔离目录。
- Worker 心跳超过两倍轮询间隔时，Dashboard 会将对应行标红提示掉线。
- `/metrics` 端点中的 Prometheus 指标会随着任务成功、失败与重试实时更新。
- Electron 客户端关闭时应确认所有子进程被正确回收，不留下残留会话或僵尸进程。

## 17. Prompt 策略与质量闸门（R5）
### Prompt 版本管理与权重配置
- 新增 Prompt 模板请放在 `app/prompting/prompts/` 目录，文件名即 Variant 名称（如 `v1_academic_cn.txt`）。
- 模板会被注册中心自动加载，无需修改代码；建议在文件首行写明用途与风格备注，方便实验对照。
- Profile 可通过 `prompting` 配置段落指定策略与流量，例如：
  ```yaml
  prompting:
    max_attempts: 3        # 单篇文章最多尝试的 Prompt 数
    strategy:
      name: weighted      # round_robin / weighted / by_profile / traffic_split
      weights:
        v1_academic_cn: 0.6
        v2_academic_cn_tighter: 0.4
  ```
- `by_profile` 支持按 Profile 名称/ID 指定 Variant，也可嵌套其它策略形成更复杂的分流逻辑。

### 质量闸门指标与阈值
- **字数**：目标区间为 1800–2300 字，超出范围会立即触发下一 Variant 或人工复核。
- **可读性**：综合平均句长（≤45 字）、段落密度（约 4 句/段）与停用词占比，得分低于 0.6 判定失败。
- **风格一致性**：统计高频词与风格词典的覆盖率/密度，得分低于 0.5 时提示补充术语。
- **重复度**：默认使用 `scikit-learn` TF-IDF 余弦相似度（>0.8 视为重复），在缺少依赖时回退到 Jaccard 指标。
- **敏感模式**：命中呼吁性语言、第一人称或台词引用会直接置零并要求人工介入。
- `ContentAudit` 表保存最终分数、原因、全部 Variant 尝试明细与回退次数，Dashboard 新增的“Prompt 实验”页可实时查看并导出 CSV。

### 风格词典与历史文章对齐
- 自定义风格词典位于 `data/style_words.txt`（一行一个词）；文件不随仓库提交，可在部署时挂载。
- 质量闸门会自动读取该词典，计算风格覆盖率；建议将用户历史文章的高频词导入此文件以增强风格一致性评分。
- 若需要临时调整风格，只需更新该文件并重启服务即可，无需修改代码。
