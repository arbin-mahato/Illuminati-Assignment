.PHONY: api web test build

api:
	PYTHONPATH=backend python -m uvicorn app.main:app --reload --port 8000

web:
	npm --prefix frontend run dev

test:
	PYTHONPATH=backend pytest backend/tests -q

build:
	npm --prefix frontend run build
