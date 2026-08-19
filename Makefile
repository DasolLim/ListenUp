# One command per feedback loop. Every target is safe to run at any time: the
# backend is pinned to its mocks by `tests/conftest.py` and by
# `playwright.config.ts`, so nothing here spends money at a provider.
#
# A script that imports test helpers does NOT inherit conftest.py — that is how
# this repo burned two billed AssemblyAI sessions. Run things through these
# targets, not by hand.

BACKEND := cd backend && . .venv/bin/activate &&
FRONTEND := cd frontend &&

.PHONY: help check types lint test e2e all

help:
	@echo "make check   fast loop  — types, lint and unit tests, both stacks (~20s)"
	@echo "make e2e     browser    — boots backend + frontend, checks a11y/contrast/layout"
	@echo "make all     everything — check, then e2e"
	@echo ""
	@echo "make types / lint / test  run one loop across both stacks"

## The fast loop. Run this constantly; it is the one that should stay green.
check: types lint test

types:
	@$(BACKEND) mypy
	@$(FRONTEND) npm run typecheck

lint:
	@$(BACKEND) ruff check .
	@$(FRONTEND) npm run lint

test:
	@$(BACKEND) python -m pytest -q
	@$(FRONTEND) npm run verify

## The slow loop. Needs a production build, so it is a few minutes cold and
## seconds warm — Playwright reuses a server that is already up.
e2e:
	@$(FRONTEND) npm run e2e

all: check e2e
