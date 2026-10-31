# Commandes du socle : le job Qualité (.github/workflows/ci.yml) appelle les
# mêmes cibles, pour qu'un test local et le CI ne divergent jamais.
.PHONY: test lint

# Tests et couverture : seuil et branches lus dans pyproject.toml.
test:
	uv run pytest --cov --cov-report=term-missing

lint:
	uv run ruff check . && uv run ruff format --check .
