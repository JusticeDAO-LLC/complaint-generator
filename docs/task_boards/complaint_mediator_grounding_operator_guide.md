# Grounded complaint operations

This guide is the operator surface for the mediator-grounding campaign. It describes the public terminal interview, consent, legal and evidence actions, and the difference between encrypted local storage and remote durability. It is not completion authority, provider authority, campaign-state authority, or publication authority.

Validation of this document does not complete `CIMP-MGND-44`. That task stays self-pending until a Root post-Native-callback audit, outside this task, accepts evidence from the separate new plan. A passing focused test is not that callback and does not manufacture completion.

The new plan is `docs/task_boards/complaint_mediator_grounding_spec.json`, `docs/task_boards/complaint_mediator_grounding_formal_work_plan.json`, and `docs/task_boards/complaint_mediator_grounding_task_board.md`. Its task ids are `CIMP-MGND-*`, with goals and subgoals declared on that plan. The earlier 58-task intake receipts remain historical scoped evidence. Do not remap them onto new task ids. This guide is not a fresh qualification of that old release and it is not a rerun of the old 83-module release closure.

## Canonical chat command

There is one primary interview command:

```bash
python -m complaint_generator.cli chat --user-id USER_ID
```

Replace `USER_ID` with a synthetic or operator-chosen case id. The command is implemented by `applications/complaint_cli.py` through `python -m complaint_generator.cli`. Starting it does not send the case to a remote model, does not prove a legal element, and does not close a supervisor task.

Session bytes default under the checkout's `.complaint_workspace/sessions`. Set `COMPLAINT_WORKSPACE_SESSION_DIR` to a directory you own when the case must live elsewhere. The service rejects a symlink. Create the wrapped key store before the first chat. A missing store or missing case key stops without minting a replacement key.

## Consent modes

Local processing is the default. Omitting a privacy flag preserves a saved choice and never creates consent. Encryption unlock is not consent. Two explicit modes exist:

```bash
python -m complaint_generator.cli chat --user-id USER_ID --privacy-mode local
python -m complaint_generator.cli chat --user-id USER_ID --privacy-mode grok
```

Inside the interview, `/privacy local` revokes remote processing for later calls and `/privacy grok` authorizes remote processing for this case. Both leave the current question pending. Remote mode can send the generation prompt, including complaint text placed in that prompt, to the configured Grok route. Local mode does not. A synthetic test transport is not live provider qualification.

## Legal and evidence actions

`/research` runs bounded legal-source acquisition for the current gap. It is not stored as an answer and it does not establish the complaint. Search hits, model text, and a parsed intermediate representation stay candidates until a source is admitted with its span and version.

`/skip` records the pending question as skipped. A skip does not satisfy a legal requirement. Answers such as "unknown" leave the requirement unresolved.

Jurisdiction and effective date are explicit operator context. They select which admitted source may be considered. They are not themselves proof that a rule applies.

## Question explanation

`/why` explains why the pending question matters. The question stays pending. The command is not stored as an answer, does not change the graph or session revision, and does not dispatch a provider. `awaiting_user` means the interview is waiting for a person. It is not a stalled worker and it does not extend a development-task deadline.

## Correction

`/edit replacement text` corrects the last recorded answer. The replacement supersedes that answer and keeps history. It does not erase the prior statement, does not rewrite an admitted legal rule, and does not by itself satisfy a proof obligation. A stale concurrent edit is rejected and is not saved.

## Pause and resume

`/pause` saves a recoverable pause and keeps the pending question. `/resume` continues that paused interview in this process. To continue in a new process, run the same canonical chat command with the same `USER_ID`, then use `/resume` if the restored session is still paused.

EOF exits 1 and Ctrl-C exits 130. `/quit` saves stop reason `user_quit` and exits 0. Each of those stops keeps the pending question when the save succeeds. A turn limit, pause, or quit is not interview saturation. Saturation only means no further answerable question remains under the current policy. Saturation is not legal sufficiency.

## Source and proof limits

A factual assertion records what the operator or an admitted narrative supplied, with its source span. A legal requirement records an admitted authority passage, jurisdiction, effective date, and version. Support and proof outcomes stay separate from those identities.

Missing authority, a contradicted span, an unavailable source, or an unavailable prover remains that typed gap. Do not treat a candidate, a skipped question, a structurally consistent graph, or a generated draft as proof. This guide does not give legal advice.

## Encrypted storage and durability

These states are distinct. A later state is not implied by an earlier one:

| State | What it means |
| --- | --- |
| `local_encrypted_commit` | Case bytes were wrapped for the local store. The disk copy is ciphertext, not a replica. |
| `ciphertext_readback` | That ciphertext was read back and authenticated. Readback is still local. |
| `queued_replication` | A replica job was queued. A queue entry is not a stored replica. |
| `pinning` | A pin was requested or recorded. A pin is not proof the bytes were read back elsewhere. |
| `verified_replica` | An authenticated remote readback succeeded for that replica. |

Local deletion removes only the local copies you delete. It is not remote erasure. A locked store does not cover prompts already sent to a provider. Unavailable storage stays unavailable. It does not mint an empty case and it does not qualify remote durability.

## What this campaign may audit

The completion contract in `docs/task_boards/complaint_mediator_grounding_completion_contract.json` defines two audits:

- Pre-completion. Focused validation may pass while `CIMP-MGND-44` remains self-pending. This task never manufactures its own completion.
- Post-Native-callback. Root, outside this task, requires the new plan's actual accepted task id, canonical task CID, goal id, and subgoal id, plus current-source public acceptance. Missing evidence is `unavailable`. Work that cannot proceed is `blocked`. Neither result is success.

Old 58-task receipts stay historical scoped evidence. They do not move to `CIMP-MGND-*` ids and they do not freshly qualify the old release.
