.PHONY: init run lint test

init:
poetry install || pip install -r requirements.txt
python app/db/migrate.py

run:
python app/main.py

lint:
ruff check .
ruff format --check .
ruff format .
ruff check --fix .
echo "Linting complete"

test:
pytest
