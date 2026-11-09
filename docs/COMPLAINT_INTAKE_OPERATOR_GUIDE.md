# Complaint intake operator guide

This guide is the operator surface for the terminal interview, local key recovery, and the complaint-improvement supervisor. It does not claim that a complete legal interview, a sufficient complaint, or a live provider campaign has been qualified.

Use `python` from `PATH`. The package requires Python 3.12 or newer (`python_requires` in `setup.py`). Do not substitute a user-home interpreter, an editor-profile default, or a path that is not installed. Replace the uppercase placeholders below with your own values. They are not home directories.

## Fresh clone

From a new checkout, initialize only the pinned intake submodules and install declared dependencies:

```bash
git submodule update --init external/ipfs_accelerate_py external/ipfs_datasets_py external/ipfs_kit_py
python -m pip install -e .
python -m pip install 'cryptography>=41.0.0' 'typer>=0.12.0'
```

`cryptography` and `typer` are explicit optional installs for this workflow. `cryptography` wraps local keys. `typer` is the preferred CLI parser; if it is absent, `applications/complaint_cli.py` uses a small built-in parser for the same flags. The checkout’s Git submodule entries select the exact revisions installed by that command. The taskboard specification records its original baseline under `upstream_pins`; reviewed integrations can advance a submodule entry later. Do not substitute a different checkout of those projects.

Print the machine-readable catalog:

```bash
python -m complaint_generator.cli intake-operator-examples
```

## Primary terminal command

There is one primary TUI command:

```bash
python -m complaint_generator.cli chat --user-id USER_ID
```

The terminal uses backend id `llm-router-grok-4.7` and model `grok-4.7` from `config.llm_router.json`. A live generation sends the prompt, including complaint text placed in that prompt, to the remote Grok provider. Starting the command does not by itself send a case.

A new case defaults to local processing. To authorize remote Grok processing for this case, use the explicit option below after reading the remote-processing limits. To revoke it for future calls, select local. Omitting the option preserves the saved choice; it never creates consent.

```bash
python -m complaint_generator.cli chat --user-id USER_ID --privacy-mode grok
python -m complaint_generator.cli chat --user-id USER_ID --privacy-mode local
```

Create the wrapped key store with `keys-init` before the first chat. Chat then prompts for the passphrase in the same process, unlocks that store, and ensures the case data key. A missing store stops with exit 2 and does not invent a key. The prompt is not an answer and is not a process argument.

Session state defaults to `.complaint_workspace/sessions` under the repository checkout. To choose another directory, set `COMPLAINT_WORKSPACE_SESSION_DIR` to a real directory you own (mode `0700`). A relative value is resolved from the current working directory. The service rejects a symlink. Example:

```bash
COMPLAINT_WORKSPACE_SESSION_DIR=SESSION_DIR python -m complaint_generator.cli chat --user-id USER_ID
```

### Controls inside the primary command

These lines are commands to the interview. They are not saved as answers.

| Input | Effect |
| --- | --- |
| `/help` | Show controls and exit codes. |
| `/privacy grok` or `/privacy local` | Authorize remote processing or revoke it for future calls; keep the current question pending. |
| `/status` | Show the pending question, objective, graph revision, stop reason, and unknown or skipped answers. |
| `/why` | Explain why the pending question was asked. The question stays pending. |
| `/skip` | Record a skip. A skip does not satisfy a legal requirement. |
| `/edit replacement text` | Replace the last recorded answer. |
| `/pause` | Save a recoverable pause and keep the pending question. |
| `/resume` | Continue after `/pause` in this process. |
| `/quit` | Save stop reason `user_quit` and leave the pending question in place (exit 0). |

EOF exits 1 and Ctrl-C exits 130. Both keep the pending question when the save succeeds. To resume in a new process, run the same primary command with the same `USER_ID`, then use `/resume` if the restored session is still paused.

A tested synthetic transcript, in order, is `/help`, `/status`, `/why`, `/skip`, `/edit synthetic replacement`, `/pause`, `/resume`, `/quit`.

### Grok 4.7 without sending a complaint

This checks the pinned route and does not dispatch a live canary unless you add `--confirm-live`:

```bash
python -m complaint_generator.cli router-live-canary --config-path config.llm_router.json --backend-id llm-router-grok-4.7
```

`--confirm-live` is an explicit opt-in for a synthetic public-token canary. It is not consent to upload an existing case, and this guide's tested example does not pass it.

## Encryption unlock, export, and recovery

Passphrases are read with a non-echo prompt inside the process. `--passphrase`, `--password`, and key-byte flags are rejected. Printed output is a receipt and does not include key bytes. Unlocking local storage is not consent for remote processing.

```bash
python -m complaint_generator.cli keys-status --store-dir STORE_DIR
python -m complaint_generator.cli keys-init --store-dir STORE_DIR --protection passphrase
python -m complaint_generator.cli keys-unlock --store-dir STORE_DIR
python -m complaint_generator.cli keys-recover-export --store-dir STORE_DIR --tenant-id TENANT_ID --case-id CASE_ID --destination RECOVERY_FILE
python -m complaint_generator.cli keys-recover-import --store-dir STORE_DIR --tenant-id TENANT_ID --case-id CASE_ID --source RECOVERY_FILE
python -m complaint_generator.cli workspace-export --store-dir STORE_DIR --tenant-id TENANT_ID --case-id CASE_ID --principal-id PRINCIPAL_ID --repository REPOSITORY_DIR --export-dir EXPORT_DIR --recovery-destination RECOVERY_FILE
```

For chat, `STORE_DIR` is the selected session directory’s `private-keys` child. A standalone `keys-unlock` unwraps keys only in that command process; chat prompts and unlocks its own process. Existing private data with a missing case key requires recovery and is never replaced with a newly minted key.

`keys-init` creates a wrapped store. `keys-unlock` opens an existing store and does not invent a key. `keys-recover-export` writes a deliberate recovery file. It is not an automatic backup. `keys-recover-import` refuses to overwrite a locked store. `workspace-export` writes a ciphertext archive and a separate recovery file. Keep `RECOVERY_FILE` apart from `EXPORT_DIR`.

`keys-lock`, `workspace-import`, wrapping rotation, data-key rotation, and retained-key revocation exist on the same CLI. Revocation requires a verified migrated backup. None of these commands erase provider-side copies.

## Supervisor start, status, and stop

Prepare and inspect before a launch. `status` and `stop` take the same explicit roots as `start`. Resume is another `start` using the same `--state-dir` after a verified stop. There is no separate resume verb.

```bash
python scripts/run_complaint_improvement_supervisor.py start --repo-root REPO_ROOT --spec SPEC_PATH --state-dir STATE_DIR --watch --monitor-seconds 21600
python scripts/run_complaint_improvement_supervisor.py status --repo-root REPO_ROOT --spec SPEC_PATH --state-dir STATE_DIR
python scripts/run_complaint_improvement_supervisor.py stop --repo-root REPO_ROOT --spec SPEC_PATH --state-dir STATE_DIR
```

`SPEC_PATH` for this program is `docs/task_boards/complaint_intake_improvement_spec.json` under `REPO_ROOT`. `STATE_DIR` is an explicit campaign directory you choose. `doctor` must report ready before `start` launches a worker. A not-ready result does not start Grok. `stop` signals only a process whose recorded birth identity matches that state directory. A PID alone is not evidence that a task is running. The campaign model is `grok-4.7` with provider fallback disabled. The implementation budget documented for a Grok task is 64 model turns and a 900-second hard deadline.

The start example attaches a bounded monitor for at most six hours. It verifies the recorded launch owner and can close an exactly owned orphan worker if that launcher exits. Monitoring never supplies user answers or resets task attempts. Each launch has one recorded monitor window.

## Operational limits

**Factual assertions versus applicable legal requirements.** A factual assertion is something the interview recorded from the operator or from a supplied narrative: who did what, when, and where. An applicable legal requirement is an element or dependency derived from a cited authority for a claim. Recording a fact does not mean a requirement is met. `/skip` and answers such as "unknown" leave the requirement unresolved. A missing or uncertain authority stays uncertain.

**Saturation versus legal sufficiency.** Saturation means no further answerable question remains under the current policy. A turn limit, pause, or quit is a separate recoverable stop and does not establish saturation. Legal sufficiency is a separate judgment about whether the recorded facts and authorities would support a filing. A structurally consistent graph, a finished question list, or a generated draft is not legal sufficiency and is not legal advice.

**Remote model processing versus encryption at rest.** Encryption at rest wraps local session and key bytes so a locked store is not plaintext on disk. Remote model processing is different: a live `grok-4.7` call sends the generation prompt to the provider. Encryption of the local store does not cover bytes already sent, and it does not make a remote call local. Unlocking the store does not authorize that call.

**Local deletion versus remote erasure.** Deleting a local session directory, export, or recovery file removes those local copies only. It does not delete prompts, logs, or backups retained by a remote model provider or by any other machine that already received them. This repository has no command that performs remote erasure.

## Known bounds

The terminal controls above are implemented in `applications/complaint_cli.py`. They are not a representation that every graph follow-up, authority lookup, or live campaign succeeds. If a provider, submodule, or keyring is unavailable, the command should return a typed failure or a not-ready receipt. Do not treat that receipt as a completed interview or as a completed supervisor task.
