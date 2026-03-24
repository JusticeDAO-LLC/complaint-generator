#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import anyio

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from complaint_generator.email_credentials import resolve_gmail_credentials
from complaint_generator.email_import import import_gmail_evidence


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Import Gmail messages and attachments into the complaint evidence folder.")
    parser.add_argument("--user-id", required=True, help="Complaint workspace user id.")
    parser.add_argument("--address", action="append", dest="addresses", required=True, help="Target address to match in From/To/Cc headers. Repeat for multiple addresses.")
    parser.add_argument("--claim-element-id", default="causation", help="Claim element to attach imported emails to.")
    parser.add_argument("--folder", default="INBOX", help="Gmail IMAP folder to scan.")
    parser.add_argument("--limit", type=int, default=None, help="Maximum number of recent messages to consider after IMAP search.")
    parser.add_argument("--date-after", default=None, help="Only search messages on/after this date (YYYY-MM-DD).")
    parser.add_argument("--date-before", default=None, help="Only search messages before this date (YYYY-MM-DD).")
    parser.add_argument("--complaint-query", default=None, help="Free-text complaint description used to rank/filter likely relevant emails.")
    parser.add_argument("--complaint-keyword", action="append", default=[], help="Repeatable complaint keyword or phrase.")
    parser.add_argument("--complaint-keyword-file", action="append", default=[], help="Path to newline-delimited complaint keywords or phrases.")
    parser.add_argument("--min-relevance-score", type=float, default=0.0, help="Minimum complaint relevance score required to import a message.")
    parser.add_argument("--workspace-root", default=".complaint_workspace/sessions", help="Workspace session root.")
    parser.add_argument("--evidence-root", default=None, help="Directory to write imported email artifacts to.")
    parser.add_argument("--gmail-user", default=os.environ.get("GMAIL_USER") or os.environ.get("EMAIL_USER"), help="Gmail address. Defaults to GMAIL_USER or EMAIL_USER.")
    parser.add_argument("--gmail-app-password", default=os.environ.get("GMAIL_APP_PASSWORD") or os.environ.get("EMAIL_PASS"), help="Gmail app password. Defaults to GMAIL_APP_PASSWORD or EMAIL_PASS.")
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
    return await import_gmail_evidence(
        addresses=args.addresses,
        user_id=args.user_id,
        claim_element_id=args.claim_element_id,
        workspace_root=Path(args.workspace_root),
        evidence_root=Path(args.evidence_root) if args.evidence_root else None,
        folder=args.folder,
        limit=args.limit,
        date_after=args.date_after,
        date_before=args.date_before,
        complaint_query=args.complaint_query,
        complaint_keywords=args.complaint_keyword,
        complaint_keyword_files=args.complaint_keyword_file,
        min_relevance_score=args.min_relevance_score,
        gmail_user=args.gmail_user,
        gmail_app_password=args.gmail_app_password,
    )


def _resolve_credentials(args: argparse.Namespace, parser: argparse.ArgumentParser) -> tuple[str, str]:
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
    args.gmail_user, args.gmail_app_password = _resolve_credentials(args, parser)

    payload = anyio.run(_run, args)
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(f"Imported {payload['imported_count']} matching email(s) into {payload['evidence_root']}")
        print(f"Searched messages: {payload['searched_message_count']}")
        print(f"Matched addresses: {', '.join(payload['matched_addresses'])}")
        if payload.get("complaint_terms"):
            print(f"Complaint terms: {', '.join(payload['complaint_terms'])}")
            print(f"Relevance filtered: {payload.get('relevance_filtered_count', 0)}")
        for item in payload.get("imported") or []:
            score = float(item.get("relevance_score", 0.0) or 0.0)
            matched_terms = ", ".join(item.get("matched_terms") or [])
            print(f"- {item['subject']} [score={score:.1f}] -> {item['artifact_dir']}")
            if matched_terms:
                print(f"  terms: {matched_terms}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
