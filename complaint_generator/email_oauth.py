from integrations.ipfs_datasets.legal_data import load_legal_symbol

DEFAULT_TOKEN_ROOT = load_legal_symbol("DEFAULT_TOKEN_ROOT", module="email_auth")
GMAIL_IMAP_SCOPE = load_legal_symbol("GMAIL_IMAP_SCOPE", module="email_auth")
build_xoauth2_bytes = load_legal_symbol("build_xoauth2_bytes", module="email_auth")
default_token_cache_path = load_legal_symbol("default_token_cache_path", module="email_auth")
load_cached_token = load_legal_symbol("load_cached_token", module="email_auth")
resolve_gmail_oauth_access_token = load_legal_symbol("resolve_gmail_oauth_access_token", module="email_auth")
run_local_server_oauth_flow = load_legal_symbol("run_local_server_oauth_flow", module="email_auth")
save_cached_token = load_legal_symbol("save_cached_token", module="email_auth")
token_is_usable = load_legal_symbol("token_is_usable", module="email_auth")

__all__ = [
    "DEFAULT_TOKEN_ROOT",
    "GMAIL_IMAP_SCOPE",
    "build_xoauth2_bytes",
    "default_token_cache_path",
    "load_cached_token",
    "resolve_gmail_oauth_access_token",
    "run_local_server_oauth_flow",
    "save_cached_token",
    "token_is_usable",
]
