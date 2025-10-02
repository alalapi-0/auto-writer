# AutoWriter 项目

## 项目目标与愿景
AutoWriter 致力于每天自动生成一篇约 2000 字的文章，并将文章推送到多个内容平台的草稿箱中，帮助创作者保持持续输出与多平台覆盖。

## 文件结构说明
- `README.md`：项目概述与操作指南。
- `pyproject.toml`：使用 Poetry 管理项目依赖与构建配置。
- `requirements.txt`：提供使用 `pip` 安装依赖的可选方案。
- `Makefile`：封装常用命令，便于开发与部署。
- `.gitignore`：忽略临时文件与敏感文件。
- `.env.example`：示例环境变量，需复制为 `.env` 并填写真实值。
- `config/`：包含统一配置与结构化日志设置。
  - `settings.py`：读取环境变量，生成应用配置对象。
  - `logging_conf.py`：定义结构化日志格式与日志器。
- `app/`：应用核心代码。
  - `main.py`：程序主入口，负责调度文章生成与投递流程。
  - `scheduler.py`：封装 APScheduler 调度逻辑，支持定时执行任务。
  - `generator/`：文章生成模块。
    - `article_generator.py`：调用大语言模型生成文章，目前使用占位实现。
    - `prompts/default_prompt.txt`：默认的 2000 字文章模板，包含可替换占位符。
  - `db/`：数据库模型与迁移。
    - `models.py`：SQLAlchemy ORM 定义。
    - `schema.sql`：SQLite/PostgreSQL 通用的建表语句。
    - `migrate.py`：初始化数据库与迁移占位逻辑。
  - `delivery/`：文章投递模块，负责将文章发送至各平台草稿箱。
    - `base.py`：平台适配器抽象基类。
    - `medium_adapter.py`：Medium 草稿箱示例适配器，包含伪代码说明。
    - `wordpress_adapter.py`：WordPress 草稿箱示例适配器。
    - `wechat_mp_adapter.py`：微信公众号草稿接口说明。
    - `playwright_driver.py`：Playwright 自动化占位实现。
  - `dedup/`：文章去重逻辑。
    - `deduplicator.py`：基于数据库记录的去重策略。
  - `utils/`：辅助函数集合。
    - `helpers.py`：通用工具方法。
  - `vps_manager.py`：VPS 生命周期管理占位文件。
- `tests/`：单元测试目录。
  - `test_basic.py`：基础的 pytest 测试示例。

## 开发环境配置步骤
### 本地开发
1. 安装 Python 3.11 及以上版本。
2. 克隆仓库后，在项目根目录执行 `python -m venv .venv` 创建虚拟环境。
3. 激活虚拟环境（Windows 使用 `\.venv\\Scripts\\activate`，Unix 使用 `source .venv/bin/activate`）。
4. 通过 `poetry install` 或 `pip install -r requirements.txt` 安装依赖。
5. 将 `.env.example` 复制为 `.env` 并填写 OpenAI API Key、数据库连接等必要配置。

### VPS 环境
1. 在云服务商创建运行 Python 3.11 的 VPS，确保具备定时任务与网络访问权限。
2. 克隆项目仓库并安装依赖。
3. 配置系统环境变量或 `.env` 文件，确保数据库与 API Key 可用。
4. 通过 `make init` 执行初始化脚本（迁移数据库、创建日志目录等）。
5. 配置守护进程或定时器（如 `systemd`、`cron`）调用 `make run` 或直接运行 `python app/main.py`。

## 运行方式
- 使用 Makefile：`make run`
- 直接运行 Python：`python app/main.py`

## 未来扩展计划
- 接入更多内容平台（知乎、头条、LinkedIn 等）。
- 引入文章分类、标签与多主题策略。
- 提供自动发布功能，支持预定时间上线。
- 集成内容质量分析与用户反馈回流。
- 扩展到多语言文章生成能力。

## 用户需要手动提供的内容
- OpenAI 或其他大语言模型服务的 API Key。
- 数据库连接字符串（SQLite 文件路径或 PostgreSQL URI）。
- 各平台的 OAuth/Token 或 Cookie 信息。
- VPS 创建、销毁脚本中的云厂商凭据与参数配置。
