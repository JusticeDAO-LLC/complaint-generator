#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import anyio


from integrations.ipfs_datasets.legal_data import load_legal_symbol

resolve_gmail_credentials = load_legal_symbol("resolve_gmail_credentials", module="email_auth")
run_gmail_duckdb_pipeline = load_legal_symbol(
    "run_gmail_workspace_duckdb_pipeline",
    module="email_workspace",
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run a checkpointed Gmail-to-DuckDB ingestion pipeline across many mailbox windows.")
    parser.add_argument("--user-id", required=True, help="Complaint workspace user id.")
    parser.add_argument("--address", action="append", dest="addresses", default=[], help="Target address to match in From/To/Cc headers. Repeat for multiple addresses.")
    parser.add_argument("--collect-all-messages", action="store_true", help="Import the whole mailbox slice instead of requiring address matches.")
    parser.add_argument("--claim-element-id", default="causation", help="Claim element to attach imported emails to.")
    parser.add_argument("--folder", default="INBOX", help="Primary Gmail IMAP folder to scan.")
    parser.add_argument("--scan-folder", action="append", default=[], help="Additional Gmail IMAP folder to scan. Repeat to broaden collection across INBOX, Sent, or All Mail.")
    parser.add_argument("--years-back", type=int, default=2, help="Broad collection window when --date-after is omitted. Defaults to 2 years.")
    parser.add_argument("--date-after", default=None, help="Only search messages on/after this date (YYYY-MM-DD).")
    parser.add_argument("--date-before", default=None, help="Only search messages before this date (YYYY-MM-DD).")
    parser.add_argument("--complaint-query", default=None, help="Free-text complaint description used to rank/filter likely relevant emails.")
    parser.add_argument("--complaint-keyword", action="append", default=[], help="Repeatable complaint keyword or phrase.")
    parser.add_argument("--min-relevance-score", type=float, default=0.0, help="Minimum complaint relevance score required to import a message.")
    parser.add_argument("--workspace-root", default=".complaint_workspace/sessions", help="Workspace session root.")
    parser.add_argument("--evidence-root", default=None, help="Directory to write imported email artifacts to.")
    parser.add_argument("--gmail-user", default=os.environ.get("GMAIL_USER") or os.environ.get("EMAIL_USER"), help="Gmail address.")
    parser.add_argument("--gmail-app-password", default=os.environ.get("GMAIL_APP_PASSWORD") or os.environ.get("EMAIL_PASS"), help="Gmail app password.")
    parser.add_argument("--use-gmail-oauth", action="store_true", help="Authenticate to Gmail IMAP with OAuth/XOAUTH2 instead of an app password.")
    parser.add_argument("--gmail-oauth-client-secrets", default=os.environ.get("GMAIL_OAUTH_CLIENT_SECRETS"), help="Google OAuth client-secrets JSON path.")
    parser.add_argument("--gmail-oauth-token-cache", default=os.environ.get("GMAIL_OAUTH_TOKEN_CACHE"), help="Optional Gmail OAuth token-cache path.")
    parser.add_argument("--no-gmail-oauth-browser", action="store_true", help="Do not automatically open the browser during the Gmail OAuth flow.")
    parser.add_argument("--prompt-for-credentials", action="store_true", help="Prompt interactively for Gmail credentials. Password input is hidden.")
    parser.add_argument("--use-keyring", action="store_true", help="Load the Gmail app password from the OS keyring when available.")
    parser.add_argument("--save-to-keyring", action="store_true", help="Save the resolved Gmail app password to the OS keyring when available.")
    parser.add_argument("--use-ipfs-secrets-vault", action="store_true", help="Load the Gmail app password from the ipfs_datasets_py DID-derived secrets vault.")
    parser.add_argument("--save-to-ipfs-secrets-vault", action="store_true", help="Save the resolved Gmail app password to the ipfs_datasets_py DID-derived secrets vault.")
    parser.add_argument("--checkpoint-name", default="gmail-duckdb-pipeline", help="Checkpoint name for resumable mailbox collection.")
    parser.add_argument("--uid-window-size", type=int, default=500, help="Maximum number of newly discovered UID messages to import per batch.")
    parser.add_argument("--uid-range-span", type=int, default=50000, help="UID range span to search per IMAP backfill chunk so very large mailboxes do not require one giant UID SEARCH result.")
    parser.add_argument("--max-batches", type=int, default=20, help="Maximum number of checkpointed Gmail batches to ingest in one pipeline run.")
    parser.add_argument("--duckdb-build-every-batches", type=int, default=10, help="How many Gmail import batches to accumulate before refreshing DuckDB/parquet artifacts. Higher values reduce index-write pressure on very large crawls.")
    parser.add_argument("--duckdb-output-dir", default=None, help="Directory for DuckDB/parquet email index artifacts.")
    parser.add_argument("--append-to-existing-corpus", action="store_true", help="Append the first batch into an existing DuckDB corpus instead of rebuilding it.")
    parser.add_argument("--bm25-search-query", default=None, help="Optional keyword query to run against the final DuckDB BM25 email index.")
    parser.add_argument("--bm25-search-limit", type=int, default=20, help="Maximum number of BM25 hits to return.")
    parser.add_argument("--json", action="store_true", help="Print the full JSON result.")
    return parser


def _resolve_credentials(args: argparse.Namespace, parser: argparse.ArgumentParser) -> tuple[str, str]:
    if getattr(args, "use_gmail_oauth", False):
        gmail_user = str(args.gmail_user or "").strip()
        if not gmail_user:
            parser.error("--gmail-user is required when --use-gmail-oauth is enabled.")
        if not getattr(args, "gmail_oauth_client_secrets", None):
            parser.error("--gmail-oauth-client-secrets is required when --use-gmail-oauth is enabled.")
        return gmail_user, ""
    return resolve_gmail_credentials(
        gmail_user=str(args.gmail_user or ""),
        gmail_app_password=str(args.gmail_app_password or ""),
        prompt_for_credentials=bool(args.prompt_for_credentials),
        use_keyring=bool(args.use_keyring),
        save_to_keyring_flag=bool(args.save_to_keyring),
        use_ipfs_secrets_vault=bool(getattr(args, "use_ipfs_secrets_vault", False)),
        save_to_ipfs_secrets_vault_flag=bool(getattr(args, "save_to_ipfs_secrets_vault", False)),
        parser=parser,
    )
async def _run(args: argparse.Namespace) -> dict[str, object]:
    return await run_gmail_duckdb_pipeline(
        user_id=args.user_id,
        addresses=args.addresses,
        collect_all_messages=bool(getattr(args, "collect_all_messages", False)),
        claim_element_id=args.claim_element_id,
        folder=args.folder,
        folders=args.scan_folder,
        years_back=args.years_back,
        date_after=args.date_after,
        date_before=args.date_before,
        complaint_query=args.complaint_query,
        complaint_keywords=args.complaint_keyword,
        min_relevance_score=args.min_relevance_score,
        workspace_root=Path(args.workspace_root),
        evidence_root=Path(args.evidence_root) if args.evidence_root else None,
        gmail_user=args.gmail_user,
        gmail_app_password=args.gmail_app_password,
        use_gmail_oauth=args.use_gmail_oauth,
        gmail_oauth_client_secrets=args.gmail_oauth_client_secrets,
        gmail_oauth_token_cache=args.gmail_oauth_token_cache,
        gmail_oauth_open_browser=not bool(args.no_gmail_oauth_browser),
        checkpoint_name=args.checkpoint_name,
        uid_window_size=args.uid_window_size,
        uid_range_span=args.uid_range_span,
        max_batches=args.max_batches,
        duckdb_build_every_batches=args.duckdb_build_every_batches,
        duckdb_output_dir=args.duckdb_output_dir,
        append_to_existing_corpus=bool(args.append_to_existing_corpus),
        bm25_search_query=args.bm25_search_query,
        bm25_search_limit=args.bm25_search_limit,
    )


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    if not args.collect_all_messages and not list(args.addresses or []):
        parser.error("Provide at least one --address or use --collect-all-messages.")
    args.gmail_user, args.gmail_app_password = _resolve_credentials(args, parser)

    payload = anyio.run(_run, args)
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(f"Pipeline batches: {payload['batch_count']} (stop_reason={payload['stop_reason']})")
        print(f"Imported emails: {payload['total_imported_count']}")
        print(f"Searched messages: {payload['total_searched_message_count']}")
        if payload.get("duckdb_index"):
            print(f"DuckDB index: {payload['duckdb_index'].get('duckdb_path')}")
        if payload.get("bm25_search"):
            print(f"BM25 hits: {payload['bm25_search'].get('result_count', 0)} for query={payload['bm25_search'].get('query')!r}")
        if payload.get("summary_path"):
            print(f"Summary: {payload['summary_path']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
