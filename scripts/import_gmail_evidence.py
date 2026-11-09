#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import anyio


from complaint_generator.email_graphrag import (
    build_email_duckdb_artifacts,
    search_email_graphrag_duckdb,
)
from integrations.ipfs_datasets.legal_data import load_legal_symbol

resolve_gmail_credentials = load_legal_symbol("resolve_gmail_credentials", module="email_auth")
import_gmail_evidence = load_legal_symbol("import_gmail_workspace_evidence", module="email_workspace")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Import Gmail messages and attachments into the complaint evidence folder.")
    parser.add_argument("--user-id", required=True, help="Complaint workspace user id.")
    parser.add_argument("--address", action="append", dest="addresses", default=[], help="Target address to match in From/To/Cc headers. Repeat for multiple addresses.")
    parser.add_argument("--collect-all-messages", action="store_true", help="Import the whole mailbox slice instead of requiring address matches.")
    parser.add_argument("--claim-element-id", default="causation", help="Claim element to attach imported emails to.")
    parser.add_argument("--folder", default="INBOX", help="Gmail IMAP folder to scan.")
    parser.add_argument("--scan-folder", action="append", default=[], help="Additional Gmail IMAP folder to scan. Repeat to broaden collection across INBOX, Sent, or All Mail.")
    parser.add_argument("--limit", type=int, default=None, help="Maximum number of recent messages to consider after IMAP search.")
    parser.add_argument("--date-after", default=None, help="Only search messages on/after this date (YYYY-MM-DD).")
    parser.add_argument("--date-before", default=None, help="Only search messages before this date (YYYY-MM-DD).")
    parser.add_argument("--years-back", type=int, default=None, help="Convenience window for broad collection, e.g. --years-back 2 to scan the last two years when --date-after is omitted.")
    parser.add_argument("--complaint-query", default=None, help="Free-text complaint description used to rank/filter likely relevant emails.")
    parser.add_argument("--complaint-keyword", action="append", default=[], help="Repeatable complaint keyword or phrase.")
    parser.add_argument("--complaint-keyword-file", action="append", default=[], help="Path to newline-delimited complaint keywords or phrases.")
    parser.add_argument("--min-relevance-score", type=float, default=0.0, help="Minimum complaint relevance score required to import a message.")
    parser.add_argument("--use-uid-checkpoint", action="store_true", help="Resume Gmail imports by IMAP UID checkpoint instead of rescanning from scratch.")
    parser.add_argument("--checkpoint-name", default=None, help="Optional checkpoint name when managing multiple Gmail import cursors.")
    parser.add_argument("--uid-window-size", type=int, default=None, help="Maximum number of newly discovered UID messages to import in this run.")
    parser.add_argument("--build-duckdb-index", action="store_true", help="Build or update a DuckDB/parquet email corpus from the generated import manifest.")
    parser.add_argument("--duckdb-output-dir", default=None, help="Directory for DuckDB/parquet email index artifacts. Defaults to a duckdb folder next to the manifest.")
    parser.add_argument("--append-duckdb-index", action="store_true", help="Append the import manifest into an existing DuckDB corpus instead of rebuilding it from scratch.")
    parser.add_argument("--bm25-search-query", default=None, help="Optional keyword query to run against the DuckDB BM25 email index after building it.")
    parser.add_argument("--bm25-search-limit", type=int, default=20, help="Maximum number of BM25 search hits to return after building the index.")
    parser.add_argument("--workspace-root", default=".complaint_workspace/sessions", help="Workspace session root.")
    parser.add_argument("--evidence-root", default=None, help="Directory to write imported email artifacts to.")
    parser.add_argument("--gmail-user", default=os.environ.get("GMAIL_USER") or os.environ.get("EMAIL_USER"), help="Gmail address. Defaults to GMAIL_USER or EMAIL_USER.")
    parser.add_argument("--gmail-app-password", default=os.environ.get("GMAIL_APP_PASSWORD") or os.environ.get("EMAIL_PASS"), help="Gmail app password. Defaults to GMAIL_APP_PASSWORD or EMAIL_PASS.")
    parser.add_argument("--use-gmail-oauth", action="store_true", help="Authenticate to Gmail IMAP with OAuth/XOAUTH2 instead of an app password.")
    parser.add_argument("--gmail-oauth-client-secrets", default=os.environ.get("GMAIL_OAUTH_CLIENT_SECRETS"), help="Google OAuth client-secrets JSON path.")
    parser.add_argument("--gmail-oauth-token-cache", default=os.environ.get("GMAIL_OAUTH_TOKEN_CACHE"), help="Optional Gmail OAuth token-cache path.")
    parser.add_argument("--no-gmail-oauth-browser", action="store_true", help="Do not automatically open the browser during the Gmail OAuth loopback flow.")
    parser.add_argument("--prompt-for-credentials", action="store_true", help="Prompt interactively for Gmail credentials. Password input is hidden.")
    parser.add_argument("--use-keyring", action="store_true", help="Load the Gmail app password from the OS keyring when available.")
    parser.add_argument("--save-to-keyring", action="store_true", help="Save the resolved Gmail app password to the OS keyring when available.")
    parser.add_argument(
        "--use-ipfs-secrets-vault",
        action="store_true",
        help="Load the Gmail app password from the ipfs_datasets_py DID-derived secrets vault.",
    )
    parser.add_argument(
        "--save-to-ipfs-secrets-vault",
        action="store_true",
        help="Save the resolved Gmail app password to the ipfs_datasets_py DID-derived secrets vault.",
    )
    parser.add_argument("--json", action="store_true", help="Print the full JSON result.")
    return parser


async def _run(args: argparse.Namespace) -> dict[str, object]:
    payload = await import_gmail_evidence(
        addresses=args.addresses,
        collect_all_messages=bool(args.collect_all_messages),
        user_id=args.user_id,
        claim_element_id=args.claim_element_id,
        workspace_root=Path(args.workspace_root),
        evidence_root=Path(args.evidence_root) if args.evidence_root else None,
        folder=args.folder,
        folders=args.scan_folder,
        limit=args.limit,
        date_after=args.date_after,
        date_before=args.date_before,
        years_back=args.years_back,
        complaint_query=args.complaint_query,
        complaint_keywords=args.complaint_keyword,
        complaint_keyword_files=args.complaint_keyword_file,
        min_relevance_score=args.min_relevance_score,
        use_gmail_oauth=args.use_gmail_oauth,
        gmail_oauth_client_secrets=args.gmail_oauth_client_secrets,
        gmail_oauth_token_cache=args.gmail_oauth_token_cache,
        gmail_oauth_open_browser=not bool(args.no_gmail_oauth_browser),
        use_uid_checkpoint=args.use_uid_checkpoint,
        checkpoint_name=args.checkpoint_name,
        uid_window_size=args.uid_window_size,
        gmail_user=args.gmail_user,
        gmail_app_password=args.gmail_app_password,
    )
    if args.build_duckdb_index and payload.get("manifest_path"):
        duckdb_summary = build_email_duckdb_artifacts(
            manifest_path=payload["manifest_path"],
            output_dir=args.duckdb_output_dir,
            append=bool(args.append_duckdb_index),
        )
        payload["duckdb_index"] = duckdb_summary
        if args.bm25_search_query and duckdb_summary.get("duckdb_path"):
            payload["bm25_search"] = search_email_graphrag_duckdb(
                index_path=duckdb_summary["duckdb_path"],
                query=args.bm25_search_query,
                limit=int(args.bm25_search_limit or 20),
                ranking="bm25",
            )
    return payload


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
        print(f"Imported {payload['imported_count']} matching email(s) into {payload['evidence_root']}")
        print(f"Searched messages: {payload['searched_message_count']}")
        if payload.get("collect_all_messages"):
            print("Matched addresses: all mailbox messages")
        else:
            print(f"Matched addresses: {', '.join(payload['matched_addresses'])}")
        if payload.get("date_after") or payload.get("date_before"):
            print(f"Date window: {payload.get('date_after') or '*'} -> {payload.get('date_before') or '*'}")
        if payload.get("complaint_terms"):
            print(f"Complaint terms: {', '.join(payload['complaint_terms'])}")
            print(f"Relevance filtered: {payload.get('relevance_filtered_count', 0)}")
        if payload.get("checkpoint_path"):
            print(f"Checkpoint: {payload['checkpoint_path']}")
        if payload.get("duckdb_index"):
            duckdb_summary = payload["duckdb_index"]
            print(f"DuckDB index: {duckdb_summary.get('duckdb_path') or duckdb_summary.get('status')}")
            if duckdb_summary.get("bm25_terms_parquet_path"):
                print(f"BM25 terms parquet: {duckdb_summary['bm25_terms_parquet_path']}")
        if payload.get("bm25_search"):
            bm25_payload = payload["bm25_search"]
            print(f"BM25 hits: {bm25_payload.get('result_count', 0)} for query={bm25_payload.get('query')!r}")
        for item in payload.get("imported") or []:
            score = float(item.get("relevance_score", 0.0) or 0.0)
            matched_terms = ", ".join(item.get("matched_terms") or [])
            print(f"- {item['subject']} [score={score:.1f}] -> {item['artifact_dir']}")
            if matched_terms:
                print(f"  terms: {matched_terms}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
