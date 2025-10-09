.PHONY: init run lint test run-local-orchestrator deliver retry-due  # 新增: 声明新目标

init:
        # 初始化依赖：优先使用 poetry，若失败则回退到 pip
        poetry install || pip install -r requirements.txt
        # 执行数据库迁移，确保表结构创建
        python app/db/migrate.py

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
