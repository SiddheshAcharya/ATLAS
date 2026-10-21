.PHONY: up down logs migrate dev api web test test-int test-offline lint fmt reset health

up:            ## start postgres, neo4j, qdrant, grobid
	docker compose up -d
	@echo "waiting for services..." && sleep 8 && $(MAKE) health

down:
	docker compose down

reset:         ## DESTROYS all data
	docker compose down -v

logs:
	docker compose logs -f --tail=100

migrate:
	alembic upgrade head

health:
	atlas health

api:
	uvicorn atlas.api.main:app --reload --port 8000

web:
	cd web && npm run dev

dev:
	$(MAKE) -j2 api web

test:
	pytest -q tests/unit

test-int:
	pytest -q -m integration tests/integration

test-offline:  ## full pipeline against a real warm cache, zero live network (tests/e2e/conftest.py)
	pytest -q tests/e2e

lint:
	ruff check src tests && mypy src

fmt:
	ruff check --fix src tests && ruff format src tests
