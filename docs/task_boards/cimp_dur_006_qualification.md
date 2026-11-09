# CIMP-DUR-006 qualification note

This note records the intake-resume contract exercised by
`tests/test_tui_interactive_flow.py` and
`tests/test_private_workspace_end_to_end.py`. It does not mark the task
complete. Completion stays with the validation gate.

The synthetic interview answers one open legal gap per turn, updates the fact
graph and the legal-requirement mapping, and reloads the encrypted snapshot
before the next question. Local private mode does not call a provider.
Cloud mode uses an injected Grok 4.7 transport and a redacted prompt.

Readiness tiers are `hermetic_fake`, `local_node`, and `remote_provider`.
Only `measured-local-node` receipts with behavioral assertions and source
hashes are complete. A nonempty CID or a task-id substring is not completion.
