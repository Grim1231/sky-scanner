# Sky Scanner

Personalized flight price scanner with 4-Layer parallel crawling.

## Project Structure

uv workspace monorepo:
- `packages/core/` - Shared models, schemas (Pydantic)
- `packages/db/` - SQLAlchemy models, Alembic migrations
- `packages/ml/` - DA models, scoring, routing algorithms
- `apps/api/` - FastAPI server
- `apps/crawler/` - 4-Layer crawler engine (L1: Google Protobuf, L2: Kiwi API, L3: Playwright)
- `apps/scheduler/` - Celery-based crawling scheduler
- `apps/web/` - Next.js frontend (TypeScript, separate from uv workspace)

## Commands

```bash
uv sync --dev              # Install all dependencies
uv run ruff check --fix .  # Lint + auto-fix
uv run ruff format .       # Format
uv run ty check .          # Type check (beta)
uv run pytest              # Run tests
uv run pre-commit run -a   # Run all pre-commit hooks
```

## Conventions

- Python 3.13+, type hints required
- ruff for linting/formatting (replaces black, isort, flake8)
- src layout for all packages
- Async-first (asyncpg, httpx, FastAPI)
- Pydantic v2 for all schemas
- Branch strategy: `main` <- `dev` <- `feature/*` (Dev), `da/*` (DA)
