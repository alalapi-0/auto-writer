.PHONY: init run lint test run-local-orchestrator deliver retry-due doctor report test-e2e playwright-install publish-all publish-one  # 新增: 声明新目标

init:
	# 初始化依赖：优先使用 poetry，若失败则回退到 pip
	poetry install || pip install -r requirements.txt
	# 执行数据库迁移，确保表结构创建
	python -m app.db.migrate

run:
	# 运行主程序，可在命令行传入 --topic 覆盖默认主题
	python app/main.py

run-local-orchestrator:
	# 本机 orchestrator 一次性执行，可通过 DATE 与 ARTICLES 覆盖
	python app/orchestrator/orchestrator.py $(if $(DATE),--date $(DATE),) $(if $(ARTICLES),--articles $(ARTICLES),)

deliver:
	# 手动触发分发流程，可通过 ARTICLE_ID 精确定位
	python scripts/deliver_once.py $(if $(ARTICLE_ID),--article-id $(ARTICLE_ID),)

retry-due:
	# 扫描 platform_logs 重试窗口并重新分发
	python scripts/retry_due.py

doctor:
        # 执行一键自检，输出配置、数据库与平台状态
        python -m scripts.doctor

run-dashboard:
        # 启动本地 Dashboard FastAPI 服务
        python -m app.dashboard.server

run-scheduler:
        # 启动调度服务，加载 Profile 并注册 APScheduler 任务
        python -m app.scheduler.service

add-user:
        # 通过 CLI 创建 Dashboard 用户，需指定 USER 环境变量
        python -m scripts.add_user --username $(USER) --role admin

report:
        # 导出可观测性报表，默认统计近 7 天
        python -m scripts.export_report --window 7

test-e2e:
	# 运行端到端集成测试确保关键链路可用
	pytest -q tests/integration

lint:
	# 先执行静态检查，再以 check 模式验证格式
	ruff check .
	ruff format --check .
	# 若格式不符，自动格式化并再次检查
	ruff format .
	ruff check --fix .
	@echo "Linting complete"

test:
        # 运行 pytest 测试用例
        pytest

playwright-install:
	# 安装 Chromium 以便 Playwright 自动化
	python -m playwright install chromium

publish-all:
	# 批量投递全部草稿，支持传入 --day 与 --platforms
	python -m scripts.publish_all

publish-one:
	# 仅投递单篇草稿，需指定平台与标题
	python -m scripts.publish_one --platform $(PLATFORM) --title "$(TITLE)"

run-gui:
	# 启动 PySide6 图形界面主入口
	python -m app.gui.main
