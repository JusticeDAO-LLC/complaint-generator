from integrations.ipfs_datasets.legal_data import load_legal_symbol

build_email_timeline_handoff = load_legal_symbol("build_email_timeline_handoff", module="email_timeline_handoff")
build_email_timeline_handoff_from_file = load_legal_symbol(
    "build_email_timeline_handoff_from_file",
    module="email_timeline_handoff",
)

__all__ = [
    "build_email_timeline_handoff",
    "build_email_timeline_handoff_from_file",
]
