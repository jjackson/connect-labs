# Agent Guidelines for CommCare Connect Labs

## Labs Architecture Overview

Labs is a **separate Django deployment** that communicates with production CommCare Connect entirely via OAuth and HTTP APIs. It has no direct database access to production data.

Most production apps have been removed from this codebase. The remaining non-labs apps (`opportunity`, `users`, `organization`, `program`, `commcarehq`) are kept only for their Django models and migrations (needed by foreign key references).

**Key principles:**

- **OAuth session auth** — no Django User model. `LabsUser` is transient (created from session on each request, never saved to DB)
- **All data via API** — `LabsRecordAPIClient` calls `/export/labs_record/` on production for all CRUD operations
- **Proxy models** — `LocalLabsRecord` subclasses provide typed access to JSON data from the API. They cannot be saved locally.
- **Context middleware** — `request.labs_context` provides `opportunity_id`, `program_id`, `organization_id` on every request

**Three middleware layers** (configured in `config/settings/local.py`):

1. `LabsAuthenticationMiddleware` — populates `request.user` as `LabsUser` from session OAuth data
2. `LabsURLWhitelistMiddleware` — redirects non-labs URLs to `connect.dimagi.com`; whitelisted prefixes: `/ai/`, `/audit/`, `/coverage/`, `/tasks/`, `/solicitations/`, `/solicitations_new/`, `/labs/`, `/custom_analysis/`
3. `LabsContextMiddleware` — extracts opportunity/program/organization from URL params and session into `request.labs_context`

**Important:** Use `config.settings.local` for local development, NOT `config.settings.labs_aws`. The `labs_aws` settings are only for the AWS deployment at `labs.connect.dimagi.com`. Local settings already have `IS_LABS_ENVIRONMENT = True`.

## Data Access Patterns

### Pattern A: LabsRecordAPIClient (The Correct Pattern for Labs)

All labs apps use `LabsRecordAPIClient` (`commcare_connect/labs/integrations/connect/api_client.py`) for data operations:

```
View receives request
  → Extracts OAuth token from request.session["labs_oauth"]["access_token"]
  → Extracts context from request.labs_context
  → Creates AppDataAccess(request=request)
    → DataAccess creates LabsRecordAPIClient(access_token, opportunity_id, ...)
      → Client calls GET/POST/PUT/DELETE on /export/labs_record/
    → DataAccess casts responses to proxy models (LocalLabsRecord subclasses)
  → View renders template with proxy model lists (NOT Django QuerySets)
```

Each app wraps the client in a `data_access.py` with domain-specific methods. See `commcare_connect/tasks/data_access.py` for the simplest example.

### Pattern B: Django ORM (Retained for Migrations Only — Do Not Use for Labs)

The `opportunity/`, `organization/`, `program/`, `users/`, and `commcarehq/` apps contain Django ORM models retained only for their migrations and foreign key references. In the labs environment, these tables are empty. **Never query these models expecting production data.** The `opportunity/` app in particular has been gutted to models + migrations + factory stubs only (no views, no business logic).

The only local Django models used by labs are cache tables in `commcare_connect/labs/analysis/backends/sql/models.py` (`RawVisitCache`, `ComputedVisitCache`, `ComputedFLWCache`).

### When to Use Which

- **Need to store/retrieve domain data?** → `LabsRecordAPIClient` via `data_access.py`
- **Need visit/user CSV data for analysis?** → `AnalysisPipeline` (handles caching transparently)
- **Need opportunity/organization metadata?** → HTTP call to `/export/opp_org_program_list/`
- **Need CommCare HQ case data?** → CommCare HQ OAuth + Case API v2 (see `coverage/` app)
- **Need AI integration?** → Add agent in `ai/agents/`, SSE streaming via `AIStreamView`
- **Need async processing?** → Celery task in `{app}/tasks.py`, SSE for progress

## Data Export API Endpoints

Base URL: `settings.CONNECT_PRODUCTION_URL` (production: `https://connect.dimagi.com`)

**Authentication:** OAuth Bearer token with `export` scope

### LabsRecord CRUD API

- `GET /export/labs_record/` — Query records. Params: `experiment`, `type`, `username`, `opportunity_id`, `organization_id`, `program_id`, `labs_record_id`, `public`, `data__<field>=<value>`
- `POST /export/labs_record/` — Create or update record. Body: `{experiment, type, data, username, opportunity_id, organization_id, program_id, labs_record_id, public}`
- `DELETE /export/labs_record/` — Delete record. Params: `id`

### Metadata APIs

- `GET /export/opp_org_program_list/` — Lists opportunities, organizations, programs (JSON)
- `GET /export/opportunity/<opp_id>/` — Full opportunity details including `learn_app`, `deliver_app`

### CSV Stream APIs (Opportunity-scoped)

- `/export/opportunity/<opp_id>/user_data/`
- `/export/opportunity/<opp_id>/user_visits/`
- `/export/opportunity/<opp_id>/completed_works/`
- `/export/opportunity/<opp_id>/payment/`
- `/export/opportunity/<opp_id>/invoice/`
- `/export/opportunity/<opp_id>/assessment/`
- `/export/opportunity/<opp_id>/completed_module/`

## How Each Labs App Works

### `audit/` — Quality Assurance Review

> See also: [`commcare_connect/audit/README.md`](../commcare_connect/audit/README.md) for data model details and testing guidance.

Structured audits of FLW visits with AI-powered reviews.

- **DataAccess:** `AuditDataAccess` in `audit/data_access.py`
- **Proxy models:** `AuditSessionRecord` (experiment=`"audit"`, type=`"AuditSession"`)
- **Key views:** Audit list (`/audit/`), creation wizard (`/audit/create/`), bulk assessment (`/audit/<pk>/bulk/`)
- **Async:** Celery task for audit creation with SSE progress streaming
- **AI review:** `audit/ai_review.py` runs validation agents on individual visits
- **Uses:** `AnalysisPipeline` for visit data filtering

### `tasks/` — Task Management

> See also: [`commcare_connect/tasks/README.md`](../commcare_connect/tasks/README.md) for data model details and testing guidance.

Task tracking for FLW follow-ups with timeline, comments, and AI assistant.

- **DataAccess:** `TaskDataAccess` in `tasks/data_access.py` (simplest example of the pattern)
- **Proxy models:** `TaskRecord` (experiment=`"tasks"`, type=`"Task"`)
- **Key views:** Task list (`/tasks/`), create/edit (`/tasks/new/`, `/tasks/<id>/edit/`)
- **OCS integration:** Tasks can trigger Open Chat Studio bots and save transcripts
- **Cross-app:** Tasks can reference audit sessions via `audit_session_id` in task data

### `workflow/` — Configurable Workflow Engine

> See also: [`commcare_connect/workflow/README.md`](../commcare_connect/workflow/README.md) for data model details and testing guidance.

Data-driven workflows with custom React UIs and pipeline integration.

- **DataAccess:** `WorkflowDataAccess`, `PipelineDataAccess` (both extend `BaseDataAccess`) in `workflow/data_access.py`
- **Proxy models:** `WorkflowDefinitionRecord`, `WorkflowRenderCodeRecord`, `WorkflowRunRecord`, `WorkflowChatHistoryRecord`, `PipelineDefinitionRecord` (experiment=`"workflow"` / `"pipeline"`)
- **Key views:** Workflow list (`/workflow/`), definition view, run view
- **Templates:** Predefined workflow templates in `workflow/templates/` (audit_with_ai_review, performance_review, ocs_outreach)
- **Render code:** React components stored as LabsRecords, rendered dynamically in workflow runner
- **Cross-app:** Can create audit sessions and tasks from workflow actions

### `ai/` — AI Agent Integration

> See also: [`commcare_connect/ai/README.md`](../commcare_connect/ai/README.md) for data model details and testing guidance.

SSE streaming endpoints for AI-assisted editing using pydantic-ai agents.

- **No data_access.py** — agents call into other apps' DataAccess classes via tool functions
- **Agents:** `workflow_agent.py`, `pipeline_agent.py`, `solicitation_agent.py`, `coding_agent.py` in `ai/agents/`
- **Key view:** `AIStreamView` at `/ai/stream/` (POST → SSE streaming)
- **Tool calls:** Agents modify workflow definitions, render code, pipeline schemas via WorkflowDataAccess/PipelineDataAccess
- **Models:** Claude Sonnet/Opus or GPT via pydantic-ai

### `solicitations/` — RFP Management

> See also: [`commcare_connect/solicitations/README.md`](../commcare_connect/solicitations/README.md) for data model details and testing guidance.

Solicitations (requests for proposals), responses, and reviews.

- **DataAccess:** `SolicitationDataAccess` in `solicitations/data_access.py`
- **Proxy models:** `SolicitationRecord`, `ResponseRecord`, `ReviewRecord`, `DeliveryTypeDescriptionRecord`, `OppOrgEnrichmentRecord` (experiment=`"solicitations"`)
- **Scoping:** Uses `program_id` and `organization_id` (NOT `opportunity_id`)
- **Key views:** Solicitation list, create, respond, review
- **Standalone:** No cross-app dependencies (except AI agent integration)

### `coverage/` — Delivery Unit Mapping

Interactive map visualization of FLW coverage.

- **Different pattern:** Uses CommCare HQ OAuth (separate from Connect OAuth) + Case API v2
- **Models:** Dataclasses (`LocalUserVisit`, `DeliveryUnit`), NOT LabsRecord proxies
- **DataAccess:** `CoverageDataAccess` fetches from CommCare HQ, not Connect
- **Key views:** Map view (`/coverage/map/`), SSE stream for GeoJSON loading
- **Standalone:** No cross-app dependencies

### `labs/` — Core Infrastructure

Foundation layer used by all other apps.

- **Key files:**
  - `models.py` — `LabsUser`, `LocalLabsRecord` base classes
  - `middleware.py` — Authentication, URL whitelist, context middleware
  - `context.py` — Context extraction and session management
  - `view_mixins.py` — `AsyncLoadingViewMixin`, `AsyncDataViewMixin`
  - `integrations/connect/api_client.py` — `LabsRecordAPIClient`
  - `integrations/connect/oauth.py` — `introspect_token()`, `fetch_user_organization_data()`
  - `integrations/connect/oauth_views.py` — OAuth flow (login, callback, logout)
  - `analysis/` — Analysis pipeline (SQL backend with PostgreSQL cache tables)
  - `explorer/` — LabsRecord data explorer UI
  - `admin_boundaries/` — Geographic boundary data (PostGIS)

## Cross-App Connections

```
Workflow ──imports──→ AuditDataAccess (creates audits from workflow actions)
Workflow ──imports──→ TaskDataAccess (creates tasks from workflow actions)
AI ──────imports──→ WorkflowDataAccess (agents modify workflow definitions)
AI ──────imports──→ SolicitationDataAccess (solicitation agent)
Audit ←──references── Tasks (tasks store audit_session_id)
All apps ──depend──→ labs/ (API client, models, middleware)
Coverage ──────────→ CommCare HQ (separate OAuth, no Connect dependency)
```

## Key Files Quick Reference

| File                                                       | Purpose                                            |
| ---------------------------------------------------------- | -------------------------------------------------- |
| `commcare_connect/labs/integrations/connect/api_client.py` | Core `LabsRecordAPIClient`                         |
| `commcare_connect/labs/models.py`                          | `LabsUser`, `LocalLabsRecord` base classes         |
| `commcare_connect/labs/middleware.py`                      | Auth, URL whitelist, context middleware            |
| `commcare_connect/labs/context.py`                         | Context extraction and session management          |
| `commcare_connect/labs/view_mixins.py`                     | Base view mixins for labs views                    |
| `commcare_connect/labs/LABS_GUIDE.md`                      | Detailed patterns: OAuth, API client, proxy models |
| `commcare_connect/{app}/data_access.py`                    | Per-app data access layer                          |
| `commcare_connect/{app}/models.py`                         | Per-app proxy model definitions                    |
| `config/settings/local.py`                                 | Labs-enabled local development settings            |

## Common Mistakes to Avoid

1. **Using Django ORM models** (`Opportunity`, `User`, `Organization`) expecting production data — these tables are empty in labs
2. **Using `config.settings.labs_aws` locally** — use `config.settings.local` instead. The `labs_aws` settings are only for the AWS deployment.
3. **Calling `.save()` on `LabsUser` or `LocalLabsRecord`** — raises `NotImplementedError`. Use `LabsRecordAPIClient` for persistence.
4. **Forgetting the URL whitelist** — new app URL prefixes must be added to `WHITELISTED_PREFIXES` in `commcare_connect/labs/middleware.py`
5. **Using `user_id` with the production API** — production uses `username` as the primary identifier, not integer IDs
6. **Not handling API errors** — `LabsRecordAPIClient` raises `LabsAPIError` on HTTP failures; handle timeouts gracefully
7. **Modifying retained non-labs apps** — don't modify `opportunity/`, `organization/`, `program/`, `users/`, or `commcarehq/`. They exist only for migrations and FK references.
8. **Hardcoding opportunity IDs** — use `request.labs_context` from middleware instead
