.PHONY: up down build logs test clean

up:
	docker compose up --build -d

down:
	docker compose down

build:
	docker compose build

logs:
	docker compose logs -f

test:
	cd backend && python -m pytest tests/test_api.py -v

clean:
	docker compose down -v
