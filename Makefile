# 声明伪目标，避免与同名文件冲突
.PHONY: init run lint test

init:
	# 初始化依赖：优先使用 poetry，若失败则回退到 pip
	poetry install || pip install -r requirements.txt
	# 执行数据库迁移，确保表结构创建
	python app/db/migrate.py

run:
	# 运行主程序，可在命令行传入 --topic 覆盖默认主题
	python app/main.py

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
