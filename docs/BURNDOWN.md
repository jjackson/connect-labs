# Codebase Improvement Burndown

## Critical — Runtime Crashes

- [x] **Fix `update_record` wrong positional args** — `tasks/data_access.py:279,294,310,334,359` pass `task.data` (dict) as `experiment` (string). Every call to `add_event`, `add_comment`, `add_ai_session`, `update_status`, `assign_task` will TypeError at runtime. *(Fixed: switched to keyword args. 10 unit tests added.)*
- [x] **Fix broken imports in `custom_analysis/mbw/views.py:20-28`** — imports `gps_analysis` and `pipeline_config` from paths that don't exist. Entire mbw sub-app fails at import. *(Fixed: corrected import paths to `workflow.templates.mbw_monitoring`.)*
- [x] **Fix broken import in `audit/management/commands/test_search_readers.py:7`** — imports `ConnectAPIFacade` from non-existent `audit/management/extractors/`. *(Fixed: deleted dead code.)*
- [x] **Fix broken management command `cleanup_duplicate_assessments.py`** — references `audit.models.Assessment` which doesn't exist (it's in `opportunity/models.py`). *(Fixed: deleted dead code.)*
- [x] **Fix missing webpack bundle reference** — `custom_pipelines/run.html` references `pipeline-runner-bundle.js` but no such webpack entry exists. *(Fixed: updated to `pipeline-editor-bundle.js`.)*

## High — Security

- [x] **Fix SSRF in `solicitations/views.py:87-121`** — `generate_criteria_api` fetches user-supplied URLs with no allowlist. Add URL validation to block internal/private IPs. *(Fixed: added `validate_url_safe()` with DNS resolution check. 14 unit tests added.)*
- [x] **Fix open redirect in Connect OAuth callback** — `oauth_views.py:44,250` doesn't validate `next` param with `url_has_allowed_host_and_scheme`. The CommCare OAuth callback already does this correctly. *(Fixed: added validation. 2 unit tests added.)*
- [x] **Set `SESSION_COOKIE_SECURE = True`** — `config/settings/labs_aws.py:26-27` explicitly sets both session and CSRF cookies insecure on the AWS deployment. *(Fixed: set both to `True`.)*
- [x] **Add `@login_required` to `clear_context`** — `labs/views.py:13-38` accepts POST without auth check, inconsistent with adjacent `refresh_org_data`. *(Fixed: added decorator. 2 unit tests added.)*
- [ ] **Decide on `_is_dimagi_user` bypass** — 5 copies across `workflow/views.py:35`, `labs/views.py:166`, `audit_of_audits/views.py:54`, `utils/analytics.py:113`, `web/context_processors.py:14` all return `True` unconditionally. Either re-enable email check or remove the dead code.

## High — Data Layer (Integration Testing Required)

- [ ] **Optimize `get_record_by_id`** — `api_client.py:160-183` fetches ALL records then scans linearly. Add server-side `id` filtering.
- [ ] **Add pagination to `get_records`** — `api_client.py:144-154` makes a single GET with no next-page handling.
- [ ] **Implement OAuth token refresh** — `refresh_token` stored at login (`oauth_views.py:210`) but never used. Users must re-login on expiry.
- [ ] **Fix race condition in `get_or_create_run`** — `workflow/data_access.py:648-682` non-atomic check-then-create allows duplicate runs.

## Medium — Error Handling

- [x] **Add logging to silent exception catches** — `audit/data_access.py:981` (`except Exception: pass`), `audit/data_access.py:1306` (`return False` with no logging). *(Fixed: added `logger.debug` and `logger.warning`.)*
- [ ] **Wrap bare `raise_for_status()` calls** — `coverage/data_access.py:100`, `audit/data_access.py:1071,1082,1110`, `commcare/api_client.py:191,324`, `funder_dashboard/data_access.py:132`. (Integration testing required)
- [ ] **Sanitize error responses** — Dozens of views return `str(e)` in 500 JSON responses across `tasks/views.py`, `workflow/views.py`, `audit/views.py`, `ai/views.py`. (Integration testing required)
- [x] **Reduce API payload log level** — `api_client.py:235` logs full payload at INFO including potential PII. Change to DEBUG. *(Fixed.)*

## Medium — Frontend

- [x] **Fix Alpine.js double-load** — `workflow/list.html:1013-1014` and `pipeline_list.html:450-451` load Alpine from CDN but it's already in the webpack vendors bundle. *(Fixed: removed CDN script tags.)*
- [x] **Fix duplicate `class=` attribute** — `account/base.html:44,47` has two `class=` attrs; second is silently ignored. *(Fixed: merged into single class attr.)*
- [ ] **Remove CDN Tailwind from production templates** — `coverage/debug.html:7` and `coverage/token_status.html:7` bypass the build pipeline.
- [x] **Remove debug `console.log` statements** — `static/js/dashboard.js:1`. *(Fixed: removed module-load console.log. Template console.logs deferred — they're interspersed in large inline scripts that need broader refactoring.)*
- [ ] **Add missing `alt` attributes** — `timeline.html:154,210`, `bulk_assessment.html:300`, `user_visit_details.html:168,270`.
- [ ] **Replace hardcoded URLs with `{% url %}` tags** — `labs/login.html:53-73`, `explorer/index.html:165`, `explorer/visit_view.html:71`, `audit_of_audits/report.html:11,204`.

## Medium — Code Quality

- [x] **Fix double decorator** — `workflow/views.py:867-870` applies `@login_required` and `@require_POST` twice. *(Fixed: removed duplicates.)*
- [x] **Fix `CELERY_TASK_ALWAYS_EAGER` string bug** — `workflow/tests/e2e/conftest.py:33` sets `"False"` (truthy string) instead of `"0"`. *(Fixed.)*
- [ ] **Extract shared `BaseDataAccess`** — `audit`, `tasks`, `solicitations` all re-implement the same 30-line init that `workflow/data_access.py:BaseDataAccess` already abstracts. (Integration testing required)
- [ ] **Remove deprecated code** — `stream_analysis_pipeline`/`run_analysis_pipeline` still called in `labs/analysis/views.py:79`, `chc_nutrition/views.py:94,279`. (Integration testing required — callers need migration.)
- [x] **Clean up deprecated `AuditTemplateRecord`** — `audit/models.py:12` marked deprecated with zero callers. *(Fixed: removed.)*
- [x] **Remove deprecated aliases in `workflow/data_access.py`** — `list_instances`, `get_instance`, `get_or_create_instance`, `update_instance_state` had zero callers. *(Fixed: removed.)*
- [ ] **Replace tempfile CSV pattern with `io.BytesIO`** — `tasks/data_access.py:449-493,551-584` and `workflow/data_access.py:1146-1174`. (Integration testing required)

## Low — Cleanup

- [ ] **Fix unofficial Font Awesome Pro CDN** — `account/base.html:12` loads from unlicensed GitHub CDN.
- [ ] **Add SRI hashes to CDN scripts** — Leaflet, Chart.js, Marked.js, Alpine, Prism all loaded without integrity checks.
- [ ] **Remove unused static files** — `commcare-logo-color.svg`, `datetime-utils.js` appear unreferenced.
- [ ] **Remove unused npm devDependencies** — `gulp-concat`, `pixrem`, `node-sass-tilde-importer`.
- [x] **Increase HSTS to meaningful duration** — `labs_aws.py:28` sets only 60 seconds. *(Fixed: increased to 3600.)*
- [x] **Fix file handle leak in e2e conftest** — `workflow/tests/e2e/conftest.py:72,114` open files without `with`. *(Fixed: added try/finally cleanup.)*
- [ ] **Extract large inline `<script>` blocks** — `audit_creation_wizard.html` (~650 lines), `bulk_assessment.html` (~500 lines), `timeline.html` (~600 lines).
