from integrations.ipfs_datasets.legal_data import load_legal_symbol

DEFAULT_QUERY_TERMS = load_legal_symbol("DEFAULT_QUERY_TERMS", module="email_relevance")
build_complaint_terms = load_legal_symbol("build_complaint_terms", module="email_relevance")
collect_email_relevance_text = load_legal_symbol("collect_email_relevance_text", module="email_relevance")
generate_email_search_plan = load_legal_symbol("generate_email_search_plan", module="email_relevance")
load_keyword_lines = load_legal_symbol("load_keyword_lines", module="email_relevance")
score_email_relevance = load_legal_symbol("score_email_relevance", module="email_relevance")
tokenize_relevance_text = load_legal_symbol("tokenize_relevance_text", module="email_relevance")

__all__ = [
    "DEFAULT_QUERY_TERMS",
    "build_complaint_terms",
    "collect_email_relevance_text",
    "generate_email_search_plan",
    "load_keyword_lines",
    "score_email_relevance",
    "tokenize_relevance_text",
]
