# Codebase Bundle: codebase/quality/tests-test_website_cohesion_playwright

Source todo: data/refactor_supervisor/refactor_todo.md
Purpose: group generated codebase findings by source file and AST locality.
Conflict policy: serialize edits to one file; allow independent file bundles to run concurrently.

## REF-306 Review swallowed exception path in tests/test_website_cohesion_playwright.py:407

- Status: completed
- Completion: manual
- Priority: P1
- Track: quality
- Depends on: 
- Outputs: data/refactor_supervisor/discovery, tests/test_website_cohesion_playwright.py
- Validation: python3 -m py_compile tests/test_website_cohesion_playwright.py
- Bundle: codebase/quality/tests-test_website_cohesion_playwright
- Bundle shard: data/refactor_supervisor/objective_bundles/codebase-quality-tests-test_website_cohesion_playwright.todo.md
- Bundle strategy: codebase_file_ast
- Graph parents: codebase/quality
- Graph depth: 1
- Parallel lane: codebase/quality/tests-test_website_cohesion_playwright
- Conflict policy: serialize findings for the same file; allow independent file bundles to run concurrently
- Predicted files: tests/test_website_cohesion_playwright.py
- AST symbols: __init__, _artifact_dir, _assert_surface_layout, _build_document_payload, _build_fixture_app, _capture_screenshot, _create_account_and_open_chat, _create_account_from_root_iframe, _fixtureprofilestore, _fixtureprofilestore.__init__, _fixtureprofilestore._matches_hashed_credentials, _fixtureprofilestore._matches_raw_credentials, _fixtureprofilestore.append_chat_message, _fixtureprofilestore.create_profile, _fixtureprofilestore.load_profile, _launch_fixture_site, _load_static_asset, _load_template, _matches_hashed_credentials, _matches_raw_credentials, _serve_app, _wait_for_surface, _write_export_artifact_metadata, append chat message, append_chat_message, applications complaint workspace, applications complaint workspace api, applications complaint workspace api attach complaint workspace routes, applications complaint workspace complaintworkspaceservice, applications document api, applications document api attach document routes, applications document ui, applications document ui attach document ui routes, applications review api, applications review api attach claim support review routes, applications review ui, applications review ui attach claim support review ui routes, applications review ui attach review health routes, applications.complaint_workspace, applications.complaint_workspace.complaintworkspaceservice, applications.complaint_workspace_api, applications.complaint_workspace_api.attach_complaint_workspace_routes, applications.document_api, applications.document_api.attach_document_routes, applications.document_ui, applications.document_ui.attach_document_ui_routes, applications.review_api, applications.review_api.attach_claim_support_review_routes, applications.review_ui, applications.review_ui.attach_claim_support_review_ui_routes, applications.review_ui.attach_review_health_routes, artifact dir, assert surface layout, build document payload, build fixture app, capture screenshot, chat fallback, chat page, chat socket, chat_fallback, chat_page, chat_socket, contextlib, contextlib contextmanager, contextlib.contextmanager, cookies page, cookies_page, create account and open chat, create account from root iframe, create profile, create_profile, fixtureprofilestore, fixtureprofilestore append chat message, fixtureprofilestore create profile, fixtureprofilestore init, fixtureprofilestore load profile, fixtureprofilestore matches hashed credentials, fixtureprofilestore matches raw credentials, home page, home_page
- AST symbol scope: file
- Goal id: codebase/quality/tests-test_website_cohesion_playwright
- Missing evidence: Review swallowed exception path in tests/test_website_cohesion_playwright.py:407
- Merge key: codebase/quality/tests-test_website_cohesion_playwright
- Merge family: tests/test_website_cohesion_playwright.py
- Merge role: codebase_scan
- Work item count: 1
- Work scope: codebase_file_ast
- Candidate kind: codebase_scan
- Goal registration: dynamic
- Todo vector key: 08605ffbd8d9b23a
- Acceptance: Codebase scan filed this finding from tests/test_website_cohesion_playwright.py:407. Use evidence in /home/barberb/complaint-generator/data/refactor_supervisor/discovery/2026-07-23-ref-306-codebase-scan-08605ffbd8d9.md, fix the bug or improvement, add or update focused validation when appropriate, and keep the supervisor-fed backlog parseable.
