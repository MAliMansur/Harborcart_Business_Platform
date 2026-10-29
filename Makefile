PYTHON ?= python3
.DEFAULT_GOAL := help
.PHONY: help preflight bootstrap install setup check test test-postgres run worker drain reconcile recovery compose-up compose-seed compose-down observe
help:
	@echo "Local: preflight bootstrap install setup check test run worker drain reconcile recovery"
	@echo "Docker gate: compose-up compose-seed test-postgres observe compose-down"
preflight:
	$(PYTHON) scripts/preflight.py
bootstrap:
	$(PYTHON) scripts/bootstrap.py
install:
	$(PYTHON) -m pip install --require-hashes -r requirements.lock
setup:
	$(PYTHON) manage.py migrate --noinput
	$(PYTHON) manage.py collectstatic --noinput
	$(PYTHON) manage.py seed_demo
check:
	$(PYTHON) manage.py check
	$(PYTHON) manage.py makemigrations --check --dry-run
test:
	$(PYTHON) manage.py test commerce.tests --settings=harbor.settings_test --verbosity=2
test-postgres:
	docker compose --profile tests run --rm tests
run:
	$(PYTHON) manage.py runserver 127.0.0.1:8080 --noreload
worker:
	$(PYTHON) manage.py worker --name worker-1
drain:
	$(PYTHON) manage.py worker --drain --name worker-1
reconcile:
	$(PYTHON) manage.py reconcile
recovery:
	$(PYTHON) manage.py recovery_check
compose-up:
	docker compose up --build -d db migrate web worker
compose-seed:
	docker compose exec web python manage.py seed_demo
compose-down:
	docker compose --profile observability down
observe:
	docker compose --profile observability up -d prometheus grafana
