# CLAUDE.md

## Project Overview

TarmacView — Drone Mission Planning Module for airport lighting inspection.
Python 3.12 + FastAPI backend, React 18 + TypeScript + Vite frontend, PostgreSQL 16.

## Build & Run Commands

```bash
# Backend — install deps
cd backend && pip install -r requirements.txt

# Backend — run dev server
cd backend && uvicorn app.main:app --reload

# Backend — run all tests
cd backend && pytest

# Backend — run single test file
cd backend && pytest tests/test_example.py -v

# Backend — lint
cd backend && ruff check .

# Backend — format check
cd backend && ruff format --check .

# Frontend — install deps
cd frontend && npm install

# Frontend — run dev server
cd frontend && npm run dev

# Frontend — run all tests
cd frontend && npx vitest run

# Frontend — run single test file
cd frontend && npx vitest run src/components/Example.test.tsx

# Frontend — lint
cd frontend && npm run lint

# Frontend — build
cd frontend && npm run build

# Database — start postgres
docker compose up -d postgres
```

## Code Style Rules

- **Polishing sweeps**: file length, docstrings, comments, named constants, and naming-consistency rules for behavior-neutral cleanup sweeps are canonically defined in the `polish-codebase` skill (`.claude/skills/polish-codebase/`). It is the single source of truth for those rules - do not fork them here.
- **Python imports**: stdlib → third-party → local (enforced by Ruff `I` rule)
- **Python naming**: `snake_case` files and functions, `PascalCase` classes
- **Python line length**: 100 characters max (Ruff config in `pyproject.toml`)
- **Frontend naming**: `PascalCase.tsx` for components, `camelCase.ts` for utilities
- **Frontend types**: `frontend/src/types/{domain}.ts`, use `interface` matching Pydantic schemas
- **Frontend design system**: Read `docs/specs/DESIGN-SYSTEM.md` before writing any components. Implement the CSS variables exactly as specified (`--tv-*`). Reference `docs/design-reference/` for visual patterns but do NOT copy Next.js patterns - use React 18 + Vite + react-router-dom. Every component must use `--tv-*` CSS variables, not placeholder/default Tailwind colors.
- **Schemas**: `{Entity}Response`, `{Entity}Create`, `{Entity}Update` for Pydantic DTOs
- **Routes**: `/api/v1/{resource}` (e.g., `/api/v1/missions`)
- **Error handling**: `HTTPException` in routes, custom exceptions in services
- **Docstrings**: every `def` function and `class` must have a `"""..."""` docstring - short, lowercase, one line when possible
- **Comments**: sparse, lowercase, casual. Follow these rules exactly:
  - Never comment what the code obviously does (`# enable postgis`, `# create engine`). If the code is self-explanatory, don't comment it.
  - Use short section labels above logical groups: `# test db config`, `# relationships`, `# runway-specific columns`
  - Use dashes (`-`) not em-dashes (`—`) in comments
  - Inline comments only for non-obvious things: `# discriminator`, `# noqa: F401`
  - Always a blank line before a section comment, no blank line between the comment and the code it describes
  - Add a blank line after a logical block ends (e.g. after `conn.commit()` before the next statement)
- **UUIDs**: `Column(UUID, primary_key=True, default=uuid4)` for all primary keys
- **Geometry**: WKT strings (`POINT Z (lon lat alt)`, `LINESTRING Z (...)`, `POLYGON Z ((...))`) stored in `Column(String)`; convert via `app.core.geometry`
- **Frontend i18n**: All user-facing strings use `react-i18next`. Translation files in `frontend/src/i18n/locales/{lang}.json`. Use `useTranslation()` hook + `t()` calls. Nest keys by page/component. Never hardcode user-visible text in JSX. Adding a new language requires only a new JSON file + registering it in `src/i18n/index.ts`.

## Project Structure

```
drone-mission-planning-module/
├── backend/
│   ├── app/
│   │   ├── api/routes/     # FastAPI routers — HTTP layer only
│   │   ├── core/           # config, database, auth, dependencies
│   │   ├── models/         # SQLAlchemy ORM models
│   │   ├── schemas/        # Pydantic v2 request/response DTOs
│   │   ├── services/       # All business logic
│   │   ├── utils/          # shared utility helpers
│   │   └── main.py         # FastAPI app + CORS + middleware
│   ├── migrations/         # Alembic migration files
│   ├── tests/              # pytest test files
│   └── requirements.txt    # Pinned deps (PROTECTED)
├── frontend/
│   ├── src/
│   │   ├── pages/          # operator-center/, coordinator-center/, super-admin/ routes
│   │   ├── components/     # Reusable React components
│   │   │   ├── common/     # Button, Input, Modal, Badge, Card, Dropdown, etc.
│   │   │   ├── mission/    # MissionConfigForm, InspectionList, TemplatePicker, etc.
│   │   │   ├── map/        # AirportMap + layers/ + overlays/ + cesium/
│   │   │   ├── coordinator/ # coordinator-specific panels and dialogs
│   │   │   ├── drone/      # DroneModelSelector, DroneModelViewer, BulkChangeDroneDialog
│   │   │   ├── admin/      # super-admin UI (InviteUserDialog)
│   │   │   ├── Layout/     # NavBar, MissionTabNav, OperatorLayout, etc.
│   │   │   └── Auth/       # ProtectedRoute
│   │   ├── contexts/       # AuthContext, AirportContext, MissionContext, ThemeContext
│   │   ├── hooks/          # custom React hooks (map drawing, tools, undo/redo, etc.)
│   │   ├── api/            # Axios client + API functions
│   │   ├── i18n/           # i18next config + locale JSON files
│   │   ├── types/          # TypeScript interfaces matching Pydantic schemas
│   │   ├── auth/           # token store and auth utilities
│   │   ├── config/         # static config (drone models, surfaces)
│   │   ├── constants/      # shared constants (palette, mapAnimations, mapTiles, mission, ui, infrastructureDefaults, camera, surface)
│   │   └── utils/          # shared utility helpers
│   └── package.json
├── .github/workflows/      # CI + harnext pipeline workflows
│                           # (harnext-*.yml are agent-driven; ci.yml, gap-agent.yml, claude-assistant.yml are project-specific)
├── scripts/                # CI helper scripts + guard scripts
├── docs/                   # Architecture, conventions, specs
├── harness.config.json     # Risk tier definitions
└── docker-compose.yml      # PostgreSQL 16
```

## Architecture Overview

```
frontend/src/ → Axios client → /api/v1/* → FastAPI routers → services → SQLAlchemy models → PostgreSQL
```

- `backend/app/api/routes/` — HTTP layer only, no business logic
- `backend/app/services/` — all business logic lives here
- `backend/app/models/` — SQLAlchemy ORM models
- `backend/app/schemas/` — Pydantic v2 request/response DTOs
- `backend/app/core/` — config, database, auth, dependencies
- `frontend/src/api/client.ts` — Axios with JWT interceptor, all API calls go through here
- `frontend/src/pages/` — operator-center, coordinator-center, and super-admin routes
- `frontend/src/components/map/layers/` — MapLibre GL layer modules (surfaceLayers, obstacleLayers, safetyZoneLayers, aglLayers, waypointLayers, mapImages)
- `frontend/src/components/map/overlays/` — map UI overlays (LayerPanel, LegendPanel, PoiInfoPanel, WaypointListPanel, TerrainToggle, MapHelpPanel, etc.)
- `frontend/src/components/map/cesium/` — CesiumJS 3D components (CesiumFlyAlong, CesiumInfrastructure, CesiumTrajectory)

**Dependency rule**: routes → services → models/schemas. Routes never import models directly.

## Critical Paths — Extra Care Required

- `**/trajectory*` — core thesis algorithm
- `**/safety_validator*` — safety-critical validation
- `**/flight_plan*` — mission output generation
- `**/migrations/versions/*` — database schema changes

Changes to these paths:
- Require additional test coverage beyond the baseline
- Must be reviewed by a human (not just the review agent)
- Should include browser evidence if they affect UI
- Are classified as **Tier 3 (high risk)** per `harness.config.json`

## Testing

- **Backend**: pytest + httpx for async API tests, real Postgres via docker service container in CI
- **Frontend**: Vitest + React Testing Library
- **Test location**: `backend/tests/test_{module}.py`, frontend co-located `{Component}.test.tsx`
- **Fixtures**: shared in `conftest.py`, test data in `tests/data/` modules
- **T3 paths** (trajectory, safety_validator, flight_plan, migrations) require thorough test coverage

## Security Constraints

- Never commit secrets, API keys, or `.env` files
- Never disable Ruff rules, ESLint rules, or TypeScript strict mode
- Validate all external input at system boundaries (Pydantic handles this)
- Use parameterized queries — SQLAlchemy ORM only, never raw SQL strings
- JWT auth via `python-jose` — never expose tokens in logs
- Follow least privilege in all configurations

## Dependency Management

- **Backend**: `requirements.txt` with pinned versions — **protected file, only humans modify**
- **Frontend**: `npm install <pkg>` — always commit `package-lock.json`
- Do not upgrade major versions without explicit instruction

## Harnext Automation

This repo uses [harnext](https://www.harnext.dev) for automated issue lifecycle. Humans steer, agents execute. Configuration lives in `~/.harnext/projects/<hash>/github.json`; pipeline workflows are under `.github/workflows/harnext-*.yml`.

### Issue Lifecycle

1. **Create issue** on GitHub using the feature template (`.github/ISSUE_TEMPLATE/feature.md`).
2. **Gate** — add label `harnext:start` to opt the issue into the pipeline. Without it, the tagger ignores the issue.
3. **Tagger** — `harnext-tagger.yml` applies `harnext:triage` to gated issues, dispatches the triage workflow.
4. **Triage** — `harnext-triage.yml` posts one comment classifying severity, scope, risk tier, and ready-to-plan state.
5. **Plan** — `harnext-plan.yml` posts a structured plan (Summary, Files to change, Approach, Risks, Test plan).
6. **Implement** — `harnext-implement.yml` creates branch `issue/<num>-<slug>`, writes code, runs quality gates, opens a draft PR.
7. **Gap (loop)** — `harnext-gap.yml` compares the linked issue's acceptance criteria against the PR diff and posts a verdict. On `GAPS_NEEDS_FIX`, `harnext-gap-bridge.yml` auto-addresses missing criteria and re-dispatches gap (up to 3 iterations before parking on `harnext:needs-judgment`). On `CLEAN` / `GAPS_ACCEPTED`, advances to review. PRs with no `Closes #N` / `Fixes #N` skip the loop and advance to review directly.
8. **Review (loop)** — `harnext-review.yml` posts a review verdict. On `request-changes`, `harnext-review-fix.yml` auto-addresses feedback and re-dispatches review (up to 5 iterations before parking on `harnext:needs-judgment`).
9. **Verify** — `harnext-verify.yml` runs lint/test/typecheck/build on the PR branch and (when frontend paths change) the bundled `browser-verify` skill on the self-hosted runner. Posts a single in-place comment with results.
10. **Doc-gardening** — `harnext-doc-gardening.yml` reconciles `docs/` and root `*.md` after merge.
11. **Human merge** — review the PR, squash merge.

### GitHub Labels

State machine labels (created automatically by harnext):
- `harnext:start` — manual gate; you add this to opt an issue in
- `harnext:triage` / `harnext:plan` / `harnext:implement` / `harnext:gap` / `harnext:review` / `harnext:verify` / `harnext:doc-gardening` — current stage
- `harnext:gap-bridge-iter-<n>` — gap-loop iteration counter
- `harnext:review-iter-<n>` — review-loop iteration counter
- `harnext:awaiting-approval` — human approval needed before next stage
- `harnext:needs-judgment` — agent failed or hit iteration cap; human must intervene

### Runner Topology

- **Self-hosted** (your Mac, registered as `harnext-cbbe54556b22`): `harnext-verify.yml` only — needs local browser, Postgres, ffmpeg.
- **GitHub-hosted** (`ubuntu-latest`): every other stage. Authenticates to Claude Code via `CLAUDE_CODE_OAUTH_TOKEN` repo secret.

Manage the runner with `harnext runner status` / `harnext runner logs`. Re-run `harnext setup` to reconfigure.

### Risk Tiers

Defined in `harness.config.json`:

| Tier | Patterns | CI Checks |
|------|----------|-----------|
| T1 (low) | `docs/**`, `*.md` | lint |
| T2 (medium) | `backend/app/**`, `frontend/src/**`, tests | lint, type-check, test, build |
| T3 (high) | `**/trajectory*`, `**/safety_validator*`, `**/flight_plan*`, `**/migrations/versions/*` | all T2 + manual approval |

### Protected Files

Agents must never modify:
- `.github/workflows/**` — pipeline definitions
- `harness.config.json` — risk tier configuration
- `backend/requirements.txt` — Python dependencies
- `frontend/package-lock.json` — npm lockfile

`CLAUDE.md` is editable by agents (e.g., during doc-gardening) when the user explicitly requests it.

## PR Conventions

- **Branch naming**: `<type>/<short-description>` (e.g., `feat/add-auth`, `fix/null-check`)
- **Commit messages**: conventional commit prefixes required (`feat:`, `fix:`, `chore:`, `refactor:`, `docs:`, `test:`, `build:`, `ci:`); messages stay short, lowercase, casual after the prefix (e.g., `feat: airport crud endpoints`, `fix: null check on map marker`)
- All PRs must pass CI checks before merge
- Classify every PR by risk tier (T1/T2/T3) in the PR description
- **Keep the PR body in sync with the code.** If a change diverges from the open PR's description — added correctness fix, expanded scope, behavior change, or a fix folded in from another issue — update the PR body via `gh pr edit <num> --body-file ...` without waiting to be asked. Either extend the in-scope section if the change is a continuation of the PR's root cause, or add an explicit "Folded-in fixes" section naming each unrelated fix, its root cause, and why it rode along. The "one issue per branch" rule still applies — disclosure is the fallback when bundling has already happened.
- **Git identity**: commits must use `Štefan Moravík <stevko.moravik@gmail.com>`

## Specification Documents — READ BEFORE IMPLEMENTING

Before implementing any issue, read the relevant spec files:

- `docs/specs/SPEC.md` — **ALWAYS READ THIS FIRST.** Complete domain model (19 tables with all columns and types), all 9 enum definitions, trajectory generation formulas, mission status state machine, and page-by-page wireframe summaries for all 14 UI pages.
- `docs/specs/WIREFRAME.md` — Full wireframe specification with every field, interaction, and edge case for each page. Read this when implementing any frontend page.
- `docs/conventions.md` — Coding standards, git workflow, quality gates, OPSEC rules.
- `docs/specs/CHAPTER3-SYSTEM-DESIGN.md` — Complete Chapter 3 from thesis.
  The authoritative design reference. Read this for any architectural question.

## DDD-Lite Patterns

Business logic belongs on model methods, not in services. Services handle DB access and HTTP concerns only.

### Aggregate Roots
- **Mission** — owns inspections, controls status transitions via `transition_to()`. Inspection add/remove works from any non-terminal state (regresses to DRAFT), max 10 inspections, auto-regresses to DRAFT on trajectory-affecting changes.
- **Airport** — owns surfaces, obstacles, safety zones via `add_surface()`, `add_obstacle()`, `add_safety_zone()`.

### Value Objects (`backend/app/models/value_objects.py`)
- **Coordinate** — immutable (lat, lon, alt) with range validation, `to_wkt()`
- **Speed** — non-negative float
- **AltitudeRange** — min ≤ max, `contains()` method
- **IcaoCode** — exactly 4 uppercase alpha chars

### Key Entity Methods
- `Mission.transition_to(status)` — enforces state machine
- `Mission.add_inspection()` / `remove_inspection()` — regresses to DRAFT, blocked in terminal states, max 10
- `InspectionConfiguration.resolve_with_defaults(template_config)`
- `AGL.calculate_lha_center_point()` — centroid of LHA positions
- `Inspection.is_speed_compatible_with_frame_rate(drone, speed)`
- `FlightPlan.compile(total_distance, estimated_duration)`

### Rules for New Code
- New business logic → method on the relevant model
- New primitive (speed, altitude, angle) → value object
- New child entity → create through aggregate root method
- Status change → `mission.transition_to()`, never assign directly

## Branching Strategy

- **Always `feat/<short-description>`** — e.g., `feat/db-models`, `feat/airport-api`, `feat/frontend-shell`
- **No milestone branches.** Every branch merges directly into `main` via squash merge.
- **One issue per branch.** Never combine multiple issues into one branch.
- Check GitHub issues/PRs to confirm dependencies are met before starting an issue.

## Agent skills

### Issue tracker

Issues and PRDs live in GitHub Issues for `LivinTribunal/drone-mission-planning-module`. Use the `gh` CLI. See `docs/agents/issue-tracker.md`.

### Domain docs

Single-context repo. Domain glossary is `CONTEXT.md` at the root; deeper specs live in `docs/specs/` (`SPEC.md`, `WIREFRAME.md`, `CHAPTER3-SYSTEM-DESIGN.md`) and architectural notes in `docs/architecture.md`. See `docs/agents/domain.md`.