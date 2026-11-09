from integrations.ipfs_datasets.legal_data import load_legal_symbol

run_gmail_duckdb_pipeline = load_legal_symbol("run_gmail_duckdb_pipeline", module="email_pipeline")
search_email_duckdb_corpus = load_legal_symbol("search_email_duckdb_corpus", module="email_pipeline")

__all__ = ["run_gmail_duckdb_pipeline", "search_email_duckdb_corpus"]
