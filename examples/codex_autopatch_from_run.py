import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
import py_compile
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Tuple

# Allow running via: python examples/codex_autopatch_from_run.py
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from backends import LLMRouterBackend


def _load_json(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _load_config(path: str) -> Dict[str, Any]:
    return _load_json(path)


def _get_llm_router_backend_config(config: Dict[str, Any], backend_id: str | None) -> Dict[str, Any]:
    backend_ids = config.get("MEDIATOR", {}).get("backends", [])
    if not backend_id:
        backend_id = backend_ids[0] if backend_ids else None
    if not backend_id:
        raise ValueError("No backend id specified and config.MEDIATOR.backends is empty")

    backends = config.get("BACKENDS", [])
    backend_config = next((b for b in backends if b.get("id") == backend_id), None)
    if not backend_config:
        raise ValueError(f"Backend id not found in config.BACKENDS: {backend_id}")
    if backend_config.get("type") != "llm_router":
        raise ValueError(f"Backend {backend_id} must have type 'llm_router'")

    backend_kwargs = dict(backend_config)
    backend_kwargs.pop("type", None)
    return backend_kwargs


def _parse_iso_dt(s: str) -> Optional[datetime]:
    if not isinstance(s, str):
        return None
    s = s.strip()
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        # Provider timestamps are untrusted and may be malformed. Keep those
        # inputs non-fatal, but allow unexpected parser defects to surface.
        return None


def _parse_codex_human_reset_at(msg: str) -> Optional[datetime]:
    """Parse Codex CLI human reset time like: 'try again at Feb 11th, 2026 11:46 PM.'

    Codex strings typically omit timezone. We treat them as UTC for consistency.
    """
    if not isinstance(msg, str) or not msg:
        return None
    m = re.search(r"try again at\s+([^\.\n]+)", msg, flags=re.IGNORECASE)
    if not m:
        return None
    raw = m.group(1).strip()
    if not raw:
        return None

    cleaned = re.sub(r"(\d+)(st|nd|rd|th)", r"\1", raw, flags=re.IGNORECASE)
    for fmt in ("%b %d, %Y %I:%M %p", "%B %d, %Y %I:%M %p"):
        try:
            dt = datetime.strptime(cleaned, fmt)
            return dt.replace(tzinfo=timezone.utc)
        except ValueError:
            # Provider reset messages are untrusted and may not match either
            # supported format. Unexpected parser failures must remain visible.
            continue
    return None


def _extract_rate_limit_reset_info(msg: str) -> Tuple[Optional[int], Optional[datetime], Optional[str]]:
    """Extract (resets_in_seconds, reset_at_dt, source) from a Codex error message.

    - source is one of: 'resets_in_seconds', 'reset_at', 'try_again_at', 'quota_exceeded', or None.
    """
    if not isinstance(msg, str):
        return None, None, None

    low = msg.lower()
    # Quota/billing exhaustion is not a backoff-able usage limit.
    quota_markers = (
        "insufficient_quota",
        "exceeded your current quota",
        "quota has been exceeded",
        "check your plan and billing",
        "billing",
        "hard limit",
        "billing limit",
        "add a payment method",
        "your account is not active",
    )
    if any(m in low for m in quota_markers) and ("usage limit" not in low) and ("usage_limit" not in low):
        return None, None, "quota_exceeded"

    reset_s: Optional[int] = None
    source: Optional[str] = None

    m = re.search(r"resets_in_seconds\"\s*:\s*(\d+)", msg)
    if not m:
        m = re.search(r"resets_in_seconds\s*[:=]\s*(\d+)", msg)
    if m:
        try:
            reset_s = int(m.group(1))
            source = "resets_in_seconds"
        except Exception:
            reset_s = None

    reset_at: Optional[datetime] = None
    m_at = re.search(r"reset_at\"\s*:\s*\"([^\"]+)\"", msg)
    if not m_at:
        m_at = re.search(r"reset_at\s*[:=]\s*([^\s\)]+)", msg)
    if m_at:
        reset_at = _parse_iso_dt(m_at.group(1))
        if reset_at is not None:
            source = "reset_at"

    if reset_at is None:
        reset_at = _parse_codex_human_reset_at(msg)
        if reset_at is not None:
            source = "try_again_at"

    if reset_at is not None and (reset_s is None or reset_s <= 0):
        remaining = int((reset_at - datetime.now(timezone.utc)).total_seconds())
        if remaining > 0:
            reset_s = remaining

    return reset_s, reset_at, source


def _debug_extract_reset_info_from_message(msg: str) -> Dict[str, Any]:
    """Debug helper: extract reset timing from a Codex rate-limit error message."""
    reset_s, reset_at, source = _extract_rate_limit_reset_info(msg)
    return {
        "reset_at_iso": (reset_at.isoformat() if isinstance(reset_at, datetime) else None),
        "resets_in_seconds": reset_s,
        "source": source,
    }


def _extract_first_error_message_from_exec_jsonl(path: str) -> Optional[str]:
    """Best-effort: extract the first error.message from a Codex exec JSONL."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    obj = json.loads(line)
                except Exception:
                    continue
                if isinstance(obj, dict) and obj.get("type") == "error" and isinstance(obj.get("message"), str):
                    msg = str(obj.get("message") or "").strip()
                    return msg or None
    except (OSError, UnicodeError):
        # The exec artifact is optional and may disappear, become unreadable,
        # or contain invalid text while a run is being inspected. Treat those
        # input failures as a missing fallback, but do not hide unexpected
        # failures in the extraction logic.
        return None
    return None


def _extract_rate_limit_reset_info_with_exec_fallback(
    *,
    msg: str,
    exec_jsonl_path: Optional[str] = None,
) -> Tuple[Optional[int], Optional[datetime], Optional[str]]:
    """Extract reset timing from the exception message, with optional exec-JSONL fallback.

    Codex provider sometimes includes the definitive reset timestamp only in the
    codex_exec_*.jsonl error message.
    """
    reset_s, reset_at, source = _extract_rate_limit_reset_info(msg)
    if source == "quota_exceeded":
        return reset_s, reset_at, source
    if reset_at is not None or (isinstance(reset_s, int) and reset_s > 0):
        return reset_s, reset_at, source

    if isinstance(exec_jsonl_path, str) and exec_jsonl_path.strip():
        provider_msg = _extract_first_error_message_from_exec_jsonl(exec_jsonl_path.strip())
        if provider_msg:
            s2, at2, src2 = _extract_rate_limit_reset_info(provider_msg)
            if src2 == "quota_exceeded":
                return s2, at2, src2
            if at2 is not None or (isinstance(s2, int) and s2 > 0):
                return s2, at2, src2

    return reset_s, reset_at, source


def _truncate_for_log(s: Optional[str], max_len: int = 400) -> Optional[str]:
    if not isinstance(s, str):
        return None
    s = s.strip().replace("\r", " ").replace("\n", " ")
    if not s:
        return None
    if len(s) <= int(max_len):
        return s
    if int(max_len) <= 3:
        return s[: int(max_len)]
    return s[: int(max_len) - 3] + "..."


def _pick_reset_at_raw_from_rate_limit_artifact(data: Dict[str, Any]) -> Optional[str]:
    if not isinstance(data, dict):
        return None
    provider_reset_at_raw = data.get("provider_reset_at")
    if isinstance(provider_reset_at_raw, str) and provider_reset_at_raw.strip():
        return provider_reset_at_raw.strip()
    reset_at_raw = data.get("reset_at")
    if isinstance(reset_at_raw, str) and reset_at_raw.strip():
        return reset_at_raw.strip()
    return None


def _write_rate_limit_artifact_payload(path: str, payload: Dict[str, Any]) -> None:
    """Persist rate-limit metadata, surfacing failures to the caller.

    Callers publish this path to users and orchestration processes, so silently
    continuing after a failed write would falsely claim that resumable metadata
    exists.
    """
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)


def _find_session_jsons(run_dir: str) -> List[str]:
    out: List[str] = []
    if not os.path.isdir(run_dir):
        return out
    for name in os.listdir(run_dir):
        if not name.startswith("session_"):
            continue
        p = os.path.join(run_dir, name, "session.json")
        if os.path.isfile(p):
            out.append(p)
    return sorted(out)


def _session_brief(doc: Dict[str, Any]) -> Dict[str, Any]:
    critic = doc.get("critic_score") or {}
    art = doc.get("artifacts") or {}

    def _count_kg(path: Any) -> Dict[str, Any]:
        if not isinstance(path, str) or not path or not os.path.isfile(path):
            return {"path": path, "total_entities": None, "total_relationships": None}
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            entities = data.get("entities") if isinstance(data, dict) else None
            rels = data.get("relationships") if isinstance(data, dict) else None
            return {
                "path": path,
                "total_entities": (len(entities) if isinstance(entities, dict) else None),
                "total_relationships": (len(rels) if isinstance(rels, dict) else None),
            }
        except Exception:
            return {"path": path, "total_entities": None, "total_relationships": None}

    def _count_dg(path: Any) -> Dict[str, Any]:
        if not isinstance(path, str) or not path or not os.path.isfile(path):
            return {"path": path, "total_nodes": None, "total_dependencies": None, "satisfaction_rate": None}
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            nodes = data.get("nodes") if isinstance(data, dict) else None
            deps = data.get("dependencies") if isinstance(data, dict) else None
            satisfied = 0
            if isinstance(nodes, dict):
                for n in nodes.values():
                    if isinstance(n, dict) and n.get("satisfied") is True:
                        satisfied += 1
            rate = (satisfied / len(nodes)) if isinstance(nodes, dict) and nodes else (0.0 if isinstance(nodes, dict) else None)
            return {
                "path": path,
                "total_nodes": (len(nodes) if isinstance(nodes, dict) else None),
                "total_dependencies": (len(deps) if isinstance(deps, dict) else None),
                "satisfaction_rate": rate,
            }
        except Exception:
            return {"path": path, "total_nodes": None, "total_dependencies": None, "satisfaction_rate": None}

    kg_path = art.get("knowledge_graph_json")
    dg_path = art.get("dependency_graph_json")
    return {
        "session_id": doc.get("session_id"),
        "success": doc.get("success"),
        "num_turns": doc.get("num_turns"),
        "overall_score": critic.get("overall_score"),
        "feedback": critic.get("feedback"),
        "artifacts": {
            "knowledge_graph": _count_kg(kg_path),
            "dependency_graph": _count_dg(dg_path),
            "evidence_duckdb_exists": art.get("evidence_duckdb_exists"),
            "legal_authorities_duckdb_exists": art.get("legal_authorities_duckdb_exists"),
        },
    }


def _pick_worst_sessions(session_docs: List[Dict[str, Any]], k: int) -> List[Dict[str, Any]]:
    def key(d: Dict[str, Any]) -> float:
        try:
            critic = d.get("critic_score") or {}
            v = critic.get("overall_score")
            return float(v) if v is not None else 1e9
        except Exception:
            return 1e9

    sorted_docs = sorted(session_docs, key=key)
    return sorted_docs[: max(0, int(k))]


def _optimizer_count(optimizer: Dict[str, Any], key: str) -> int:
    """Return a persisted optimizer count, defaulting malformed values to zero."""
    value = optimizer.get(key)
    if value is None:
        return 0
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError):
        return 0


def _build_prompt(
    *,
    run_dir: str,
    cycle_summary_path: str,
    cycle_summary: Dict[str, Any],
    sgd_report_path: str,
    sgd_report: Dict[str, Any],
    worst_sessions: List[Dict[str, Any]],
    worst_session_json_paths: List[str],
    context_mode: str = "rich",
) -> str:
    optimizer = cycle_summary.get("optimizer_report") or {}
    priority = optimizer.get("priority_improvements") or []
    recs = (sgd_report.get("recommendations") or [])[:10]

    session_snippet_path = os.path.join(PROJECT_ROOT, "adversarial_harness", "session.py")
    abs_session_path = os.path.abspath(session_snippet_path)
    abs_kg_path = os.path.abspath(os.path.join(PROJECT_ROOT, "complaint_phases", "knowledge_graph.py"))
    abs_dg_path = os.path.abspath(os.path.join(PROJECT_ROOT, "complaint_phases", "dependency_graph.py"))
    abs_denoiser_path = os.path.abspath(os.path.join(PROJECT_ROOT, "complaint_phases", "denoiser.py"))
    abs_mediator_path = os.path.abspath(os.path.join(PROJECT_ROOT, "mediator", "mediator.py"))

    optimizer_graph_diag = {
        k: optimizer.get(k)
        for k in [
            "kg_sessions_with_data",
            "dg_sessions_with_data",
            "kg_sessions_empty",
            "dg_sessions_empty",
            "kg_avg_total_entities",
            "kg_avg_total_relationships",
            "kg_avg_gaps",
            "dg_avg_total_nodes",
            "dg_avg_total_dependencies",
            "dg_avg_satisfaction_rate",
        ]
        if k in optimizer
    }
    sgd_graphs = sgd_report.get("graphs") if isinstance(sgd_report, dict) else None
    graphs_health = cycle_summary.get("graphs_health")
    graphs_dynamics_health = cycle_summary.get("graphs_dynamics_health")

    focus: List[str] = []
    kg_avg_entities_raw = optimizer.get("kg_avg_total_entities")
    try:
        kg_avg_entities = float(kg_avg_entities_raw) if kg_avg_entities_raw is not None else None
    except (TypeError, ValueError):
        # Optimizer reports may contain missing or non-numeric metric values.
        # Ignore only those expected conversion failures; unexpected defects
        # must remain visible instead of being swallowed by best-effort focus
        # generation below.
        kg_avg_entities = None

    kg_d_entities_raw = optimizer.get("kg_avg_entities_delta_per_iter")
    try:
        kg_d_entities = float(kg_d_entities_raw) if kg_d_entities_raw is not None else None
    except (TypeError, ValueError):
        # Optimizer reports are persisted inputs and may contain non-numeric
        # metric values. Ignore only expected conversion failures here so an
        # unexpected runtime defect cannot be swallowed by the best-effort
        # focus generation below.
        kg_d_entities = None

    kg_d_rels_raw = optimizer.get("kg_avg_relationships_delta_per_iter")
    try:
        kg_d_rels = float(kg_d_rels_raw) if kg_d_rels_raw is not None else None
    except (TypeError, ValueError):
        # Persisted optimizer metrics can be malformed. Expected conversion
        # errors simply omit this diagnostic; unexpected failures must remain
        # visible rather than being swallowed by the focus-generation fallback.
        kg_d_rels = None

    dg_avg_nodes_raw = optimizer.get("dg_avg_total_nodes")
    try:
        dg_avg_nodes = float(dg_avg_nodes_raw) if dg_avg_nodes_raw is not None else None
    except (TypeError, ValueError):
        # Persisted optimizer metrics can be malformed. Treat only expected
        # numeric conversion failures as missing data; unexpected failures
        # must remain observable instead of being hidden by prompt generation.
        dg_avg_nodes = None

    kg_with = _optimizer_count(optimizer, "kg_sessions_with_data")
    dg_with = _optimizer_count(optimizer, "dg_sessions_with_data")
    kg_empty = _optimizer_count(optimizer, "kg_sessions_empty")
    dg_empty = _optimizer_count(optimizer, "dg_sessions_empty")
    kg_d_gaps_raw = optimizer.get("kg_avg_gaps_delta_per_iter")
    try:
        kg_d_gaps = float(kg_d_gaps_raw) if kg_d_gaps_raw is not None else None
    except (TypeError, ValueError, OverflowError):
        # Persisted optimizer metrics can be malformed or outside the range
        # accepted by float(). Omit only those expected input failures so
        # unexpected conversion defects remain visible for diagnosis.
        kg_d_gaps = None
    kg_not_reducing = _optimizer_count(optimizer, "kg_sessions_gaps_not_reducing")

    if kg_with > 0 and kg_empty == kg_with:
        focus.append("Knowledge graphs are empty across analyzed sessions")
    elif kg_avg_entities is not None and kg_avg_entities < 2.0:
        focus.append("Knowledge graphs are very small on average")

    # Dynamics: if gaps aren't shrinking or graphs aren't growing, steer to denoiser answer processing.
    if kg_not_reducing > 0:
        focus.append("Knowledge graph gaps are not reducing across iterations")
    if kg_d_gaps is not None and kg_d_gaps >= 0.0:
        focus.append("Knowledge graph gaps are flat/increasing per iteration")
    if kg_d_entities is not None and kg_d_entities < 0.1:
        focus.append("Knowledge graph is not growing per iteration")
    if kg_d_rels is not None and kg_d_rels < 0.05:
        focus.append("Knowledge graph relationships are not growing per iteration")

    if dg_with > 0 and dg_empty == dg_with:
        focus.append("Dependency graphs are empty across analyzed sessions")
    elif dg_avg_nodes is not None and dg_avg_nodes < 2.0:
        focus.append("Dependency graphs are very small on average")

    suspected_files: List[str] = []
    if any("Knowledge graph" in f for f in focus):
        suspected_files.append(abs_kg_path)
        # When gaps aren't shrinking, the best starting point is answer processing.
        if any("gaps" in f.lower() for f in focus) or any("not growing per iteration" in f for f in focus):
            suspected_files.append(abs_denoiser_path)
    if any("Dependency graph" in f for f in focus):
        suspected_files.append(abs_dg_path)
    if focus:
        suspected_files.append(abs_mediator_path)
    else:
        suspected_files.append(abs_session_path)

    context_mode = (context_mode or "rich").strip().lower()
    if context_mode not in {"rich", "lean"}:
        context_mode = "rich"

    worst_briefs = [_session_brief(d) for d in worst_sessions]

    # We include a helpful snippet (question selection logic) but allow patches across
    # the key files that affect question selection and graph population.
    # In lean mode, omit the snippet to avoid resending ~80 lines of code every step.
    snippet = "(omitted in lean mode)"
    if context_mode == "rich":
        try:
            with open(session_snippet_path, "r", encoding="utf-8") as f:
                lines = f.read().splitlines()
            # Grab the question selection section if possible.
            snippet = "\n".join(lines[90:170])
        except Exception:
            snippet = "(unable to load adversarial_harness/session.py snippet)"

    # To reduce prompt tokens, lean mode points Codex at the persisted JSON artifacts
    # and relies on tool calls (cat/grep) to pull only what it needs.
    if context_mode == "lean":
        return f"""You are Codex CLI.

Tool-mode is ENABLED. You may take multiple turns by requesting a tool call, then using its result to decide on a better patch.

On each turn, output exactly ONE of the following:

1) A single JSON object requesting a tool:
{{
  "type": "tool",
    "tool": "ls" | "cat" | "grep" | "patch",
  "args": {{ ... }}
}}

2) A single JSON object returning the final patch:
{{
    "type": "final",
    "patch": "*** Begin Patch\\n...\\n*** End Patch"
}}

3) (Backward compatible) Output a raw apply_patch patch starting with '*** Begin Patch' and ending with '*** End Patch'.

Important patch-application behavior (read carefully):
- If you output MULTIPLE separate apply_patch blocks in one response, the system will validate each block and then attempt to COMBINE all valid blocks into ONE transactional patch.
- The combined patch is applied ONLY if the combined patch also validates (dry-run apply).
- If blocks validate individually but do NOT combine cleanly, your output is treated as invalid and you must return ONE coherent patch block that includes ALL intended changes.
- Therefore: Prefer returning a SINGLE apply_patch block that covers all changes across all files.

Tool specs (paths must be within the repository root; keep outputs small):
- ls:    args={{"path": "."}}  -> list directory entries
- cat:   args={{"path": "path/to/file.py", "start_line": 1, "end_line": 200}} -> read a line range
- grep:  args={{"pattern": "string or regex", "path": "path/or/dir", "max_matches": 50}} -> search text
- patch: args={{"patch": "*** Begin Patch\\n...\\n*** End Patch"}} -> validate patch formatting + file targets (does NOT apply)

Before returning a final patch (type=final or raw patch), you SHOULD call the patch tool on your candidate patch and fix any errors it reports.

When PATCH_VALIDATION reports an error, it may include file_context/file_excerpt lines. Use those EXACT lines for your hunk context (copy them contiguously), then apply minimal edits.

You must output a REAL patch in apply_patch format, not a template.

apply_patch dialect (STRICT):
- Your final output must contain EXACTLY ONE apply_patch block.
- The very first non-empty line must be exactly: *** Begin Patch
- The very last non-empty line must be exactly:  *** End Patch
- Between them, you MUST include one-or-more file sections that begin with:
        *** Update File: /absolute/path/to/file.py
- Only Update File is supported (do NOT use Add File / Delete File).
- Paths in *** Update File MUST be absolute paths under the repository root.
- Hunks consist of raw file lines copied verbatim from the current file.
    - Prefix deletions with '-' and additions with '+'.
    - Unchanged context lines have NO prefix (do not start them with a single leading space).
    - Do NOT include unified-diff headers like 'diff --git', '---', '+++', 'index', or '@@ -1,2 +1,2'.
- You MAY include lines that start with '@@' ONLY as hunk separators/scope hints; never use '@@' or '...' as placeholders.

Minimal valid example (illustrative only — you must use real current file lines):
*** Begin Patch
*** Update File: /home/barberb/complaint-generator/some_module.py
@@
-old line copied exactly from file
+new line
 unchanged context line copied exactly from file
*** End Patch

Patch formatting rules (important):
- Do NOT output unified-diff style prefixes (no leading ' ' marker on unchanged lines).
- Do NOT use '...' or '@@' as an ellipsis to omit lines inside a hunk.
- Each hunk must contain exact, contiguous lines copied from the current file content.
- Use '@@' only to start a new hunk (or include a scope hint like '@@ class Foo'), never as a placeholder.

If you return option (2) as JSON (type=final):
- The value of "patch" MUST be a valid JSON string.
- Represent newlines as '\\n' inside that JSON string (do not include literal newlines inside the JSON string).

Scope:
- You MAY change any *.py file under the repository root: {os.path.abspath(PROJECT_ROOT)}
- Use ONLY absolute paths in *** Update File lines.
- Suggested starting points (not exclusive):
    - {abs_session_path}
    - {abs_kg_path}
    - {abs_dg_path}
    - {abs_denoiser_path}
    - {abs_mediator_path}

Context files (use tools to read only what you need):
- cycle_summary.json: {os.path.abspath(cycle_summary_path)}
- sgd_report.json:    {os.path.abspath(sgd_report_path)}
- worst sessions (session.json):\n{json.dumps([os.path.abspath(p) for p in worst_session_json_paths], ensure_ascii=False, indent=2)}

Primary focus (computed from diagnostics):
{json.dumps(focus, ensure_ascii=False)}

Suspected files to start with:
{json.dumps(suspected_files, ensure_ascii=False, indent=2)}

Goal:
- Address the highest-impact items in Priority improvements and SGD recommendations.
- If graphs are empty/tiny: improve knowledge graph and dependency graph population/reduction so downstream denoising has structure.
- If question repetition is flagged: reduce repeated identical mediator questions in adversarial sessions (improve efficiency + info extraction).
- Keep changes minimal and localized.
- Do NOT add dependencies.
- Ensure existing tests keep passing.

Quality constraints (important):
- Do NOT invent legal elements/requirements or factual content. Prefer extracting/deriving structure from the session text, existing artifacts, and deterministic heuristics.
- Avoid creating dense graphs by linking every claim to every entity (no cartesian-product relationships). Add relationships only when a clear textual or structural signal exists.
- Prefer small, high-signal changes over broad refactors.

Implementation constraints:
- Only modify Python files.
- Prefer changing adversarial harness behavior (e.g., question selection logic) rather than core mediator logic.

Strong suggestion for step 1:
- Use cat/grep to inspect the relevant portions of the suspected files and the context JSONs, then propose a patch.

Output requirements:
- Output MUST start with the exact line: *** Begin Patch
- Use absolute file paths (within the repository root) in each *** Update File line.
- Patch MUST include a non-trivial change (not placeholders like /abs/path/to/file.py or 'old'/'new').
- Output MUST end with the exact line: *** End Patch
- No markdown fences. No extra commentary.

Now begin."""

    return f"""You are Codex CLI.

Tool-mode is ENABLED. You may take multiple turns by requesting a tool call, then using its result to decide on a better patch.

On each turn, output exactly ONE of the following:

1) A single JSON object requesting a tool:
{{
  "type": "tool",
    "tool": "ls" | "cat" | "grep" | "patch",
  "args": {{ ... }}
}}

2) A single JSON object returning the final patch:
{{
    "type": "final",
    "patch": "*** Begin Patch\\n...\\n*** End Patch"
}}

3) (Backward compatible) Output a raw apply_patch patch starting with '*** Begin Patch' and ending with '*** End Patch'.

Important patch-application behavior (read carefully):
- If you output MULTIPLE separate apply_patch blocks in one response, the system will validate each block and then attempt to COMBINE all valid blocks into ONE transactional patch.
- The combined patch is applied ONLY if the combined patch also validates (dry-run apply).
- If blocks validate individually but do NOT combine cleanly, your output is treated as invalid and you must return ONE coherent patch block that includes ALL intended changes.
- Therefore: Prefer returning a SINGLE apply_patch block that covers all changes across all files.

Tool specs (paths must be within the repository root; keep outputs small):
- ls:    args={{"path": "."}}  -> list directory entries
- cat:   args={{"path": "path/to/file.py", "start_line": 1, "end_line": 200}} -> read a line range
- grep:  args={{"pattern": "string or regex", "path": "path/or/dir", "max_matches": 50}} -> search text
- patch: args={{"patch": "*** Begin Patch\\n...\\n*** End Patch"}} -> validate patch formatting + file targets (does NOT apply)

Before returning a final patch (type=final or raw patch), you SHOULD call the patch tool on your candidate patch and fix any errors it reports.

When PATCH_VALIDATION reports an error, it may include file_context/file_excerpt lines. Use those EXACT lines for your hunk context (copy them contiguously), then apply minimal edits.

You must output a REAL patch in apply_patch format, not a template.

apply_patch dialect (STRICT):
- Your final output must contain EXACTLY ONE apply_patch block.
- The very first non-empty line must be exactly: *** Begin Patch
- The very last non-empty line must be exactly:  *** End Patch
- Between them, you MUST include one-or-more file sections that begin with:
        *** Update File: /absolute/path/to/file.py
- Only Update File is supported (do NOT use Add File / Delete File).
- Paths in *** Update File MUST be absolute paths under the repository root.
- Hunks consist of raw file lines copied verbatim from the current file.
    - Prefix deletions with '-' and additions with '+'.
    - Unchanged context lines have NO prefix (do not start them with a single leading space).
    - Do NOT include unified-diff headers like 'diff --git', '---', '+++', 'index', or '@@ -1,2 +1,2'.
- You MAY include lines that start with '@@' ONLY as hunk separators/scope hints; never use '@@' or '...' as placeholders.

Minimal valid example (illustrative only — you must use real current file lines):
*** Begin Patch
*** Update File: /home/barberb/complaint-generator/some_module.py
@@
-old line copied exactly from file
+new line
 unchanged context line copied exactly from file
*** End Patch

Patch formatting rules (important):
- Do NOT output unified-diff style prefixes (no leading ' ' marker on unchanged lines).
- Do NOT use '...' or '@@' as an ellipsis to omit lines inside a hunk.
- Each hunk must contain exact, contiguous lines copied from the current file content.
- Use '@@' only to start a new hunk (or include a scope hint like '@@ class Foo'), never as a placeholder.

If you return option (2) as JSON (type=final):
- The value of "patch" MUST be a valid JSON string.
- Represent newlines as '\\n' inside that JSON string (do not include literal newlines inside the JSON string).

Scope:
- You MAY change any *.py file under the repository root: {os.path.abspath(PROJECT_ROOT)}
- Use ONLY absolute paths in *** Update File lines.
- Suggested starting points (not exclusive):
    - {abs_session_path}
    - {abs_kg_path}
    - {abs_dg_path}
    - {abs_denoiser_path}
    - {abs_mediator_path}

Context:
- We just ran an adversarial harness batch from: {os.path.abspath(run_dir)}
- Priority improvements from optimizer: {json.dumps(priority, ensure_ascii=False)}
- Optimizer graph diagnostics: {json.dumps(optimizer_graph_diag, ensure_ascii=False)}
- Graphs health (static): {json.dumps(graphs_health, ensure_ascii=False)}
- Graphs health (dynamics): {json.dumps(graphs_dynamics_health, ensure_ascii=False)}
- SGD recommendations: {json.dumps(recs, ensure_ascii=False)}
- SGD graph summary: {json.dumps(sgd_graphs, ensure_ascii=False)}
- Worst session briefs (from this run):\n{json.dumps(worst_briefs, ensure_ascii=False, indent=2)}

Primary focus (computed from diagnostics):
{json.dumps(focus, ensure_ascii=False)}

Suspected files to start with:
{json.dumps(suspected_files, ensure_ascii=False, indent=2)}

Goal:
- Address the highest-impact items in Priority improvements and SGD recommendations.
- If graphs are empty/tiny: improve knowledge graph and dependency graph population/reduction so downstream denoising has structure.
- If question repetition is flagged: reduce repeated identical mediator questions in adversarial sessions (improve efficiency + info extraction).
- Keep changes minimal and localized.
- Do NOT add dependencies.
- Ensure existing tests keep passing.

Quality constraints (important):
- Do NOT invent legal elements/requirements or factual content. Prefer extracting/deriving structure from the session text, existing artifacts, and deterministic heuristics.
- Avoid creating dense graphs by linking every claim to every entity (no cartesian-product relationships). Add relationships only when a clear textual or structural signal exists.
- Prefer small, high-signal changes over broad refactors.

Implementation constraints:
- Only modify Python files.
- Prefer changing adversarial harness behavior (e.g., question selection logic) rather than core mediator logic.

Output requirements:
- Output MUST start with the exact line: *** Begin Patch
- Use absolute file paths (within the repository root) in each *** Update File line.
- Patch MUST include a non-trivial change (not placeholders like /abs/path/to/file.py or 'old'/'new').
- Output MUST end with the exact line: *** End Patch
- No markdown fences. No extra commentary.

Helpful code snippet from adversarial_harness/session.py (current):
{snippet}

Now produce the patch."""


_JSON_OBJECT_RE = re.compile(r"\{[\s\S]*\}\s*$")


def _safe_abs_path(path: str) -> str:
    if not isinstance(path, str) or not path:
        raise ValueError("path is required")
    candidate = os.path.abspath(os.path.join(PROJECT_ROOT, path)) if not os.path.isabs(path) else os.path.abspath(path)
    root = os.path.abspath(PROJECT_ROOT)
    if candidate == root or candidate.startswith(root + os.sep):
        return candidate
    raise ValueError(f"Path is outside repository root: {path}")


def _tool_ls(*, path: str) -> str:
    p = _safe_abs_path(path)
    if not os.path.isdir(p):
        return f"ERROR: not a directory: {path}"
    try:
        names = sorted(os.listdir(p))
    except Exception as e:
        return f"ERROR: ls failed: {e}"
    # Keep outputs small.
    if len(names) > 200:
        names = names[:200] + ["...(truncated)"]
    return "\n".join(names)


def _tool_cat(*, path: str, start_line: int = 1, end_line: int = 200) -> str:
    p = _safe_abs_path(path)
    if not os.path.isfile(p):
        return f"ERROR: not a file: {path}"
    start = max(1, int(start_line or 1))
    end = max(start, int(end_line or start))
    max_span = 400
    if (end - start + 1) > max_span:
        end = start + max_span - 1
    try:
        with open(p, "r", encoding="utf-8", errors="replace") as f:
            lines = f.read().splitlines()
    except Exception as e:
        return f"ERROR: cat failed: {e}"
    total = len(lines)
    sel = lines[start - 1 : min(end, total)]
    header = f"FILE: {os.path.relpath(p, PROJECT_ROOT)} ({start}-{min(end, total)} of {total})"
    body = "\n".join(f"{i+start}: {line}" for i, line in enumerate(sel))
    suffix = "\n...(truncated)" if end < total else ""
    return header + "\n" + body + suffix


def _tool_grep(*, pattern: str, path: str, max_matches: int = 50) -> str:
    p = _safe_abs_path(path)
    try:
        rx = re.compile(pattern)
    except re.error:
        rx = None
    max_m = max(1, min(int(max_matches or 50), 200))

    matches: List[str] = []

    def scan_file(fp: str) -> None:
        nonlocal matches
        try:
            with open(fp, "r", encoding="utf-8", errors="replace") as f:
                for i, line in enumerate(f, start=1):
                    ok = (rx.search(line) is not None) if rx else (pattern in line)
                    if ok:
                        rel = os.path.relpath(fp, PROJECT_ROOT)
                        matches.append(f"{rel}:{i}:{line.rstrip()}"[:500])
                        if len(matches) >= max_m:
                            return
        except Exception:
            return

    if os.path.isfile(p):
        scan_file(p)
    elif os.path.isdir(p):
        for root, _dirs, files in os.walk(p):
            for name in files:
                if len(matches) >= max_m:
                    break
                fp = os.path.join(root, name)
                # Skip huge/binary-ish files by extension heuristic.
                if name.endswith((".png", ".jpg", ".jpeg", ".gif", ".pdf", ".zip", ".gz", ".db", ".duckdb")):
                    continue
                scan_file(fp)
            if len(matches) >= max_m:
                break
    else:
        return f"ERROR: path not found: {path}"

    if not matches:
        return "(no matches)"
    out = "\n".join(matches)
    if len(matches) >= max_m:
        out += "\n...(truncated)"
    return out


class PatchApplyError(Exception):
    def __init__(
        self,
        message: str,
        *,
        file_path: Optional[str] = None,
        hunk_index: Optional[int] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.file_path = file_path
        self.hunk_index = hunk_index
        self.details = details or None


def _validate_python_syntax(file_path: str, file_lines: List[str]) -> None:
    if not file_path.endswith(".py"):
        return
    src = "\n".join(file_lines) + "\n"
    try:
        compile(src, file_path, "exec")
    except SyntaxError as e:
        detail = (e.msg or "SyntaxError").strip()
        loc = f"line {e.lineno}" if e.lineno else "unknown line"
        raise PatchApplyError(f"Python syntax error after patch: {detail} ({loc})", file_path=file_path) from e


def _parse_apply_patch(text: str) -> List[Tuple[str, List[List[str]]]]:
    """Parse apply_patch formatted text into [(file_path, [hunk_lines...])]."""
    text = _normalize_patch_text(text)
    lines = text.splitlines()
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()

    if not lines or lines[0].strip() != "*** Begin Patch" or lines[-1].strip() != "*** End Patch":
        raise PatchApplyError("Not in apply_patch format")

    global_prefix_hint = False
    for ln in lines:
        if ln.startswith("*** ") or ln.startswith("@@"):
            continue
        if ln.startswith(("+", "-")):
            if len(ln) >= 3 and ln[1] == " " and ln[2] != " ":
                global_prefix_hint = True
                break
        if ln.startswith(" ") and (len(ln) == 1 or ln[1] != " "):
            global_prefix_hint = True
            break

    i = 1
    file_blocks: List[Tuple[str, List[List[str]]]] = []
    current_file: Optional[str] = None
    current_hunks: List[List[str]] = []
    current_hunk: Optional[List[str]] = None

    def normalize_hunk_lines(raw_lines: List[str]) -> List[str]:
        def leading_space_count(s: str) -> int:
            n = 0
            for ch in s:
                if ch == " ":
                    n += 1
                else:
                    break
            return n

        def looks_like_unified_diff_prefix(ln: str) -> bool:
            """Detect common unified-diff prefixes that Codex sometimes emits.

            apply_patch format expects raw file lines (optionally prefixed with + / -).
            Unified diffs often prefix unchanged lines with a single leading space.
            For Python, that produces leading whitespace counts of 5, 9, 13, ... which
            won't match the underlying file. We strip that prefix when detected.
            """
            if not ln:
                return False
            if ln.startswith(("*** ", "@@")):
                return False
            if ln[0] in "+-":
                # Some diffs include an extra space after +/- before the actual line.
                if len(ln) > 1 and ln[1] == " ":
                    return leading_space_count(ln[1:]) % 4 == 1
                return False
            if ln.startswith(" "):
                return leading_space_count(ln) % 4 == 1
            return False

        strip_global_prefix = global_prefix_hint or any(
            looks_like_unified_diff_prefix(ln) for ln in raw_lines
        )

        out: List[str] = []
        for ln in raw_lines:
            if not strip_global_prefix:
                out.append(ln)
                continue

            if ln.startswith(("+", "-")) and len(ln) > 1 and ln[1] == " ":
                if leading_space_count(ln[1:]) % 4 == 1:
                    out.append(ln[0] + ln[2:])
                    continue

            if ln.startswith(" "):
                if leading_space_count(ln) % 4 == 1:
                    out.append(ln[1:])
                    continue

            out.append(ln)

        return out

    def flush_file() -> None:
        nonlocal current_file, current_hunks, current_hunk
        if current_file is None:
            return
        if current_hunk is not None and current_hunk:
            current_hunks.append(normalize_hunk_lines(current_hunk))
        file_blocks.append((current_file, current_hunks))
        current_file = None
        current_hunks = []
        current_hunk = None

    while i < len(lines) - 1:
        line = lines[i]
        if line.startswith("*** Update File:"):
            flush_file()
            current_file = line.split(":", 1)[1].strip()
            current_hunks = []
            current_hunk = None
            i += 1
            continue
        if line.startswith("*** Add File:") or line.startswith("*** Delete File:"):
            raise PatchApplyError("Only '*** Update File' patches are supported")
        if line.startswith("@@"):
            if current_file is None:
                i += 1
                continue
            if current_hunk is not None and current_hunk:
                current_hunks.append(normalize_hunk_lines(current_hunk))
            current_hunk = []
            i += 1
            continue

        if current_file is not None:
            if current_hunk is None:
                current_hunk = []
            current_hunk.append(line)
        i += 1

    flush_file()
    return file_blocks


def _find_subsequence(haystack: List[str], needle: List[str]) -> Optional[int]:
    if not needle:
        return None
    max_i = len(haystack) - len(needle)
    for i in range(max_i + 1):
        if haystack[i : i + len(needle)] == needle:
            return i
    return None


def _find_subsequence_rstrip(haystack: List[str], needle: List[str]) -> Optional[int]:
    if not needle:
        return None
    hay = [h.rstrip() for h in haystack]
    ned = [n.rstrip() for n in needle]
    max_i = len(hay) - len(ned)
    for i in range(max_i + 1):
        if hay[i : i + len(ned)] == ned:
            return i
    return None


def _find_subsequence_relaxed_indent(haystack: List[str], needle: List[str]) -> Optional[int]:
    """Fallback matching that ignores leading indentation differences.

    This is intentionally conservative: it only succeeds when there is exactly ONE
    matching location, to avoid applying hunks to the wrong region.
    """

    if not needle:
        return None

    hay = [h.strip() for h in haystack]
    ned = [n.strip() for n in needle]
    max_i = len(hay) - len(ned)
    matches: List[int] = []
    for i in range(max_i + 1):
        if hay[i : i + len(ned)] == ned:
            matches.append(i)
            if len(matches) > 1:
                return None
    return matches[0] if matches else None


def _apply_hunk_to_lines(file_lines: List[str], hunk_lines: List[str]) -> List[str]:
    old_block: List[str] = []
    new_block: List[str] = []
    for raw in hunk_lines:
        if raw.startswith("-"):
            old_block.append(raw[1:])
        elif raw.startswith("+"):
            new_block.append(raw[1:])
        else:
            old_block.append(raw)
            new_block.append(raw)

    pos = _find_subsequence(file_lines, old_block)
    if pos is None:
        pos = _find_subsequence_rstrip(file_lines, old_block)
    if pos is None:
        pos = _find_subsequence_relaxed_indent(file_lines, old_block)
    if pos is None:
        def clip(lines: List[str], limit: int = 80) -> List[str]:
            return lines if len(lines) <= limit else (lines[:limit] + ["...<clipped>..."])

        raise PatchApplyError(
            "Hunk context not found",
            details={
                "old_block": clip(old_block),
                "new_block": clip(new_block),
                "hunk_lines": clip(list(hunk_lines)),
            },
        )

    return file_lines[:pos] + new_block + file_lines[pos + len(old_block) :]


def _build_failure_excerpt_from_file_lines(
    *,
    file_path: str,
    file_lines: List[str],
    failure_details: Optional[Dict[str, Any]],
    window_lines: int = 80,
) -> Dict[str, Any]:
    """Build a compact excerpt around a likely anchor line.

    The excerpt is meant to be embedded into error JSON and then fed back to Codex.
    """

    total = len(file_lines)
    window_lines = max(20, int(window_lines))

    anchor: Optional[str] = None
    old_block = None
    if isinstance(failure_details, dict):
        old_block = failure_details.get("old_block")
    if isinstance(old_block, list):
        for ln in old_block:
            if not isinstance(ln, str):
                continue
            s = ln.strip()
            if not s:
                continue
            if s.startswith("#"):
                continue
            if len(s) < 8:
                continue
            anchor = ln
            break

    start = 0
    end = min(total, window_lines)
    if anchor is not None:
        try:
            pos = file_lines.index(anchor)
            half = window_lines // 2
            start = max(0, pos - half)
            end = min(total, start + window_lines)
            start = max(0, end - window_lines)
        except ValueError:
            # Anchor not found; keep default head excerpt.
            pass

    excerpt_lines = [f"{i+1}: {file_lines[i]}" for i in range(start, end)]
    return {
        "file_excerpt": excerpt_lines,
        "file_context": {
            "path": file_path,
            "start_line": start + 1,
            "end_line": end,
            "total_lines": total,
        },
    }


def _extract_json_block_after_header(text: str, header: str) -> Optional[str]:
    """Extract a JSON value that appears after a header line in the base prompt."""

    if not isinstance(text, str) or not text:
        return None
    idx = text.find(header)
    if idx < 0:
        return None
    after = text[idx + len(header) :]
    # The JSON block typically begins on the next line.
    if after.startswith("\n"):
        after = after[1:]
    # Stop at the next double-newline section break.
    end = after.find("\n\n")
    blob = after if end < 0 else after[:end]
    blob = blob.strip()
    return blob or None


def _make_task_reminder(base_prompt: str) -> str:
    """Build a short reminder line to keep Codex on-task each turn."""

    focus_summary = ""
    suspected_summary = ""
    try:
        focus_blob = _extract_json_block_after_header(
            base_prompt, "Primary focus (computed from diagnostics):\n"
        )
        if focus_blob:
            focus_val = json.loads(focus_blob)
            if isinstance(focus_val, list) and focus_val:
                items = [str(x) for x in focus_val[:2] if x]
                focus_summary = "; ".join(items)
    except Exception:
        focus_summary = ""

    try:
        sus_blob = _extract_json_block_after_header(
            base_prompt, "Suspected files to start with:\n"
        )
        if sus_blob:
            sus_val = json.loads(sus_blob)
            if isinstance(sus_val, list) and sus_val:
                # Keep it short: file basenames only.
                basenames = [os.path.basename(str(p)) for p in sus_val[:3] if p]
                suspected_summary = ",".join(basenames)
    except Exception:
        suspected_summary = ""

    parts = [
        "SYSTEM_TASK_REMINDER:",
        (f"focus={focus_summary}" if focus_summary else "focus=follow the diagnostics"),
        (f"start={suspected_summary}" if suspected_summary else ""),
        "output=ONE coherent apply_patch block",
        "no placeholders/no bare @@",
        "fix validation by copying file_excerpt lines verbatim",
    ]
    return " ".join([p for p in parts if p]).strip()


def _extract_update_files_from_patch_text(patch_text: str) -> List[str]:
    """Best-effort: extract absolute file paths targeted by a patch."""

    try:
        blocks = _parse_apply_patch(_normalize_patch_text(patch_text))
    except Exception:
        return []
    out: List[str] = []
    for fp, _ in blocks:
        if isinstance(fp, str) and fp:
            out.append(fp)
    return out


def _multi_file_excerpts_for_prompt(
    file_paths: List[str],
    *,
    patch_text: Optional[str] = None,
    max_files: int = 4,
    lines_each: int = 50,
) -> str:
    """Build a clipped multi-file excerpt block for Codex repair prompts."""

    patch_text_norm = None
    patch_blocks = None
    if isinstance(patch_text, str) and patch_text.strip():
        patch_text_norm = _normalize_patch_text(patch_text)
        try:
            patch_blocks = _parse_apply_patch(patch_text_norm)
        except Exception:
            patch_blocks = None

    def excerpt_for_file(fp: str) -> Dict[str, Any]:
        # Default: head excerpt.
        try:
            with open(fp, "r", encoding="utf-8", errors="replace") as f:
                lines = f.read().splitlines()
        except Exception:
            return {}

        if patch_blocks:
            # Try to anchor around a line from the old_block context in the patch.
            for pfp, hunks in patch_blocks:
                if pfp != fp:
                    continue
                for hunk_lines in hunks:
                    old_block: List[str] = []
                    for raw in hunk_lines:
                        if raw.startswith("-"):
                            old_block.append(raw[1:])
                        elif raw.startswith("+"):
                            continue
                        else:
                            old_block.append(raw)
                    if old_block:
                        return _build_failure_excerpt_from_file_lines(
                            file_path=fp,
                            file_lines=lines,
                            failure_details={"old_block": old_block},
                            window_lines=int(lines_each),
                        )

        return _build_failure_excerpt_from_file_lines(
            file_path=fp,
            file_lines=lines,
            failure_details=None,
            window_lines=int(lines_each),
        )

    out_lines: List[str] = []
    picked = 0
    for fp in file_paths:
        if picked >= max(1, int(max_files)):
            break
        if not isinstance(fp, str) or not fp:
            continue
        try:
            _safe_abs_path(fp)
        except Exception:
            continue
        if not os.path.isfile(fp):
            continue
        excerpt = excerpt_for_file(fp)
        if not excerpt:
            continue
        out_lines.append(f"FILE_CONTEXT: {fp}")
        ctx = excerpt.get("file_context") or {}
        out_lines.append(
            f"RANGE: {ctx.get('start_line')}..{ctx.get('end_line')} of {ctx.get('total_lines')}"
        )
        for ln in excerpt.get("file_excerpt") or []:
            out_lines.append(str(ln))
        out_lines.append("")
        picked += 1

    return "\n".join(out_lines).strip()


def _dry_run_apply_patch_text(patch_text: str) -> List[str]:
    """Return list of files that would be updated, or raise PatchApplyError."""
    patch_text = _normalize_patch_text(patch_text)
    file_blocks = _parse_apply_patch(patch_text)
    if not file_blocks:
        return []

    updated_files: List[str] = []
    for file_path, hunks in file_blocks:
        if not os.path.isabs(file_path):
            raise PatchApplyError("Patch paths must be absolute", file_path=file_path)
        try:
            _safe_abs_path(file_path)
        except Exception as e:
            raise PatchApplyError("Patch path not allowed", file_path=file_path, details={"error": str(e)}) from e
        if not os.path.isfile(file_path):
            raise PatchApplyError("Target file does not exist", file_path=file_path)

        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            file_lines = f.read().splitlines()

        for hunk_index, hunk_lines in enumerate(hunks):
            try:
                file_lines = _apply_hunk_to_lines(file_lines, hunk_lines)
            except PatchApplyError as e:
                details = dict(e.details or {}) if isinstance(e.details, dict) else {}
                details.update(
                    _build_failure_excerpt_from_file_lines(
                        file_path=file_path,
                        file_lines=file_lines,
                        failure_details=details,
                    )
                )
                raise PatchApplyError(e.message, file_path=file_path, hunk_index=hunk_index, details=details) from e

        _validate_python_syntax(file_path, file_lines)
        if file_path not in updated_files:
            updated_files.append(file_path)

    return updated_files


def _extract_apply_patch_blocks(text: str) -> List[str]:
    """Extract one-or-more apply_patch blocks from text.

    Codex sometimes returns multiple "*** Begin Patch ... *** End Patch" blocks
    in a single response. Treating that as one combined patch causes the
    intermediate boundary lines to be interpreted as hunk context.
    """

    normalized = _normalize_patch_text(text or "")
    pattern = re.compile(r"\*\*\* Begin Patch.*?\*\*\* End Patch", re.DOTALL)
    blocks = [m.group(0).strip() for m in pattern.finditer(normalized)]
    if blocks:
        return blocks
    if _looks_like_apply_patch(normalized):
        return [normalized]
    return []


def _pick_first_valid_patch(text: str) -> Optional[str]:
    """Return first apply_patch block that passes dry-run validation."""

    candidate, _ = _pick_best_valid_patch_with_report(text)
    return candidate


def _combine_apply_patch_blocks(blocks: List[str]) -> str:
    """Combine multiple apply_patch blocks into a single apply_patch patch.

    Each input block must begin with '*** Begin Patch' and end with '*** End Patch'.
    The combined output contains one Begin/End wrapper and concatenates the
    internal patch bodies.
    """

    bodies: List[str] = []
    for b in blocks:
        lines = _normalize_patch_text(b).splitlines()
        while lines and not lines[0].strip():
            lines.pop(0)
        while lines and not lines[-1].strip():
            lines.pop()
        if not lines or lines[0].strip() != "*** Begin Patch" or lines[-1].strip() != "*** End Patch":
            raise PatchApplyError("Not in apply_patch format")
        body = lines[1:-1]
        bodies.extend(body)

    out_lines = ["*** Begin Patch"]
    out_lines.extend(bodies)
    out_lines.append("*** End Patch")
    return "\n".join(out_lines).strip() + "\n"


def _pick_first_valid_patch_with_report(
    text: str,
    *,
    max_blocks: int = 12,
) -> Tuple[Optional[str], Dict[str, Any]]:
    """Pick the first valid patch block and return a validation report.

    Codex sometimes emits multiple "*** Begin Patch ... *** End Patch" blocks.
    We validate blocks independently and return the first one that dry-runs.
    The returned report is designed to be JSON-serializable.
    """

    blocks = _extract_apply_patch_blocks(text)
    report: Dict[str, Any] = {
        "block_count": len(blocks),
        "max_blocks": int(max_blocks),
        "blocks": [],
        "valid_count": 0,
        "selected_index": None,
    }
    if not blocks:
        return None, report

    selected: Optional[str] = None
    for idx, block in enumerate(blocks[: max(1, int(max_blocks))]):
        if not _looks_like_apply_patch(block):
            report["blocks"].append(
                {
                    "index": idx,
                    "ok": False,
                    "looks_like_apply_patch": False,
                    "error": {"message": "Not in apply_patch format"},
                }
            )
            continue

        try:
            updated = _dry_run_apply_patch_text(block)
            report["valid_count"] += 1
            report["blocks"].append(
                {
                    "index": idx,
                    "ok": True,
                    "looks_like_apply_patch": True,
                    "would_update_files": updated,
                    "note": ("no-op patch" if not updated else None),
                }
            )
            if selected is None:
                selected = block
                report["selected_index"] = idx
        except PatchApplyError as e:
            report["blocks"].append(
                {
                    "index": idx,
                    "ok": False,
                    "looks_like_apply_patch": True,
                    "error": {
                        "message": e.message,
                        "file_path": e.file_path,
                        "hunk_index": e.hunk_index,
                        "details": e.details,
                    },
                }
            )

    return selected, report


def _pick_best_valid_patch_with_report(
    text: str,
    *,
    max_blocks: int = 12,
) -> Tuple[Optional[str], Dict[str, Any]]:
    """Pick the best patch from a model output.

    - If exactly one block validates, select it.
    - If multiple blocks validate, attempt to combine them into a single patch
      and select the combined patch only if it also validates.

    If multiple blocks validate individually but cannot be combined cleanly,
    we return (None, report) so the caller can ask Codex to produce a single
    coherent patch.
    """

    first, report = _pick_first_valid_patch_with_report(text, max_blocks=max_blocks)
    blocks = _extract_apply_patch_blocks(text)
    report["selected_kind"] = "single" if first is not None else None
    report["selected_indices"] = [report.get("selected_index")] if report.get("selected_index") is not None else []

    valid_blocks: List[Tuple[int, str]] = []
    for entry in report.get("blocks", []):
        if entry.get("ok") is True and isinstance(entry.get("index"), int):
            idx = int(entry["index"])
            if 0 <= idx < len(blocks):
                valid_blocks.append((idx, blocks[idx]))

    if len(valid_blocks) <= 1:
        return first, report

    # Multiple valid blocks: try combining.
    try:
        combined_text = _combine_apply_patch_blocks([b for _, b in valid_blocks])
        _dry_run_apply_patch_text(combined_text)
    except PatchApplyError as e:
        report["selected_kind"] = None
        report["selected_index"] = None
        report["selected_indices"] = [i for i, _ in valid_blocks]
        report["combined_validation"] = {
            "ok": False,
            "error": {
                "message": e.message,
                "file_path": e.file_path,
                "hunk_index": e.hunk_index,
                "details": e.details,
            },
        }
        return None, report

    report["selected_kind"] = "combined"
    report["selected_indices"] = [i for i, _ in valid_blocks]
    report["combined_validation"] = {"ok": True}
    return combined_text, report


def _apply_patch_transaction(patch_text: str) -> Tuple[List[str], Dict[str, str]]:
    """Apply patch in-memory across all files first, then write.

    Returns (updated_files, original_text_by_file) on success.
    """

    patch_text = _normalize_patch_text(patch_text)
    file_blocks = _parse_apply_patch(patch_text)
    if not file_blocks:
        return ([], {})

    original_text_by_file: Dict[str, str] = {}
    updated_lines_by_file: Dict[str, List[str]] = {}

    for file_path, _ in file_blocks:
        if not os.path.isabs(file_path):
            raise PatchApplyError("Patch paths must be absolute", file_path=file_path)
        try:
            _safe_abs_path(file_path)
        except Exception as e:
            raise PatchApplyError("Patch path not allowed", file_path=file_path, details={"error": str(e)}) from e
        if not os.path.isfile(file_path):
            raise PatchApplyError("Target file does not exist", file_path=file_path)
        if file_path not in original_text_by_file:
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                original_text_by_file[file_path] = f.read()
            updated_lines_by_file[file_path] = original_text_by_file[file_path].splitlines()

    updated_files: List[str] = []
    for file_path, hunks in file_blocks:
        file_lines = updated_lines_by_file[file_path]
        for hunk_index, hunk_lines in enumerate(hunks):
            try:
                file_lines = _apply_hunk_to_lines(file_lines, hunk_lines)
            except PatchApplyError as e:
                raise PatchApplyError(e.message, file_path=file_path, hunk_index=hunk_index, details=e.details) from e

        _validate_python_syntax(file_path, file_lines)
        updated_lines_by_file[file_path] = file_lines
        if file_path not in updated_files:
            updated_files.append(file_path)

    for file_path in updated_files:
        with open(file_path, "w", encoding="utf-8") as f:
            f.write("\n".join(updated_lines_by_file[file_path]) + "\n")

    return (updated_files, original_text_by_file)


def _restore_original_text(original_text_by_file: Dict[str, str]) -> None:
    for abs_path, text in original_text_by_file.items():
        os.makedirs(os.path.dirname(abs_path) or ".", exist_ok=True)
        with open(abs_path, "w", encoding="utf-8") as f:
            f.write(text)


def _run_post_apply_checks(
    *,
    updated_files: List[str],
    check_pycompile: bool,
    check_pyright: bool,
    check_pytest: bool,
) -> None:
    if check_pycompile:
        for fp in updated_files:
            if not fp.endswith(".py"):
                continue
            try:
                py_compile.compile(fp, doraise=True)
            except py_compile.PyCompileError as e:
                raise RuntimeError(f"py_compile failed for {fp}: {e}") from e

    # Pylance isn't a CLI, but pyright uses the same underlying analyzer.
    if check_pyright:
        pyright_targets = [fp for fp in updated_files if fp.endswith(".py")]
        if not pyright_targets:
            return
        pyright = shutil.which("pyright")
        if pyright:
            cmd = [pyright]
        else:
            # If installed via pip, pyright is typically available as a module.
            cmd = [sys.executable, "-m", "pyright"]

        proc = subprocess.run(
            cmd + pyright_targets,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        if proc.returncode != 0:
            raise RuntimeError("pyright failed:\n" + (proc.stdout or ""))

    if check_pytest:
        proc = subprocess.run(
            [sys.executable, "-m", "pytest", "-q"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        if proc.returncode != 0:
            raise RuntimeError("pytest failed:\n" + (proc.stdout or ""))


def _tool_patch(*, patch: str) -> str:
    text = _normalize_patch_text(patch or "")
    blocks = _extract_apply_patch_blocks(text)
    looks_like = _looks_like_apply_patch(text) or bool(blocks)

    # Single-block validation (fast path)
    if len(blocks) <= 1:
        try:
            update_files = _dry_run_apply_patch_text(text)
            result = {
                "ok": True,
                "looks_like_apply_patch": looks_like,
                "would_update_files": update_files,
                "note": ("no-op patch" if not update_files else None),
            }
            return json.dumps(result, ensure_ascii=False, indent=2)
        except PatchApplyError as e:
            result = {
                "ok": False,
                "looks_like_apply_patch": looks_like,
                "error": {
                    "message": e.message,
                    "file_path": e.file_path,
                    "hunk_index": e.hunk_index,
                    "details": e.details,
                },
            }
            return json.dumps(result, ensure_ascii=False, indent=2)

    # Multi-block validation: validate each block individually, then validate a combined patch
    # built from all individually-valid blocks.
    _, report = _pick_first_valid_patch_with_report(text)
    valid_indices = [
        int(b["index"]) for b in report.get("blocks", [])
        if b.get("ok") is True and isinstance(b.get("index"), int)
    ]
    valid_blocks = [blocks[i] for i in valid_indices if 0 <= i < len(blocks)]

    combined_ok = False
    combined_error: Optional[Dict[str, Any]] = None
    combined_would_update: List[str] = []
    if valid_blocks:
        try:
            combined_text = _combine_apply_patch_blocks(valid_blocks)
            combined_would_update = _dry_run_apply_patch_text(combined_text)
            combined_ok = True
        except PatchApplyError as e:
            combined_error = {
                "message": e.message,
                "file_path": e.file_path,
                "hunk_index": e.hunk_index,
                "details": e.details,
            }

    result = {
        "ok": combined_ok,
        "looks_like_apply_patch": looks_like,
        "multi_block": True,
        "block_count": len(blocks),
        "valid_block_count": len(valid_blocks),
        "blocks": report.get("blocks", []),
        "combined": {
            "ok": combined_ok,
            "would_update_files": combined_would_update,
            "error": combined_error,
        },
    }
    return json.dumps(result, ensure_ascii=False, indent=2)


def _try_parse_json_object(text: str) -> Optional[Dict[str, Any]]:
    if not isinstance(text, str):
        return None
    s = text.strip()
    if not s.startswith("{"):
        # Try to recover a trailing JSON object.
        m = _JSON_OBJECT_RE.search(s)
        if not m:
            return None
        s = m.group(0)
    try:
        obj = json.loads(s)
    except json.JSONDecodeError:
        # Model output is untrusted and malformed JSON is an expected miss.
        # Unexpected decoder/runtime failures must remain visible to callers.
        return None
    return obj if isinstance(obj, dict) else None


def _run_codex_with_tools(*, backend: LLMRouterBackend, base_prompt: str, max_steps: int = 8) -> str:
    raise RuntimeError("Use _run_codex_with_tools_logged")


def _append_jsonl(path: str, obj: Dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")


def _append_jsonl_best_effort(path: str, obj: Dict[str, Any], *, event_name: str) -> bool:
    """Append an optional transcript event, warning on expected artifact failures.

    Transcript events supplement the primary run artifacts, so an unavailable
    transcript must not replace the operational error being reported.  Keep
    expected filesystem and text-encoding failures non-fatal, but make them
    visible and allow unexpected implementation failures to propagate.
    """
    try:
        _append_jsonl(path, obj)
    except (OSError, UnicodeError) as exc:
        print(
            f"Warning: could not append {event_name} event to transcript "
            f"{os.path.abspath(path)}: {exc}",
            file=sys.stderr,
        )
        return False
    return True


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _run_codex_with_tools_logged(
    *,
    backend: LLMRouterBackend,
    base_prompt: str,
    max_steps: int = 8,
    chat_jsonl_path: Optional[str] = None,
) -> str:
    tool_log: List[str] = []
    last_output = ""
    task_reminder = _make_task_reminder(base_prompt)

    def _compact_for_prompt(text: str, *, max_chars: int = 2200, max_lines: int = 80) -> str:
        """Compact tool results/validation before re-injecting into the rolling prompt.

        We still persist full results in the JSONL transcript, but keeping the
        rolling prompt compact materially reduces prompt tokens on later turns.
        """

        if not isinstance(text, str):
            text = str(text)
        lines = text.splitlines()
        if len(lines) > max_lines:
            head = lines[: max_lines // 2]
            tail = lines[-(max_lines - len(head)) :]
            omitted = len(lines) - len(head) - len(tail)
            lines = head + [f"...(omitted {omitted} lines)..."] + tail
        out = "\n".join(lines)
        if len(out) > max_chars:
            keep = max(200, max_chars // 2)
            out = out[:keep] + "\n...(omitted chars)...\n" + out[-keep:]
        return out

    if chat_jsonl_path:
        _append_jsonl(
            chat_jsonl_path,
            {
                "event": "session_start",
                "ts": _utc_iso(),
                "tool_protocol": "v1",
                "max_steps": int(max_steps),
                "base_prompt": base_prompt,
            },
        )

    for step in range(max(1, int(max_steps))):
        transcript = base_prompt
        if tool_log:
            transcript += "\n\n" + "\n\n".join(tool_log[-8:])
        transcript += "\n\n" + task_reminder

        if chat_jsonl_path:
            _append_jsonl(
                chat_jsonl_path,
                {
                    "event": "prompt",
                    "ts": _utc_iso(),
                    "step": step + 1,
                    "tool_log_tail": tool_log[-8:],
                },
            )

        out = backend(transcript)
        last_output = out or ""

        if chat_jsonl_path:
            _append_jsonl(
                chat_jsonl_path,
                {
                    "event": "model_output",
                    "ts": _utc_iso(),
                    "step": step + 1,
                    "text": last_output,
                },
            )

        # IMPORTANT: Prefer handling JSON tool/final outputs first.
        # Otherwise, apply_patch blocks embedded inside JSON string fields (escaped "\\n")
        # get misinterpreted as raw patches and will always fail validation.
        obj = _try_parse_json_object(last_output)
        if obj:
            typ = obj.get("type")
            if typ == "final":
                patch = obj.get("patch")
                if isinstance(patch, str):
                    json_candidate, json_report = _pick_best_valid_patch_with_report(patch)
                    if json_candidate is not None:
                        if chat_jsonl_path and json_report.get("block_count", 0) > 1:
                            _append_jsonl(
                                chat_jsonl_path,
                                {
                                    "event": "patch_blocks",
                                    "ts": _utc_iso(),
                                    "step": step + 1,
                                    "kind": "json_final",
                                    "report": json_report,
                                },
                            )
                        would_update = []
                        selected_index = json_report.get("selected_index")
                        if isinstance(selected_index, int):
                            for b in json_report.get("blocks", []):
                                if b.get("index") == selected_index and b.get("ok") is True:
                                    would_update = b.get("would_update_files", []) or []
                                    break
                        if chat_jsonl_path:
                            _append_jsonl(
                                chat_jsonl_path,
                                {
                                    "event": "patch_candidate",
                                    "ts": _utc_iso(),
                                    "step": step + 1,
                                    "kind": "json_final",
                                    "ok": True,
                                    "would_update_files": would_update,
                                    "block_index": json_report.get("selected_index"),
                                    "block_count": json_report.get("block_count"),
                                    "valid_count": json_report.get("valid_count"),
                                },
                            )
                        return json_candidate

                    if json_report.get("block_count", 0) > 1 and json_report.get("valid_count", 0) > 1:
                        blocks = _extract_apply_patch_blocks(patch)
                        valid_indices = [
                            int(b["index"]) for b in json_report.get("blocks", [])
                            if b.get("ok") is True and isinstance(b.get("index"), int)
                        ]
                        valid_blocks = [blocks[i] for i in valid_indices if 0 <= i < len(blocks)]
                        try:
                            combined_text = _combine_apply_patch_blocks(valid_blocks)
                        except Exception:
                            combined_text = ""
                        if combined_text:
                            validation = _tool_patch(patch=combined_text)
                            involved = _extract_update_files_from_patch_text(combined_text)
                            context = _multi_file_excerpts_for_prompt(involved, patch_text=combined_text)
                            tool_log.append(
                                "SYSTEM: Your JSON final included multiple independently-valid patch blocks, "
                                "but they did not combine into a single transactional patch. Return ONE coherent patch block "
                                "that includes ALL intended changes across files."
                            )
                            tool_log.append("PATCH_VALIDATION:\n" + _compact_for_prompt(validation))
                            if context:
                                tool_log.append(
                                    "MULTI_FILE_CONTEXT:\n" + _compact_for_prompt(context, max_chars=2200, max_lines=120)
                                )
                            if chat_jsonl_path:
                                _append_jsonl(
                                    chat_jsonl_path,
                                    {
                                        "event": "combined_patch_failed",
                                        "ts": _utc_iso(),
                                        "step": step + 1,
                                        "validation": json.loads(validation),
                                        "multi_file_context": context,
                                        "report": json_report,
                                    },
                                )
                            continue

                    json_blocks = _extract_apply_patch_blocks(patch)
                    if json_blocks:
                        first = json_blocks[0]
                        if chat_jsonl_path:
                            _append_jsonl(
                                chat_jsonl_path,
                                {
                                    "event": "patch_candidate",
                                    "ts": _utc_iso(),
                                    "step": step + 1,
                                    "kind": "json_final",
                                    "ok": False,
                                    "validation": json.loads(_tool_patch(patch=first)),
                                },
                            )
                        tool_log.append(
                            "SYSTEM: Your JSON final patch failed dry-run validation. Fix it, and consider calling the patch tool before finalizing."
                        )
                        tool_log.append("PATCH_VALIDATION:\n" + _compact_for_prompt(_tool_patch(patch=first)))
                        continue

                tool_log.append(
                    "SYSTEM: Your previous JSON final did not include a valid apply_patch patch. Return ONLY a corrected final patch."
                )
                continue

            if typ != "tool":
                tool_log.append("SYSTEM: Invalid JSON. 'type' must be 'tool' or 'final'.")
                continue

            tool = obj.get("tool")
            args = obj.get("args")
            if not isinstance(tool, str) or not isinstance(args, dict):
                tool_log.append("SYSTEM: Invalid tool request. Must include string 'tool' and object 'args'.")
                continue

            try:
                if tool == "ls":
                    result = _tool_ls(path=str(args.get("path", ".")))
                elif tool == "cat":
                    result = _tool_cat(
                        path=str(args.get("path", "")),
                        start_line=int(args.get("start_line", 1) or 1),
                        end_line=int(args.get("end_line", 200) or 200),
                    )
                elif tool == "grep":
                    result = _tool_grep(
                        pattern=str(args.get("pattern", "")),
                        path=str(args.get("path", ".")),
                        max_matches=int(args.get("max_matches", 50) or 50),
                    )
                elif tool == "patch":
                    result = _tool_patch(patch=str(args.get("patch", "")))
                else:
                    result = f"ERROR: unknown tool: {tool}"
            except Exception as e:
                result = f"ERROR: tool execution failed: {e}"

            if chat_jsonl_path:
                _append_jsonl(
                    chat_jsonl_path,
                    {
                        "event": "tool_call",
                        "ts": _utc_iso(),
                        "step": step + 1,
                        "tool": tool,
                        "args": args,
                    },
                )
                _append_jsonl(
                    chat_jsonl_path,
                    {
                        "event": "tool_result",
                        "ts": _utc_iso(),
                        "step": step + 1,
                        "tool": tool,
                        "result": result,
                    },
                )

            tool_log.append(
                f"TOOL_CALL(step={step+1}): {json.dumps(obj, ensure_ascii=False)}\nTOOL_RESULT:\n{_compact_for_prompt(result)}".strip()
            )
            continue

        # No JSON: treat as raw patch output.
        raw_candidate, raw_report = _pick_best_valid_patch_with_report(last_output)
        if raw_candidate is not None:
            if chat_jsonl_path and raw_report.get("block_count", 0) > 1:
                _append_jsonl(
                    chat_jsonl_path,
                    {
                        "event": "patch_blocks",
                        "ts": _utc_iso(),
                        "step": step + 1,
                        "kind": "raw",
                        "report": raw_report,
                    },
                )
            would_update = []
            selected_index = raw_report.get("selected_index")
            if isinstance(selected_index, int):
                for b in raw_report.get("blocks", []):
                    if b.get("index") == selected_index and b.get("ok") is True:
                        would_update = b.get("would_update_files", []) or []
                        break
            if chat_jsonl_path:
                _append_jsonl(
                    chat_jsonl_path,
                    {
                        "event": "patch_candidate",
                        "ts": _utc_iso(),
                        "step": step + 1,
                        "kind": "raw",
                        "ok": True,
                        "would_update_files": would_update,
                        "block_index": raw_report.get("selected_index"),
                        "block_count": raw_report.get("block_count"),
                        "valid_count": raw_report.get("valid_count"),
                    },
                )
            return raw_candidate

        # Multiple blocks may each validate, but the combined patch may still fail.
        # If that happens, provide combined validation back to the model.
        if raw_report.get("block_count", 0) > 1 and raw_report.get("valid_count", 0) > 1:
            combined_text = ""
            try:
                blocks = _extract_apply_patch_blocks(last_output)
                valid_indices = [
                    int(b["index"]) for b in raw_report.get("blocks", [])
                    if b.get("ok") is True and isinstance(b.get("index"), int)
                ]
                valid_blocks = [blocks[i] for i in valid_indices if 0 <= i < len(blocks)]
                combined_text = _combine_apply_patch_blocks(valid_blocks)
            except Exception:
                combined_text = ""
            if combined_text:
                validation = _tool_patch(patch=combined_text)
                involved = _extract_update_files_from_patch_text(combined_text)
                context = _multi_file_excerpts_for_prompt(involved, patch_text=combined_text)
                tool_log.append(
                    "SYSTEM: Your output contained multiple independently-valid patch blocks, "
                    "but they did not combine into a single transactional patch. Return ONE coherent patch block "
                    "that includes ALL intended changes across files."
                )
                tool_log.append("PATCH_VALIDATION:\n" + _compact_for_prompt(validation))
                if context:
                    tool_log.append("MULTI_FILE_CONTEXT:\n" + _compact_for_prompt(context, max_chars=2200, max_lines=120))
                if chat_jsonl_path:
                    _append_jsonl(
                        chat_jsonl_path,
                        {
                            "event": "combined_patch_failed",
                            "ts": _utc_iso(),
                            "step": step + 1,
                            "validation": json.loads(validation),
                            "multi_file_context": context,
                            "report": raw_report,
                        },
                    )
                continue

        # If we got apply_patch-looking output but it failed, log the first block's validation
        # so the model can repair it.
        raw_blocks = _extract_apply_patch_blocks(last_output)
        if raw_blocks:
            first = raw_blocks[0]
            if chat_jsonl_path:
                _append_jsonl(
                    chat_jsonl_path,
                    {
                        "event": "patch_candidate",
                        "ts": _utc_iso(),
                        "step": step + 1,
                        "kind": "raw",
                        "ok": False,
                        "validation": json.loads(_tool_patch(patch=first)),
                    },
                )
                if len(raw_blocks) > 1:
                    _append_jsonl(
                        chat_jsonl_path,
                        {
                            "event": "patch_blocks",
                            "ts": _utc_iso(),
                            "step": step + 1,
                            "kind": "raw",
                            "report": raw_report,
                        },
                    )
            tool_log.append(
                "SYSTEM: Candidate patch failed dry-run validation. Fix the patch, and consider calling the patch tool before finalizing."
            )
            if len(raw_blocks) > 1:
                tool_log.append(
                    f"SYSTEM: Your output contained {len(raw_blocks)} separate patch blocks, and none validated. Return ONE corrected patch block."
                )
            tool_log.append("PATCH_VALIDATION:\n" + _compact_for_prompt(_tool_patch(patch=first)))
            continue

        # If the model output is neither JSON nor apply_patch, nudge toward valid output formats.
        tool_log.append(
            "SYSTEM: Your previous output was not valid JSON or an apply_patch patch. "
            "Return either a JSON tool request or a JSON final patch."
        )
        continue

    # Final forced attempt
    # Important: include the tool_log tail so the model has the evidence/context
    # it gathered (otherwise it may keep asking for tools and never finalize).
    final_prompt = base_prompt
    if tool_log:
        final_prompt += "\n\n" + "\n\n".join(tool_log[-8:])
    final_prompt += "\n\n" + task_reminder
    final_prompt += (
        "\n\n"
        "Tool budget exhausted. You MUST now return ONLY a JSON {type:'final', patch:'...'} "
        "containing a valid apply_patch patch. Do NOT request any tools."
    )

    if chat_jsonl_path:
        _append_jsonl(
            chat_jsonl_path,
            {
                "event": "final_prompt",
                "ts": _utc_iso(),
                "tool_log_tail": tool_log[-8:],
            },
        )

    out = backend(final_prompt)
    if chat_jsonl_path:
        _append_jsonl(
            chat_jsonl_path,
            {
                "event": "final_model_output",
                "ts": _utc_iso(),
                "text": out or "",
            },
        )

    # If the model still tries to request tools, reprompt once more (no tools allowed).
    out_obj = _try_parse_json_object(out or "")
    if out_obj and out_obj.get("type") == "tool":
        reprompt = (
            final_prompt
            + "\n\nSYSTEM: Tool calls are not allowed now. Return ONLY the JSON final patch object."
        )
        out = backend(reprompt)
        if chat_jsonl_path:
            _append_jsonl(
                chat_jsonl_path,
                {
                    "event": "final_model_output_retry",
                    "ts": _utc_iso(),
                    "text": out or "",
                },
            )

    raw_candidate, raw_report = _pick_best_valid_patch_with_report(out or "")
    if raw_candidate is not None:
        if chat_jsonl_path and raw_report.get("block_count", 0) > 1:
            _append_jsonl(
                chat_jsonl_path,
                {
                    "event": "patch_blocks",
                    "ts": _utc_iso(),
                    "kind": "forced_final_raw",
                    "report": raw_report,
                },
            )
        return raw_candidate

    raw_blocks = _extract_apply_patch_blocks(out or "")
    if raw_blocks:
        first = raw_blocks[0]
        try:
            _dry_run_apply_patch_text(first)
            return first
        except PatchApplyError:
            validation = _tool_patch(patch=first)
            repair_prompt = (
                base_prompt
                + "\n\nYour candidate patch failed dry-run validation. Fix it."
                + "\nPATCH_VALIDATION:\n"
                + validation
                + "\n\nReturn ONLY a JSON {type:'final', patch:'...'} with a corrected patch."
            )
            if chat_jsonl_path:
                _append_jsonl(
                    chat_jsonl_path,
                    {
                        "event": "forced_patch_failed",
                        "ts": _utc_iso(),
                        "validation": json.loads(validation),
                    },
                )
            out2 = backend(repair_prompt)
            obj2 = _try_parse_json_object(out2 or "")
            if obj2 and obj2.get("type") == "final" and isinstance(obj2.get("patch"), str):
                repaired, repaired_report = _pick_best_valid_patch_with_report(obj2["patch"])
                if repaired is not None:
                    if chat_jsonl_path and repaired_report.get("block_count", 0) > 1:
                        _append_jsonl(
                            chat_jsonl_path,
                            {
                                "event": "patch_blocks",
                                "ts": _utc_iso(),
                                "kind": "forced_final_repair",
                                "report": repaired_report,
                            },
                        )
                    return repaired
    obj = _try_parse_json_object(out or "")
    if obj and obj.get("type") == "final" and isinstance(obj.get("patch"), str):
        candidate, json_report = _pick_best_valid_patch_with_report(obj["patch"])
        if candidate is not None:
            if chat_jsonl_path and json_report.get("block_count", 0) > 1:
                _append_jsonl(
                    chat_jsonl_path,
                    {
                        "event": "patch_blocks",
                        "ts": _utc_iso(),
                        "kind": "forced_final_json",
                        "report": json_report,
                    },
                )
            return candidate

        blocks = _extract_apply_patch_blocks(obj["patch"])
        if blocks:
            first = blocks[0]
            try:
                _dry_run_apply_patch_text(first)
                return first
            except PatchApplyError:
                validation = _tool_patch(patch=first)
                repair_prompt = (
                    base_prompt
                    + "\n\nYour candidate patch failed dry-run validation. Fix it."
                    + "\nPATCH_VALIDATION:\n"
                    + validation
                    + "\n\nReturn ONLY a JSON {type:'final', patch:'...'} with a corrected patch."
                )
                if chat_jsonl_path:
                    _append_jsonl(
                        chat_jsonl_path,
                        {
                            "event": "forced_patch_failed",
                            "ts": _utc_iso(),
                            "validation": json.loads(validation),
                        },
                    )
                out2 = backend(repair_prompt)
                obj2 = _try_parse_json_object(out2 or "")
                if obj2 and obj2.get("type") == "final" and isinstance(obj2.get("patch"), str):
                    repaired, repaired_report = _pick_best_valid_patch_with_report(obj2["patch"])
                    if repaired is not None:
                        if chat_jsonl_path and repaired_report.get("block_count", 0) > 1:
                            _append_jsonl(
                                chat_jsonl_path,
                                {
                                    "event": "patch_blocks",
                                    "ts": _utc_iso(),
                                    "kind": "forced_final_json_repair",
                                    "report": repaired_report,
                                },
                            )
                        return repaired
    raise SystemExit(
        "Codex did not return a valid apply_patch patch after tool loop. "
        "Re-run with different prompt or increase max steps."
    )


def _looks_like_apply_patch(text: str) -> bool:
    text = text.strip("\n")
    return text.startswith("*** Begin Patch") and text.endswith("*** End Patch") and "*** Update File:" in text


def _normalize_patch_text(text: str) -> str:
    """Normalize common near-miss formats into apply_patch text."""
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        # Drop opening fence line
        if lines:
            lines = lines[1:]
        # Drop closing fence line if present
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()

    # Normalize Begin/End Patch markers even when they appear mid-text (e.g.
    # multiple patch blocks concatenated).
    text = re.sub(r"(?m)^Begin Patch\s*$", "*** Begin Patch", text)
    text = re.sub(r"(?m)^End Patch\s*$", "*** End Patch", text)

    if text.startswith("Begin Patch"):
        text = "*** " + text

    # Some outputs omit the space: "***Begin Patch"
    if text.startswith("***Begin Patch"):
        text = text.replace("***Begin Patch", "*** Begin Patch", 1)

    return text


def _reprompt_for_real_patch(*, previous_output: str, original_prompt: str) -> str:
    return (
        original_prompt
        + "\n\n"
        + "Your previous output was invalid (not a real apply_patch patch)."
        + " Specifically: it must start with the exact line '*** Begin Patch' (3 asterisks)."
        + "\nHere is what you output last time:\n"
        + previous_output
        + "\n\nReturn ONLY a corrected apply_patch patch."
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Use Codex CLI via llm-router to propose an apply_patch patch from a persisted run"
    )
    parser.add_argument("--config", default="config.llm_router.json")
    parser.add_argument("--backend-id", default="llm-router-codex")
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--max-worst-sessions", type=int, default=3)
    parser.add_argument(
        "--context-mode",
        choices=["rich", "lean"],
        default="rich",
        help="rich inlines JSON context into the prompt; lean points Codex at JSON artifacts and relies on tool calls to fetch context",
    )
    parser.add_argument("--max-steps", type=int, default=8)

    # Backend retry/backoff (passed through to LLMRouterBackend)
    parser.add_argument(
        "--retry-max-attempts",
        type=int,
        default=1,
        help="Retry attempts for transient LLM/router failures (default: 1).",
    )
    parser.add_argument(
        "--retry-backoff-base-s",
        type=float,
        default=0.5,
        help="Base backoff seconds for retries (default: 0.5).",
    )
    parser.add_argument(
        "--retry-backoff-max-s",
        type=float,
        default=20.0,
        help="Max backoff seconds for retries (default: 20.0).",
    )
    parser.add_argument(
        "--retry-jitter-s",
        type=float,
        default=0.1,
        help="Random jitter seconds added to backoff (default: 0.1).",
    )

    # Driver-level 429 handling (Codex usage-limit): optionally sleep until reset then retry once.
    parser.set_defaults(wait_on_429=True)
    parser.add_argument(
        "--wait-on-429",
        dest="wait_on_429",
        action="store_true",
        help=(
            "If Codex returns 429/usage_limit_reached and provides resets_in_seconds, "
            "sleep then retry once (default)."
        ),
    )
    parser.add_argument(
        "--no-wait-on-429",
        dest="wait_on_429",
        action="store_false",
        help="Do not sleep/retry on 429; exit with code 2 after writing the transcript.",
    )
    parser.add_argument(
        "--wait-on-429-max-s",
        type=int,
        default=15 * 60,
        help="Maximum seconds to sleep on 429 before giving up (default: 900). Use 0 for unlimited.",
    )
    parser.add_argument(
        "--wait-on-429-max-retries",
        type=int,
        default=1,
        help=(
            "Maximum number of sleep+retry cycles on 429 before giving up (default: 1). "
            "Use 0 for unlimited."
        ),
    )
    parser.add_argument(
        "--wait-on-429-buffer-s",
        type=int,
        default=2,
        help="Extra seconds added to resets_in_seconds before retry (default: 2).",
    )
    parser.add_argument(
        "--wait-on-429-fallback-s",
        type=int,
        default=60,
        help=(
            "If a 429/usage limit error does not include resets_in_seconds, sleep this many seconds then retry "
            "(default: 60)."
        ),
    )
    parser.add_argument(
        "--wait-on-429-fallback-max-s",
        type=int,
        default=15 * 60,
        help=(
            "Maximum seconds to sleep when using fallback/exponential backoff because reset timing is unknown "
            "(default: 900). Use 0 for unlimited."
        ),
    )

    parser.add_argument(
        "--debug-rate-limit-jsonl",
        default=None,
        help=(
            "Debug: parse a Codex exec JSONL (type=error message) for reset timing and print the extracted reset_at + resets_in_seconds, "
            "then exit without making any Codex calls."
        ),
    )
    parser.add_argument(
        "--debug-rate-limit-message",
        default=None,
        help=(
            "Debug: parse a provided rate-limit error message string for reset timing and print extracted reset_at + resets_in_seconds, "
            "then exit without making any Codex calls."
        ),
    )

    parser.set_defaults(apply_patch=True)
    parser.add_argument(
        "--apply",
        dest="apply_patch",
        action="store_true",
        help="Apply the generated patch to the working tree (default).",
    )
    parser.add_argument(
        "--no-apply",
        dest="apply_patch",
        action="store_false",
        help="Do not apply the patch (only write it under <run_dir>/_patches).",
    )

    parser.set_defaults(undo_on_failure=True)
    parser.add_argument(
        "--undo-on-failure",
        dest="undo_on_failure",
        action="store_true",
        help="If apply/checks fail, restore original file contents (default).",
    )
    parser.add_argument(
        "--no-undo-on-failure",
        dest="undo_on_failure",
        action="store_false",
        help="If apply/checks fail, leave changes on disk.",
    )

    parser.set_defaults(check_pycompile=True)
    parser.add_argument(
        "--check-pycompile",
        dest="check_pycompile",
        action="store_true",
        help="Run py_compile on updated .py files after applying (default).",
    )
    parser.add_argument(
        "--no-check-pycompile",
        dest="check_pycompile",
        action="store_false",
        help="Skip py_compile checks.",
    )

    parser.set_defaults(check_pyright=False)
    parser.add_argument(
        "--check-pyright",
        dest="check_pyright",
        action="store_true",
        help="Run pyright (Pylance-like) if installed.",
    )
    parser.add_argument(
        "--no-check-pyright",
        dest="check_pyright",
        action="store_false",
        help="Skip pyright checks.",
    )
    # Enable pyright by default so the default flow runs the Pylance-like gate.
    parser.set_defaults(check_pyright=True)

    parser.set_defaults(check_pytest=True)
    parser.add_argument(
        "--check-pytest",
        dest="check_pytest",
        action="store_true",
        help="Run pytest -q after applying (default).",
    )
    parser.add_argument(
        "--no-check-pytest",
        dest="check_pytest",
        action="store_false",
        help="Skip pytest checks.",
    )
    args = parser.parse_args()

    # Debug-only: verify reset timestamp parsing without calling Codex.
    if args.debug_rate_limit_message or args.debug_rate_limit_jsonl:
        msg = None
        if args.debug_rate_limit_message:
            msg = str(args.debug_rate_limit_message)
        elif args.debug_rate_limit_jsonl:
            try:
                with open(str(args.debug_rate_limit_jsonl), "r", encoding="utf-8") as f:
                    for line in f:
                        try:
                            obj = json.loads(line)
                        except Exception:
                            continue
                        if isinstance(obj, dict) and obj.get("type") == "error" and isinstance(obj.get("message"), str):
                            msg = obj.get("message")
            except Exception as e:
                print(f"[debug] failed to read jsonl: {e}")
                return 1

        if not msg:
            print("[debug] no error message found")
            return 1

        info = _debug_extract_reset_info_from_message(msg)
        print("[debug] parsed reset info:")
        print(json.dumps(info, indent=2))
        return 0

    run_dir = args.run_dir
    cycle_summary_path = os.path.join(run_dir, "cycle_summary.json")
    if not os.path.isfile(cycle_summary_path):
        raise SystemExit(f"Missing cycle_summary.json: {cycle_summary_path}")

    cycle_summary = _load_json(cycle_summary_path)
    sgd_report_path = cycle_summary.get("sgd_report_path")
    if not sgd_report_path or not os.path.isfile(sgd_report_path):
        raise SystemExit(
            f"Missing sgd_report_path from cycle_summary or file not found: {sgd_report_path}"
        )
    sgd_report = _load_json(sgd_report_path)

    session_jsons = _find_session_jsons(run_dir)
    session_docs = [_load_json(p) for p in session_jsons]
    worst = _pick_worst_sessions(session_docs, args.max_worst_sessions)
    worst_session_paths = session_jsons[:]
    try:
        worst_ids = {d.get("session_id") for d in worst}
        worst_session_paths = [p for p, d in zip(session_jsons, session_docs) if d.get("session_id") in worst_ids]
    except Exception:
        worst_session_paths = session_jsons[: args.max_worst_sessions]

    config = _load_config(args.config)
    backend_kwargs = _get_llm_router_backend_config(config, args.backend_id)
    # Keep Codex CLI session/event logs inside the run artifacts (statefiles is git-ignored).
    # This relies on ipfs_datasets_py.llm_router trace options.
    try:
        provider = str(backend_kwargs.get("provider") or "")
    except Exception:
        provider = ""
    if provider.strip() == "codex_cli":
        # Best-effort: codex exec stdout JSONL (thread_id, usage incl cached_input_tokens).
        backend_kwargs.setdefault("trace", True)
        backend_kwargs.setdefault("trace_dir", os.path.join(run_dir, "_patches"))

    # Pass through retry/backoff tuning.
    backend_kwargs = {
        **backend_kwargs,
        "retry_max_attempts": int(args.retry_max_attempts),
        "retry_backoff_base_s": float(args.retry_backoff_base_s),
        "retry_backoff_max_s": float(args.retry_backoff_max_s),
        "retry_jitter_s": float(args.retry_jitter_s),
    }

    backend = LLMRouterBackend(**backend_kwargs)

    prompt = _build_prompt(
        run_dir=run_dir,
        cycle_summary_path=cycle_summary_path,
        cycle_summary=cycle_summary,
        sgd_report_path=str(sgd_report_path),
        sgd_report=sgd_report,
        worst_sessions=worst,
        worst_session_json_paths=worst_session_paths[: args.max_worst_sessions],
        context_mode=str(args.context_mode),
    )

    out_dir = os.path.join(run_dir, "_patches")
    os.makedirs(out_dir, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')
    chat_jsonl_path = os.path.join(out_dir, f"codex_chat_{ts}.jsonl")

    def _write_rate_limit_artifact(
        *,
        transcript_path: str,
        reset_s: Optional[int],
        reset_at_override: Optional[str] = None,
        reset_source: Optional[str] = None,
        provider_error_message: Optional[str] = None,
        will_retry: bool,
        sleep_s: Optional[int] = None,
        attempt_index: int = 0,
    ) -> str:
        now = datetime.now(timezone.utc)
        reset_at = None
        if isinstance(reset_at_override, str) and reset_at_override.strip():
            reset_at = reset_at_override.strip()
        elif isinstance(reset_s, int) and reset_s > 0:
            reset_at = (now + timedelta(seconds=int(reset_s))).isoformat()
        elif isinstance(sleep_s, int) and sleep_s > 0:
            # Fallback when Codex doesn't provide resets_in_seconds: record the wait window we chose.
            reset_at = (now + timedelta(seconds=int(sleep_s))).isoformat()

        payload = {
            "ts": now.isoformat(),
            "kind": "rate_limit",
            "provider": "codex_cli",
            "transcript_path": os.path.abspath(transcript_path),
            "provider_error_message": _truncate_for_log(provider_error_message, 2000),
            "resets_in_seconds": reset_s,
            "reset_at": reset_at,
            "reset_source": (str(reset_source) if reset_source else None),
            "provider_reset_at": (
                reset_at_override.strip() if isinstance(reset_at_override, str) and reset_at_override.strip() else None
            ),
            "will_retry": bool(will_retry),
            "sleep_seconds": sleep_s,
        }

        suffix = "" if int(attempt_index) <= 0 else f"_retry{int(attempt_index):02d}"
        path = os.path.join(out_dir, f"codex_rate_limit_{ts}{suffix}.json")
        _write_rate_limit_artifact_payload(path, payload)

        _append_jsonl_best_effort(
            transcript_path,
            {
                "event": "rate_limit",
                "ts": payload["ts"],
                "resets_in_seconds": reset_s,
                "reset_at": reset_at,
                "provider_error_message": payload.get("provider_error_message"),
                "will_retry": bool(will_retry),
                "sleep_seconds": sleep_s,
                "artifact_path": os.path.abspath(path),
            },
            event_name="rate-limit",
        )

        return path

    def _maybe_sleep_from_previous_rate_limit() -> None:
        if not bool(args.wait_on_429):
            return
        try:
            candidates = sorted(
                [p for p in os.listdir(out_dir) if p.startswith("codex_rate_limit_") and p.endswith(".json")]
            )
            if not candidates:
                return

            latest = os.path.join(out_dir, candidates[-1])
            with open(latest, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict) or data.get("will_retry") is not True:
                return

            now = datetime.now(timezone.utc)
            reset_at_raw = _pick_reset_at_raw_from_rate_limit_artifact(data)
            reset_at = None
            if isinstance(reset_at_raw, str) and reset_at_raw.strip():
                try:
                    reset_at = datetime.fromisoformat(reset_at_raw.strip())
                    if reset_at.tzinfo is None:
                        reset_at = reset_at.replace(tzinfo=timezone.utc)
                except Exception:
                    reset_at = None

            if reset_at is None:
                ts_raw = data.get("ts")
                sleep_raw = data.get("sleep_seconds")
                if isinstance(ts_raw, str) and isinstance(sleep_raw, (int, float)) and float(sleep_raw) > 0:
                    try:
                        started = datetime.fromisoformat(ts_raw.strip())
                        if started.tzinfo is None:
                            started = started.replace(tzinfo=timezone.utc)
                        reset_at = started + timedelta(seconds=int(float(sleep_raw)))
                    except Exception:
                        reset_at = None

            if reset_at is None:
                return

            remaining = (reset_at - now).total_seconds()
            if remaining <= 1:
                return

            buffer_s = max(0, int(args.wait_on_429_buffer_s))
            sleep_for = int(remaining) + buffer_s
            print(
                f"Codex usage-limit: resets_in_seconds={int(remaining)} reset_at={reset_at.isoformat()} "
                f"(wrote {os.path.abspath(latest)}); sleeping {sleep_for}s then retrying (attempt=resume)...",
                file=sys.stderr,
            )
            time.sleep(sleep_for)
        except Exception:
            return

    def _rate_limit_hint(
        *,
        reset_s: Optional[int],
        transcript_path: str,
        artifact_path: Optional[str] = None,
        reset_at: Optional[str] = None,
        provider_error_message: Optional[str] = None,
    ) -> str:
        hint = "Codex CLI rate/usage limit reached."
        if isinstance(reset_s, int) and reset_s > 0:
            mins = max(1, int(round(reset_s / 60.0)))
            hint += f" Try again in ~{mins} min (resets_in_seconds={reset_s})."
        elif isinstance(reset_at, str) and reset_at.strip():
            hint += f" Reset ETA: {reset_at.strip()}."
        else:
            hint += " Reset ETA unknown (no resets_in_seconds provided)."
        if bool(args.wait_on_429):
            hint += (
                " If you want to fail fast instead of waiting, pass: --no-wait-on-429"
            )
        hint += " You can reduce load and rerun with one or more of:"
        hint += (
            f" --retry-max-attempts {max(3, int(args.retry_max_attempts))}"
            f" --retry-backoff-base-s {max(0.5, float(args.retry_backoff_base_s))}"
            f" --retry-backoff-max-s {max(5.0, float(args.retry_backoff_max_s))}"
        )
        hint += (
            f" --context-mode lean"
            f" --max-steps {max(10, int(args.max_steps) // 2)}"
            f" --max-worst-sessions {max(1, int(args.max_worst_sessions) // 2)}"
        )
        hint += (
            "\nTranscript (including tool loop prompts) is saved at: "
            + os.path.abspath(transcript_path)
        )
        if isinstance(artifact_path, str) and artifact_path.strip():
            hint += "\nRate-limit metadata is saved at: " + os.path.abspath(artifact_path.strip())
        provider_msg_snip = _truncate_for_log(provider_error_message, 800)
        if provider_msg_snip:
            hint += "\nProvider error message: " + provider_msg_snip
        return hint

    patch_text: str
    attempt = 0
    current_chat_path = chat_jsonl_path

    _maybe_sleep_from_previous_rate_limit()
    while True:
        try:
            patch_text = _run_codex_with_tools_logged(
                backend=backend,
                base_prompt=prompt,
                max_steps=int(args.max_steps),
                chat_jsonl_path=current_chat_path,
            )
            break
        except Exception as e:
            msg = str(e or "")
            low = msg.lower()
            is_quota_exceeded = (
                "codex_error_kind=quota_exceeded" in low
                or "insufficient_quota" in low
                or "exceeded your current quota" in low
                or "quota has been exceeded" in low
                or "check your plan and billing" in low
                or ("billing" in low and "usage limit" not in low and "usage_limit" not in low)
            )
            is_rate_limit = (
                "usage_limit_reached" in low
                or ("http 429" in low)
                or ("too many requests" in low)
            )
            if not is_rate_limit and not is_quota_exceeded:
                raise

            exec_jsonl_path: Optional[str] = None
            try:
                exec_candidates = sorted(
                    [p for p in os.listdir(out_dir) if p.startswith("codex_exec_") and p.endswith(".jsonl")]
                )
                if exec_candidates:
                    exec_jsonl_path = os.path.join(out_dir, exec_candidates[-1])
            except Exception:
                exec_jsonl_path = None

            provider_error_message: Optional[str] = None
            if isinstance(exec_jsonl_path, str) and exec_jsonl_path.strip():
                provider_error_message = _extract_first_error_message_from_exec_jsonl(exec_jsonl_path.strip())

            # Enrich the exception string with provider text for better debugging/observability.
            if provider_error_message and provider_error_message not in msg:
                msg = msg + "\n" + provider_error_message

            reset_s, reset_at, reset_source = _extract_rate_limit_reset_info_with_exec_fallback(
                msg=msg,
                exec_jsonl_path=exec_jsonl_path,
            )

            if reset_source == "quota_exceeded" or is_quota_exceeded:
                artifact_path = _write_rate_limit_artifact(
                    transcript_path=current_chat_path,
                    reset_s=None,
                    reset_at_override=None,
                    reset_source="quota_exceeded",
                    provider_error_message=provider_error_message,
                    will_retry=False,
                    attempt_index=int(attempt),
                )
                provider_msg_snip = _truncate_for_log(provider_error_message, 800)
                print(
                    "Codex quota/billing limit exceeded (not retrying).\n"
                    + "Transcript (including tool loop prompts) is saved at: "
                    + os.path.abspath(current_chat_path)
                    + "\nMetadata is saved at: "
                    + os.path.abspath(artifact_path)
                    + ("\nProvider error message: " + provider_msg_snip if provider_msg_snip else ""),
                    file=sys.stderr,
                )
                return 2

            if (not bool(args.wait_on_429)) or (
                int(args.wait_on_429_max_retries) > 0 and attempt >= int(args.wait_on_429_max_retries)
            ):
                reset_at_override = reset_at.isoformat() if isinstance(reset_at, datetime) else None
                artifact_path = _write_rate_limit_artifact(
                    transcript_path=current_chat_path,
                    reset_s=reset_s,
                    reset_at_override=reset_at_override,
                    reset_source=reset_source,
                    provider_error_message=provider_error_message,
                    will_retry=False,
                    attempt_index=int(attempt),
                )
                print(
                    _rate_limit_hint(
                        reset_s=reset_s,
                        transcript_path=current_chat_path,
                        artifact_path=artifact_path,
                        reset_at=(reset_at_override or None),
                        provider_error_message=provider_error_message,
                    ),
                    file=sys.stderr,
                )
                return 2

            buffer_s = max(0, int(args.wait_on_429_buffer_s))
            fallback_base_s = max(1, int(args.wait_on_429_fallback_s))
            fallback_max_s = int(args.wait_on_429_fallback_max_s)
            if fallback_max_s <= 0:
                fallback_max_s = -1

            if isinstance(reset_s, int) and reset_s > 0:
                # Known reset window (from resets_in_seconds or derived from reset_at).
                sleep_s = int(reset_s) + buffer_s
            else:
                # Unknown reset timing: exponential backoff based on attempt count.
                sleep_s = int(fallback_base_s) * (2 ** int(attempt))
                if fallback_max_s > 0:
                    sleep_s = min(int(sleep_s), int(fallback_max_s))

            max_wait_s = int(args.wait_on_429_max_s)
            if max_wait_s <= 0:
                max_wait_s = -1
            if max_wait_s > 0 and sleep_s > max_wait_s:
                reset_at_override = reset_at.isoformat() if isinstance(reset_at, datetime) else None
                artifact_path = _write_rate_limit_artifact(
                    transcript_path=current_chat_path,
                    reset_s=reset_s,
                    reset_at_override=reset_at_override,
                    reset_source=reset_source,
                    provider_error_message=provider_error_message,
                    will_retry=False,
                    attempt_index=int(attempt),
                )
                print(
                    _rate_limit_hint(
                        reset_s=reset_s,
                        transcript_path=current_chat_path,
                        artifact_path=artifact_path,
                        reset_at=(reset_at_override or None),
                        provider_error_message=provider_error_message,
                    )
                    + f"\nNot waiting: resets_in_seconds+buffer={sleep_s} exceeds --wait-on-429-max-s={max_wait_s}.",
                    file=sys.stderr,
                )
                return 2

            reset_at_override = None
            if isinstance(reset_at, datetime):
                reset_at_override = reset_at.isoformat()
            artifact_path = _write_rate_limit_artifact(
                transcript_path=current_chat_path,
                reset_s=reset_s,
                reset_at_override=reset_at_override,
                reset_source=reset_source,
                provider_error_message=provider_error_message,
                will_retry=True,
                sleep_s=sleep_s,
                attempt_index=int(attempt),
            )
            reset_at_str = reset_at_override or (datetime.now(timezone.utc) + timedelta(seconds=int(sleep_s))).isoformat()
            next_attempt = int(attempt) + 1
            exc_snip = _truncate_for_log(msg, 500) or ""
            exc_part = f" exception=\"{exc_snip}\"" if exc_snip else ""
            print(
                f"Codex usage-limit: resets_in_seconds={reset_s} reset_at={reset_at_str}{exc_part} (wrote {os.path.abspath(artifact_path)}); sleeping {sleep_s}s then retrying (attempt={next_attempt})...",
                file=sys.stderr,
            )
            time.sleep(sleep_s)
            attempt += 1
            current_chat_path = os.path.join(out_dir, f"codex_chat_{ts}_retry{attempt:02d}.jsonl")

    out_path = os.path.join(
        out_dir,
        f"codex_patch_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.patch",
    )
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(patch_text)

    if bool(args.apply_patch):
        updated_files: List[str] = []
        original_text_by_file: Dict[str, str] = {}
        try:
            updated_files, original_text_by_file = _apply_patch_transaction(patch_text)
            _run_post_apply_checks(
                updated_files=updated_files,
                check_pycompile=bool(args.check_pycompile),
                check_pyright=bool(args.check_pyright),
                check_pytest=bool(args.check_pytest),
            )
        except Exception:
            if bool(args.undo_on_failure) and original_text_by_file:
                _restore_original_text(original_text_by_file)
            raise

    print(out_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
