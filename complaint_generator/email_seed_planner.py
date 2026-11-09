from integrations.ipfs_datasets.legal_data import load_legal_symbol

build_email_seed_plan = load_legal_symbol("build_email_seed_plan", module="email_seed_planner")

__all__ = ["build_email_seed_plan"]
