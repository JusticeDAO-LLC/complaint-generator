import argparse
import ast
import base64
import difflib
import importlib.util
import json
import os
import re
import subprocess
import sys
import time
import glob
import tempfile
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

# Allow running via: python examples/codex_multi_run_autopatch.py
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from adversarial_harness import AdversarialHarness, Optimizer
from backends import LLMRouterBackend
from mediator import Mediator


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


def _load_session_sgd_report_module():
    path = os.path.join(PROJECT_ROOT, "examples", "session_sgd_report.py")
    spec = importlib.util.spec_from_file_location("session_sgd_report", path)
    if not spec or not spec.loader:
        raise RuntimeError(f"Unable to load session_sgd_report.py from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[attr-defined]
    return module


_sgd = _load_session_sgd_report_module()
_find_session_json_files = _sgd._find_session_json_files
_summarize_session = _sgd._summarize_session
_write_report = _sgd._write_report


def _utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def _ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def _run_batch_and_persist(
    *,
    config_path: str,
    backend_id: str,
    state_dir: str,
    run_id: str,
    num_sessions: int,
    max_turns: int,
    max_parallel: int,
    personalities: Optional[List[str]],
    retry_max_attempts: int,
    retry_backoff_base_s: float,
    retry_backoff_max_s: float,
    retry_jitter_s: float,
    session_trace: bool = False,
    session_cache_friendly: bool = False,
) -> str:
    config = _load_config(config_path)
    backend_kwargs = _get_llm_router_backend_config(config, backend_id)

    run_dir = os.path.join(state_dir, "_runs", run_id)
    _ensure_dir(run_dir)

    # Retry/backoff settings are passed through as kwargs.
    base_backend_kwargs: Dict[str, Any] = {
        **backend_kwargs,
        "retry_max_attempts": retry_max_attempts,
        "retry_backoff_base_s": retry_backoff_base_s,
        "retry_backoff_max_s": retry_backoff_max_s,
        "retry_jitter_s": retry_jitter_s,
    }

    if session_trace:
        base_backend_kwargs = {
            **base_backend_kwargs,
            "trace": True,
            "trace_dir": os.path.join(run_dir, "_sessions"),
        }

    llm_backend_complainant = LLMRouterBackend(**base_backend_kwargs)
    llm_backend_critic = LLMRouterBackend(**base_backend_kwargs)

    def _make_session_backend(*, role: str, session_id: str, session_dir: str | None) -> LLMRouterBackend:
        per_call_kwargs: Dict[str, Any] = dict(base_backend_kwargs)

        # Cache-friendly Copilot CLI mode:
        # - Use an isolated --config-dir per (session, role) so `--continue` reuses
        #   a stable session without contaminating other sessions.
        # - `ipfs_datasets_py.llm_router.generate_text` will retry once without
        #   --continue on the first turn if needed.
        if session_cache_friendly and session_dir:
            per_call_kwargs["copilot_config_dir"] = os.path.join(session_dir, "_copilot", role, "config")
            per_call_kwargs["continue_session"] = True

            # Keep Copilot logs nearby for debugging.
            per_call_kwargs.setdefault("copilot_log_dir", os.path.join(session_dir, "_copilot", role, "logs"))

        return LLMRouterBackend(**per_call_kwargs)

    complainant_factory = None
    critic_factory = None
    if session_cache_friendly:
        complainant_factory = lambda session_id, session_dir: _make_session_backend(
            role="complainant",
            session_id=session_id,
            session_dir=session_dir,
        )
        critic_factory = lambda session_id, session_dir: _make_session_backend(
            role="critic",
            session_id=session_id,
            session_dir=session_dir,
        )

    def mediator_factory(session_id: str | None = None, session_dir: str | None = None, **kwargs) -> Mediator:
        if session_cache_friendly and session_id and session_dir:
            backend = _make_session_backend(role="mediator", session_id=session_id, session_dir=session_dir)
        else:
            backend = LLMRouterBackend(**base_backend_kwargs)
        return Mediator(backends=[backend], **kwargs)

    harness = AdversarialHarness(
        llm_backend_complainant=llm_backend_complainant,
        llm_backend_critic=llm_backend_critic,
        mediator_factory=mediator_factory,
        max_parallel=max_parallel,
        session_state_dir=run_dir,
        llm_backend_complainant_factory=complainant_factory,
        llm_backend_critic_factory=critic_factory,
    )

    start = time.time()
    results = harness.run_batch(
        num_sessions=num_sessions,
        max_turns_per_session=max_turns,
        personalities=personalities,
    )
    duration_s = time.time() - start

    opt_report = Optimizer().analyze(results)
    optimizer_dict = opt_report.to_dict()

    session_json_files = _find_session_json_files(run_dir)
    summaries = [_summarize_session(p) for p in session_json_files]
    sgd_report_path = _write_report(run_dir, os.path.join(run_dir, "_reports"), summaries)

    sgd_report: Dict[str, Any] = {}
    try:
        sgd_report = _load_json(sgd_report_path)
    except Exception:
        sgd_report = {}

    graphs_health = None
    try:
        graphs_obj: Any = sgd_report.get("graphs")
        if isinstance(graphs_obj, dict):
            kg_obj = graphs_obj.get("knowledge_graph")
            dg_obj = graphs_obj.get("dependency_graph")
            kg: Dict[str, Any] = kg_obj if isinstance(kg_obj, dict) else {}
            dg: Dict[str, Any] = dg_obj if isinstance(dg_obj, dict) else {}
            graphs_health = (
                f"kg_files={kg.get('sessions_with_file')}/{sgd_report.get('num_sessions')} "
                f"kg_empty={kg.get('sessions_empty')}/{kg.get('sessions_with_file')} "
                f"dg_files={dg.get('sessions_with_file')}/{sgd_report.get('num_sessions')} "
                f"dg_empty={dg.get('sessions_empty')}/{dg.get('sessions_with_file')}"
            )
    except Exception:
        graphs_health = None

    graphs_dynamics_health = None
    try:
        def _fmt_delta(value: Any) -> str:
            if isinstance(value, (int, float)):
                return f"{value:+.2f}"
            return "n/a"

        kg_ent_d = optimizer_dict.get("kg_avg_entities_delta_per_iter")
        kg_rel_d = optimizer_dict.get("kg_avg_relationships_delta_per_iter")
        kg_gaps_d = optimizer_dict.get("kg_avg_gaps_delta_per_iter")
        kg_gaps_nondec = optimizer_dict.get("kg_sessions_gaps_not_reducing")

        if any(isinstance(v, (int, float)) for v in (kg_ent_d, kg_rel_d, kg_gaps_d)) or isinstance(
            kg_gaps_nondec, int
        ):
            denom = num_sessions if isinstance(num_sessions, int) and num_sessions > 0 else "n/a"
            nondec_s = kg_gaps_nondec if isinstance(kg_gaps_nondec, int) else "n/a"
            graphs_dynamics_health = (
                f"kg_entΔ={_fmt_delta(kg_ent_d)} "
                f"kg_relΔ={_fmt_delta(kg_rel_d)} "
                f"kg_gapsΔ={_fmt_delta(kg_gaps_d)} "
                f"kg_gaps_nondec={nondec_s}/{denom}"
            )
    except Exception:
        graphs_dynamics_health = None

    payload = {
        "run_id": run_id,
        "run_dir": os.path.abspath(run_dir),
        "config": {
            "backend_id": backend_id,
            "num_sessions": num_sessions,
            "max_turns": max_turns,
            "max_parallel": max_parallel,
            "personalities": personalities,
            "retry_max_attempts": retry_max_attempts,
            "retry_backoff_base_s": retry_backoff_base_s,
            "retry_backoff_max_s": retry_backoff_max_s,
            "retry_jitter_s": retry_jitter_s,
        },
        "timing": {
            "batch_duration_seconds": duration_s,
        },
        "optimizer_report": optimizer_dict,
        "sgd_report_path": os.path.abspath(sgd_report_path),
        "sgd_graphs": (sgd_report.get("graphs") if isinstance(sgd_report, dict) else None),
        "graphs_health": graphs_health,
        "graphs_dynamics_health": graphs_dynamics_health,
        "retry_stats": {
            "complainant": llm_backend_complainant.get_retry_stats(),
            "critic": llm_backend_critic.get_retry_stats(),
        },
    }

    out_path = os.path.join(run_dir, "cycle_summary.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    return run_dir


def _generate_codex_patch_for_run(
    *,
    python_exe: str,
    run_dir: str,
    config_path: str,
    backend_id: str,
    context_mode: str = "rich",
    wait_forever_on_429: bool = False,
    wait_on_429_fallback_s: Optional[int] = None,
    wait_on_429_fallback_max_s: Optional[int] = None,
) -> str:
    def _find_latest_rate_limit_artifact() -> Optional[str]:
        try:
            candidates = sorted(
                glob.glob(os.path.join(run_dir, "_patches", "codex_rate_limit_*.json"))
            )
        except Exception:
            candidates = []
        return candidates[-1] if candidates else None

    def _print_rate_limit_summary(path: str) -> None:
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            print(f"[codex] rate-limited (metadata unreadable): {path}")
            return

        reset_s = data.get("resets_in_seconds")
        reset_at = data.get("reset_at")
        sleep_s = data.get("sleep_seconds")
        will_retry = data.get("will_retry")
        parts = ["[codex] rate-limited"]
        if reset_s:
            parts.append(f"resets_in_seconds={reset_s}")
        if reset_at:
            parts.append(f"reset_at={reset_at}")
        if sleep_s:
            parts.append(f"sleep_seconds={sleep_s}")
        parts.append(f"will_retry={bool(will_retry)}")
        parts.append(f"artifact={os.path.abspath(path)}")
        print(" ".join(parts))

    def _run_streaming(cmd: List[str]) -> subprocess.CompletedProcess:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        assert proc.stdout is not None
        lines: List[str] = []
        saw_sleep_line = False
        for line in proc.stdout:
            # Stream child output live so users see sleep/backoff without waiting.
            sys.stdout.write(line)
            sys.stdout.flush()
            lines.append(line)
            if (not saw_sleep_line) and ("Codex usage-limit:" in line and "sleeping" in line):
                saw_sleep_line = True
                # Child line already includes reset_at + sleep seconds; add a parent-level marker.
                print("[codex] child entered sleep mode (rate limit)")

        rc = proc.wait()
        return subprocess.CompletedProcess(cmd, rc, "".join(lines), None)

    cmd = [
        python_exe,
        os.path.join(PROJECT_ROOT, "examples", "codex_autopatch_from_run.py"),
        "--config",
        config_path,
        "--backend-id",
        backend_id,
        "--run-dir",
        run_dir,
        "--context-mode",
        str(context_mode or "rich"),
        "--no-apply",
    ]
    if wait_forever_on_429:
        cmd += [
            "--wait-on-429",
            "--wait-on-429-max-s",
            "0",
            "--wait-on-429-max-retries",
            "0",
        ]
        if wait_on_429_fallback_s is not None:
            cmd += ["--wait-on-429-fallback-s", str(int(wait_on_429_fallback_s))]
        if wait_on_429_fallback_max_s is not None:
            cmd += ["--wait-on-429-fallback-max-s", str(int(wait_on_429_fallback_max_s))]

    proc = _run_streaming(cmd)
    if proc.returncode != 0:
        if proc.returncode == 2:
            artifact = _find_latest_rate_limit_artifact()
            if artifact:
                _print_rate_limit_summary(artifact)
            raise RuntimeError(
                "codex_autopatch_from_run rate-limited (exit=2). "
                + (f"See: {os.path.abspath(artifact)}\n" if artifact else "")
                + (proc.stdout or "")
            )
        raise RuntimeError(f"codex_autopatch_from_run failed (exit={proc.returncode}):\n{proc.stdout}")

    out = (proc.stdout or "").strip().splitlines()
    patch_path = out[-1].strip() if out else ""
    if not patch_path or not os.path.isfile(patch_path):
        raise RuntimeError(f"codex_autopatch_from_run did not output a valid patch path. Output:\n{proc.stdout}")
    return patch_path


@dataclass
class PatchApplyError(Exception):
    message: str
    file_path: Optional[str] = None
    hunk_index: Optional[int] = None
    details: Optional[Dict[str, Any]] = None

    def __str__(self) -> str:
        msg = self.message or ""
        extra: List[str] = []
        if self.file_path:
            extra.append(f"file={self.file_path}")
        if self.hunk_index is not None:
            extra.append(f"hunk={self.hunk_index}")
        if extra:
            return f"{msg} ({', '.join(extra)})".strip()
        return msg


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


def _select_context_slice_for_failure(
    *,
    file_text: str,
    failure_details: Optional[Dict[str, Any]],
    window_lines: int,
) -> Tuple[str, Optional[Dict[str, Any]]]:
    """Return (maybe_sliced_text, slice_meta).

    Uses failure_details['old_block'] as an anchor to find the best approximate
    location in the current file, then returns a bounded line slice around it.
    """
    file_lines = (file_text or "").splitlines()

    if window_lines <= 0:
        return file_text, {
            "start_line": 1,
            "end_line": len(file_lines),
            "total_lines": len(file_lines),
            "sliced": False,
            "mode": "full_file",
        }

    if len(file_lines) <= window_lines:
        return file_text, {"start_line": 1, "end_line": len(file_lines), "total_lines": len(file_lines), "sliced": False}

    old_block = []
    if failure_details and isinstance(failure_details.get("old_block"), list):
        old_block = [str(x) for x in (failure_details.get("old_block") or [])]

    # Pick a few distinctive anchor lines from the old block.
    anchors: List[str] = []
    for ln in old_block:
        s = ln.rstrip("\n")
        if not s.strip():
            continue
        if sum(ch.isalnum() for ch in s) < 8:
            continue
        if len(s.strip()) < 12:
            continue
        anchors.append(s.rstrip())
        if len(anchors) >= 6:
            break

    # Find best candidate index.
    best_idx: Optional[int] = None
    best_score = -1

    def score_at(idx: int) -> int:
        # Score by counting matching lines with rstrip() in a small lookahead.
        score = 0
        for j in range(min(12, len(old_block), len(file_lines) - idx)):
            if file_lines[idx + j].rstrip() == (old_block[j].rstrip() if j < len(old_block) else ""):
                score += 1
        return score

    # First: exact line matches.
    for a in anchors:
        for idx, fl in enumerate(file_lines):
            if fl.rstrip() == a:
                s = score_at(idx)
                if s > best_score:
                    best_score = s
                    best_idx = idx

    # Second: approximate (close) match to a single anchor line.
    if best_idx is None and anchors:
        for idx, fl in enumerate(file_lines):
            cand = fl.strip()
            if not cand:
                continue
            ratios = [difflib.SequenceMatcher(None, cand, a.strip()).ratio() for a in anchors]
            if not ratios:
                continue
            r = max(ratios)
            if r >= 0.88:
                s = score_at(idx)
                # Boost by ratio to break ties.
                boosted = int(s * 100 + r * 10)
                if boosted > best_score:
                    best_score = boosted
                    best_idx = idx

    if best_idx is None:
        # Fallback: keep full text if we cannot localize.
        return file_text, {"start_line": 1, "end_line": len(file_lines), "total_lines": len(file_lines), "sliced": False}

    half = max(20, window_lines // 2)
    start = max(0, best_idx - half)
    end = min(len(file_lines), start + window_lines)
    # Re-adjust start if we hit the end.
    start = max(0, end - window_lines)

    sliced_lines = file_lines[start:end]
    sliced_text = "\n".join(sliced_lines) + "\n"
    meta = {
        "start_line": start + 1,
        "end_line": end,
        "total_lines": len(file_lines),
        "sliced": True,
        "anchor_index": best_idx + 1,
    }
    return sliced_text, meta


def _expand_context_window_lines(*, base_window_lines: int, attempt: int, file_total_lines: int) -> int:
    """Increase context window on repeated failures.

    Returns 0 to indicate "full file" once the expanded window would cover the whole file.
    """
    if base_window_lines <= 0:
        return 0
    attempt = max(1, int(attempt or 1))
    expanded = base_window_lines * (2 ** (attempt - 1))
    if file_total_lines > 0 and expanded >= file_total_lines:
        return 0
    return int(expanded)


def _normalize_patch_text(text: str) -> str:
    """Normalize common Codex near-miss formats into apply_patch text."""
    text = (text or "").strip()
    if not text:
        return text

    # Drop fenced blocks like ```diff ... ```
    if text.startswith("```"):
        lines = text.splitlines()
        lines = lines[1:] if lines else []
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()

    # Normalize Begin Patch -> *** Begin Patch
    if text.startswith("Begin Patch"):
        text = "*** " + text

    # Normalize missing space: ***Begin Patch
    if text.startswith("***Begin Patch"):
        text = text.replace("***Begin Patch", "*** Begin Patch", 1)

    return text


def _parse_apply_patch(text: str) -> List[Tuple[str, List[List[str]]]]:
    """Parse apply_patch formatted text into [(file_path, [hunk_lines...])]."""
    text = _normalize_patch_text(text)
    lines = text.splitlines()
    # tolerate leading/trailing whitespace
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()

    if not lines or lines[0].strip() != "*** Begin Patch" or lines[-1].strip() != "*** End Patch":
        raise PatchApplyError("Not in apply_patch format")

    # Detect a common model formatting issue: every line is prefixed with exactly one extra space.
    # If present anywhere in the patch, we treat it as global for all hunks.
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
        # If the model prefixed *every* patch line with one extra space, we'll see patterns like:
        #  ' import logging' or '- import logging' or '+ import logging'
        # In that case we need to strip one leading space (or one space after +/-) on *all* lines,
        # including indented lines.
        def leading_space_count(s: str) -> int:
            n = 0
            for ch in s:
                if ch == " ":
                    n += 1
                else:
                    break
            return n

        def looks_like_unified_diff_prefix(ln: str) -> bool:
            if not ln:
                return False
            if ln.startswith(("*** ", "@@")):
                return False
            if ln[0] in "+-":
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
                # If indentation after +/- is off-by-one relative to 4-space blocks, strip one.
                if leading_space_count(ln[1:]) % 4 == 1:
                    out.append(ln[0] + ln[2:])
                    continue

            if ln.startswith(" "):
                if leading_space_count(ln) % 4 == 1:
                    out.append(ln[1:])
                    continue

            out.append(ln)

        return out

    def flush_file():
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
            raise PatchApplyError("Only '*** Update File' patches are supported by this script")
        if line.startswith("@@"):
            if current_file is None:
                i += 1
                continue
            if current_hunk is not None and current_hunk:
                current_hunks.append(normalize_hunk_lines(current_hunk))
            current_hunk = []
            i += 1
            continue

        # normal patch/content line
        if current_file is not None:
            if current_hunk is None:
                current_hunk = []
            # skip purely blank separators between hunks
            current_hunk.append(line)
        i += 1

    flush_file()
    # Allow a no-op patch (Begin/End Patch with no file blocks). This can happen
    # when Codex determines the requested change is already present.
    return file_blocks


def _find_subsequence(haystack: Sequence[str], needle: Sequence[str], start_at: int = 0) -> Optional[int]:
    if not needle:
        return None
    max_i = len(haystack) - len(needle)
    for i in range(start_at, max_i + 1):
        if list(haystack[i : i + len(needle)]) == list(needle):
            return i
    return None


def _find_subsequence_rstrip(haystack: Sequence[str], needle: Sequence[str], start_at: int = 0) -> Optional[int]:
    """Fallback matching that ignores trailing whitespace differences."""
    if not needle:
        return None
    hay = [h.rstrip() for h in haystack]
    ned = [n.rstrip() for n in needle]
    max_i = len(hay) - len(ned)
    for i in range(start_at, max_i + 1):
        if hay[i : i + len(ned)] == ned:
            return i
    return None


def _find_subsequence_relaxed_indent(haystack: Sequence[str], needle: Sequence[str], start_at: int = 0) -> Optional[int]:
    """Conservative fallback matching that ignores leading indentation differences.

    Only succeeds when there is exactly ONE matching location (from start_at), to
    reduce the risk of applying a hunk to the wrong region.
    """

    if not needle:
        return None

    hay = [h.strip() for h in haystack]
    ned = [n.strip() for n in needle]
    max_i = len(hay) - len(ned)
    matches: List[int] = []
    for i in range(start_at, max_i + 1):
        if list(hay[i : i + len(ned)]) == list(ned):
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
        # Keep details small but actionable for Codex repair prompts.
        def clip(lines: List[str], limit: int = 80) -> List[str]:
            if len(lines) <= limit:
                return lines
            return lines[:limit] + ["...<clipped>..."]

        raise PatchApplyError(
            "Hunk context not found",
            details={
                "old_block": clip(old_block),
                "new_block": clip(new_block),
                "hunk_lines": clip(list(hunk_lines)),
            },
        )

    return file_lines[:pos] + new_block + file_lines[pos + len(old_block) :]


def _dry_run_apply_patch_text(patch_text: str) -> None:
    """Validate that a patch can apply cleanly to current working tree.

    Raises PatchApplyError if it cannot be applied.
    """
    patch_text = _normalize_patch_text(patch_text)
    file_blocks = _parse_apply_patch(patch_text)

    # No-op patches are valid.
    if not file_blocks:
        return

    for file_path, hunks in file_blocks:
        if not os.path.isabs(file_path):
            raise PatchApplyError("Patch paths must be absolute", file_path=file_path)
        if not os.path.isfile(file_path):
            raise PatchApplyError("Target file does not exist", file_path=file_path)

        with open(file_path, "r", encoding="utf-8") as f:
            file_lines = f.read().splitlines()

        for hunk_index, hunk_lines in enumerate(hunks):
            try:
                file_lines = _apply_hunk_to_lines(file_lines, hunk_lines)
            except PatchApplyError as e:
                raise PatchApplyError(e.message, file_path=file_path, hunk_index=hunk_index, details=e.details) from e

        _validate_python_syntax(file_path, file_lines)


def _apply_patch_transaction(patch_text: str) -> Tuple[List[str], Dict[str, str]]:
    """Apply patch in-memory across all files first, then write.

    Returns (updated_files, original_contents_by_file) on success.
    """
    patch_text = _normalize_patch_text(patch_text)
    file_blocks = _parse_apply_patch(patch_text)
    if not file_blocks:
        return ([], {})

    # Load all file contents upfront so we can write atomically per patch.
    original_text_by_file: Dict[str, str] = {}
    updated_lines_by_file: Dict[str, List[str]] = {}

    for file_path, _ in file_blocks:
        if not os.path.isabs(file_path):
            raise PatchApplyError("Patch paths must be absolute", file_path=file_path)
        if not os.path.isfile(file_path):
            raise PatchApplyError("Target file does not exist", file_path=file_path)
        if file_path not in original_text_by_file:
            original_text_by_file[file_path] = _read_text(file_path)
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

    # Write all updated files at the end.
    for file_path in updated_files:
        with open(file_path, "w", encoding="utf-8") as f:
            f.write("\n".join(updated_lines_by_file[file_path]) + "\n")

    return (updated_files, original_text_by_file)


def apply_apply_patch_text(patch_text: str) -> List[str]:
    """Apply an apply_patch formatted patch to the working tree.

    Returns list of updated file paths.
    """
    updated, _original = _apply_patch_transaction(patch_text)
    return updated


def _project_relative_path(abs_path: str) -> str:
    try:
        rel = os.path.relpath(abs_path, PROJECT_ROOT)
    except Exception:
        rel = abs_path.lstrip(os.sep)
    if rel.startswith(".."):
        return abs_path.lstrip(os.sep)
    return rel


def _write_undo_record(undo_dir: str, patch_name: str, original_text_by_file: Dict[str, str], updated_files: List[str]) -> str:
    _ensure_dir(undo_dir)
    payload = {
        "patch": patch_name,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "files": {
            path: {
                "relative": _project_relative_path(path),
                "original_b64": base64.b64encode(text.encode("utf-8")).decode("ascii"),
            }
            for path, text in original_text_by_file.items()
        },
        "updated_files": updated_files,
    }
    out_path = os.path.join(undo_dir, f"{patch_name}.undo.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    return out_path


def _restore_undo_record(undo_record_path: str) -> List[str]:
    payload = _load_json(undo_record_path)
    files = payload.get("files", {})
    restored: List[str] = []
    for abs_path, meta in files.items():
        original_b64 = (meta or {}).get("original_b64")
        if not original_b64:
            continue
        text = base64.b64decode(original_b64.encode("ascii")).decode("utf-8")
        _ensure_dir(os.path.dirname(abs_path))
        with open(abs_path, "w", encoding="utf-8") as f:
            f.write(text)
        restored.append(abs_path)
    return restored


def _extract_update_files(patch_text: str) -> List[str]:
    files: List[str] = []
    for line in patch_text.splitlines():
        if line.startswith("*** Update File:"):
            files.append(line.split(":", 1)[1].strip())
    return files


def _codex_fix_patch(
    *,
    codex_backend: LLMRouterBackend,
    failing_patch_text: str,
    error_message: str,
    file_contents: Dict[str, str],
    failure_details: Optional[Dict[str, Any]] = None,
) -> str:
    context = {
        "error": error_message,
        "failure_details": failure_details,
        "files": {path: contents for path, contents in file_contents.items()},
        "previous_patch": failing_patch_text,
    }

    prompt = (
        "You are Codex CLI. You must output ONLY an apply_patch formatted patch.\n\n"
        "Task: Fix the patch so it applies cleanly to the CURRENT file contents provided.\n"
        "Rules:\n"
        "- Output MUST start with: *** Begin Patch\n"
        "- Output MUST end with: *** End Patch\n"
        "- Use only: *** Update File: <absolute path> (no Add File / Delete File)\n"
        "- Do NOT emit unified-diff prefixes (no leading ' ' marker on unchanged lines).\n"
        "- You MAY use '@@' only as a hunk separator/scope hint; do NOT use '@@' or '...' as placeholders.\n"
        "- Do not use placeholder paths or template lines.\n"
        "- Keep the change minimal; preserve intent of the previous patch.\n\n"
        "Patch quality requirements:\n"
        "- Do not truncate or corrupt lines (no partial tokens).\n"
        "- Ensure every changed region includes enough exact context lines to apply.\n"
        "- Keep hunks small and focused; avoid huge hunks spanning multiple functions.\n\n"
        "If the failure_details include an old_block that could not be found, rebase your patch: locate the intended code in the CURRENT file and rewrite the hunk context so it matches exactly.\n\n"
        "Note: Some file contents may be truncated to a line slice; if failure_details.file_context is present, use those line ranges as the authoritative view for rebasing hunks.\n\n"
        "Here is the failure context as JSON (includes current file contents):\n"
        + json.dumps(context, ensure_ascii=False)
    )

    fixed = codex_backend(prompt)
    return _normalize_patch_text(str(fixed))


def _read_text(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _atomic_write_json(path: str, payload: Dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(prefix=os.path.basename(path) + ".", dir=os.path.dirname(path) or ".")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
            f.write("\n")
        os.replace(tmp_path, path)
    finally:
        try:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
        except OSError:
            pass


def _load_json_or_none(path: str) -> Optional[Dict[str, Any]]:
    """Load an optional JSON object, returning ``None`` only when it is absent."""

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        return None

    if not isinstance(data, dict):
        raise ValueError(
            f"Expected a JSON object in {path!r}, got {type(data).__name__}"
        )
    return data


_STAGE_ORDER: Dict[str, int] = {
    "batch": 10,
    "batch_done": 20,
    "patch": 30,
    "patch_saved": 40,
    "apply": 50,
    "apply_done": 60,
    "pytest": 70,
    "pytest_done": 80,
    "run_done": 90,
    "done": 100,
}


def _maybe_advance_stage(progress: Dict[str, Any], new_stage: str) -> None:
    cur = progress.get("current_stage")
    if isinstance(cur, str):
        if _STAGE_ORDER.get(cur, -1) >= _STAGE_ORDER.get(new_stage, -1):
            return
    progress["current_stage"] = new_stage


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Run multiple adversarial batches, generate Codex patches per run, then apply all patches with auto-fix retries"
        )
    )
    parser.add_argument("--config", default="config.llm_router.json")
    parser.add_argument("--state-dir", default="statefiles")
    parser.add_argument("--batch-backend-id", default=None, help="Backend id for running sessions (defaults to config.MEDIATOR.backends[0])")
    parser.add_argument("--codex-backend-id", default="llm-router-codex")
    parser.add_argument(
        "--codex-context-mode",
        choices=["rich", "lean"],
        default="rich",
        help="Pass through to codex_autopatch_from_run.py to reduce prompt tokens (lean relies on tool reads)",
    )
    parser.add_argument(
        "--codex-wait-forever-on-429",
        action="store_true",
        help=(
            "When calling codex_autopatch_from_run.py, wait indefinitely through rate limiting "
            "(sleep+retry until success) instead of exiting with code 2."
        ),
    )
    parser.add_argument(
        "--codex-wait-on-429-fallback-s",
        type=int,
        default=None,
        help=(
            "Pass through to codex_autopatch_from_run.py as --wait-on-429-fallback-s (only relevant with "
            "--codex-wait-forever-on-429). If omitted, uses the driver default."
        ),
    )
    parser.add_argument(
        "--codex-wait-on-429-fallback-max-s",
        type=int,
        default=None,
        help=(
            "Pass through to codex_autopatch_from_run.py as --wait-on-429-fallback-max-s (only relevant with "
            "--codex-wait-forever-on-429). If omitted, uses the driver default."
        ),
    )
    parser.add_argument("--runs", type=int, default=10)
    parser.add_argument("--sessions-per-run", type=int, default=10)
    parser.add_argument("--max-turns", type=int, default=8)
    parser.add_argument("--max-parallel", type=int, default=2)
    parser.add_argument("--personalities", default=None)

    parser.add_argument(
        "--session-trace",
        action="store_true",
        help="Enable per-call LLM traces for mediator sessions (useful to observe cached_input_tokens with codex_cli).",
    )

    parser.add_argument(
        "--session-cache-friendly",
        action="store_true",
        help=(
            "Enable a Copilot CLI cache-friendly mode by isolating each session into its own Copilot --config-dir and using --continue. "
            "This reduces prompt-prefix churn across turns without leaking state across parallel sessions."
        ),
    )

    parser.add_argument("--retry-max-attempts", type=int, default=1)
    parser.add_argument("--retry-backoff-base-s", type=float, default=0.5)
    parser.add_argument("--retry-backoff-max-s", type=float, default=20.0)
    parser.add_argument("--retry-jitter-s", type=float, default=0.1)

    parser.add_argument("--apply-fix-max-attempts", type=int, default=2)
    parser.add_argument(
        "--generate-fix-max-attempts",
        type=int,
        default=2,
        help="If Codex generates a patch that can't apply to the current tree, ask Codex to fix it up to this many times.",
    )
    parser.add_argument(
        "--undo-on-test-failure",
        action="store_true",
        help="If pytest fails at the end, undo all applied patches from this run before exiting.",
    )

    parser.set_defaults(pytest_after_each_run=True)
    parser.add_argument(
        "--pytest-after-each-run",
        dest="pytest_after_each_run",
        action="store_true",
        help="Run pytest -q after each run's patch is applied (default).",
    )
    parser.add_argument(
        "--no-pytest-after-each-run",
        dest="pytest_after_each_run",
        action="store_false",
        help="Disable running pytest after each run.",
    )

    parser.set_defaults(undo_last_on_pytest_fail=True)
    parser.add_argument(
        "--undo-last-on-pytest-fail",
        dest="undo_last_on_pytest_fail",
        action="store_true",
        help="If pytest fails after applying a patch, undo only that patch and continue (default).",
    )
    parser.add_argument(
        "--no-undo-last-on-pytest-fail",
        dest="undo_last_on_pytest_fail",
        action="store_false",
        help="If pytest fails after applying a patch, keep the patch applied.",
    )

    parser.add_argument(
        "--stop-on-pytest-fail",
        action="store_true",
        help="Stop immediately if pytest fails after a run.",
    )
    parser.add_argument(
        "--fix-context-window-lines",
        type=int,
        default=240,
        help=(
            "When asking Codex to fix a failing/out-of-date patch, include only a slice of the failing file around the best anchor match. "
            "Set to 0 to always send full files."
        ),
    )
    parser.add_argument(
        "--undo-dir",
        default=None,
        help="Directory to store undo records (defaults to <orchestrator_dir>/undo)",
    )

    parser.add_argument(
        "--orchestrator-id",
        default=None,
        help=(
            "Optional stable id for this orchestrator run (enables resume). "
            "Artifacts are written under <state-dir>/_runs/<orchestrator-id>."
        ),
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help=(
            "Resume an existing orchestrator run using --orchestrator-id and its progress.json. "
            "Skips already-completed runs/stages when possible."
        ),
    )
    parser.add_argument(
        "--start-at",
        type=int,
        default=None,
        help="Start (or resume) at a specific run index i (0-based). Overrides progress.json.",
    )
    args = parser.parse_args()

    personalities = None
    if args.personalities:
        personalities = [p.strip() for p in args.personalities.split(",") if p.strip()]

    config = _load_config(args.config)
    batch_backend_id = args.batch_backend_id
    if not batch_backend_id:
        backend_ids = config.get("MEDIATOR", {}).get("backends", [])
        batch_backend_id = backend_ids[0] if backend_ids else None
    if not batch_backend_id:
        raise SystemExit("No batch backend id available")

    orchestrator_id = str(args.orchestrator_id or f"autopatch_{_utc_stamp()}")
    orchestrator_dir = os.path.join(args.state_dir, "_runs", orchestrator_id)
    if bool(args.resume) and not os.path.isdir(orchestrator_dir):
        raise SystemExit(f"--resume was set but orchestrator dir does not exist: {orchestrator_dir}")
    _ensure_dir(orchestrator_dir)

    progress_path = os.path.join(orchestrator_dir, "progress.json")
    progress = _load_json_or_none(progress_path) or {}

    start_i = 0
    if isinstance(args.start_at, int) and args.start_at >= 0:
        start_i = int(args.start_at)
    elif bool(args.resume):
        nxt = progress.get("next_run_index")
        if isinstance(nxt, int) and nxt >= 0:
            start_i = int(nxt)

    progress = {
        **progress,
        "orchestrator_id": orchestrator_id,
        "orchestrator_dir": os.path.abspath(orchestrator_dir),
        "runs_total": int(args.runs),
        "next_run_index": int(start_i),
        "status": "running",
        "ts": datetime.now(timezone.utc).isoformat(),
    }
    _atomic_write_json(progress_path, progress)

    patches_dir = os.path.join(orchestrator_dir, "patches")
    fixed_dir = os.path.join(orchestrator_dir, "patches_fixed")
    undo_dir = args.undo_dir or os.path.join(orchestrator_dir, "undo")
    _ensure_dir(patches_dir)
    _ensure_dir(fixed_dir)
    _ensure_dir(undo_dir)

    python_exe = sys.executable

    # Codex backend used for patch-fix retries (uses llm-router config for codex backend).
    codex_backend_kwargs = _get_llm_router_backend_config(config, args.codex_backend_id)
    codex_backend = LLMRouterBackend(**codex_backend_kwargs)

    run_records: List[Dict[str, Any]] = []
    applied: List[Dict[str, Any]] = []
    undo_records: List[str] = []
    per_run_tests: List[Dict[str, Any]] = []

    try:
        for i in range(int(start_i), int(args.runs)):
            run_id = f"{orchestrator_id}_run_{i:02d}"
            print(f"[batch] {i+1}/{args.runs} run_id={run_id}")

            prev_run_index = progress.get("current_run_index")
            prev_stage = progress.get("current_stage") if isinstance(progress.get("current_stage"), str) else None
            resuming_same_run = bool(args.resume) and prev_run_index == int(i) and bool(prev_stage)
            start_stage = prev_stage if resuming_same_run else "batch"

            progress.update(
                {
                    "ts": datetime.now(timezone.utc).isoformat(),
                    "current_run_index": int(i),
                    "current_run_id": run_id,
                    "current_stage": start_stage,
                    "next_run_index": int(i),
                }
            )
            _atomic_write_json(progress_path, progress)

            run_dir = os.path.join(args.state_dir, "_runs", run_id)
            cycle_summary_path = os.path.join(run_dir, "cycle_summary.json")
            if os.path.isfile(cycle_summary_path):
                run_dir = os.path.abspath(run_dir)
                print(f"[batch] skip (already exists) run_dir={run_dir}")
            else:
                run_dir = _run_batch_and_persist(
                    config_path=args.config,
                    backend_id=batch_backend_id,
                    state_dir=args.state_dir,
                    run_id=run_id,
                    num_sessions=args.sessions_per_run,
                    max_turns=args.max_turns,
                    max_parallel=args.max_parallel,
                    personalities=personalities,
                    retry_max_attempts=args.retry_max_attempts,
                    retry_backoff_base_s=args.retry_backoff_base_s,
                    retry_backoff_max_s=args.retry_backoff_max_s,
                    retry_jitter_s=args.retry_jitter_s,
                    session_trace=bool(args.session_trace),
                    session_cache_friendly=bool(args.session_cache_friendly),
                )

            if not resuming_same_run or start_stage in {"batch", "batch_done"}:
                progress.update(
                    {
                        "ts": datetime.now(timezone.utc).isoformat(),
                        "current_stage": "batch_done",
                        "current_run_dir": os.path.abspath(run_dir),
                    }
                )
            else:
                progress.update(
                    {
                        "ts": datetime.now(timezone.utc).isoformat(),
                        "current_run_dir": os.path.abspath(run_dir),
                    }
                )
            _atomic_write_json(progress_path, progress)

            rec: Dict[str, Any] = {
                "i": i,
                "run_id": run_id,
                "run_dir": os.path.abspath(run_dir),
            }

            try:
                # If we're resuming and the prior state already indicates this run is finished,
                # fast-forward to the next run index.
                if resuming_same_run and isinstance(prev_stage, str) and prev_stage in {"run_done", "done"}:
                    print(f"[run] skip (resume complete) run_id={run_id} stage={prev_stage}")
                    run_records.append({**rec, "resumed_complete": True, "resumed_stage": prev_stage})
                    progress.update(
                        {
                            "ts": datetime.now(timezone.utc).isoformat(),
                            "next_run_index": int(i) + 1,
                        }
                    )
                    _maybe_advance_stage(progress, "run_done")
                    _atomic_write_json(progress_path, progress)
                    continue

                if not resuming_same_run or start_stage in {"batch", "batch_done", "patch"}:
                    progress.update(
                        {
                            "ts": datetime.now(timezone.utc).isoformat(),
                            "current_stage": "patch",
                        }
                    )
                else:
                    progress.update({"ts": datetime.now(timezone.utc).isoformat()})
                _atomic_write_json(progress_path, progress)

                local_patch_path = os.path.join(patches_dir, f"patch_{i:02d}.patch")
                if os.path.isfile(local_patch_path):
                    patch_text = _normalize_patch_text(_read_text(local_patch_path))
                    rec["patch_path"] = os.path.abspath(local_patch_path)
                    print(f"[patch] skip (already exists) patch={os.path.basename(local_patch_path)}")
                else:
                    patch_path = _generate_codex_patch_for_run(
                        python_exe=python_exe,
                        run_dir=run_dir,
                        config_path=args.config,
                        backend_id=args.codex_backend_id,
                        context_mode=str(args.codex_context_mode),
                        wait_forever_on_429=bool(args.codex_wait_forever_on_429),
                        wait_on_429_fallback_s=args.codex_wait_on_429_fallback_s,
                        wait_on_429_fallback_max_s=args.codex_wait_on_429_fallback_max_s,
                    )
                    patch_text = _normalize_patch_text(_read_text(patch_path))

                # If resuming at/after apply_done, the saved patch is expected to no longer
                # dry-run apply (because it may already be applied). Skip validation/fix.
                resume_stage_order = (
                    _STAGE_ORDER.get(str(prev_stage), -1) if (resuming_same_run and isinstance(prev_stage, str)) else -1
                )
                if resume_stage_order >= _STAGE_ORDER.get("apply_done", 60):
                    print(f"[patch] resume: skipping dry-run validation (stage={prev_stage})")
                else:
                    # Validate (dry-run apply) immediately; if Codex produced a broken patch, repair it now.
                    gen_attempt = 0
                    while True:
                        gen_attempt += 1
                        try:
                            _dry_run_apply_patch_text(patch_text)
                            break
                        except PatchApplyError as e:
                            if gen_attempt > args.generate_fix_max_attempts:
                                raise PatchApplyError(
                                    f"Generated patch failed dry-run apply after fixes: {e}",
                                    file_path=e.file_path,
                                    hunk_index=e.hunk_index,
                                ) from e

                            update_files = _extract_update_files(patch_text)
                            file_contents: Dict[str, str] = {}
                            for fp in update_files:
                                if os.path.isfile(fp):
                                    file_contents[fp] = _read_text(fp)
                            if e.file_path and os.path.isfile(e.file_path):
                                full_text = _read_text(e.file_path)
                                total_lines = len((full_text or "").splitlines())
                                window_lines = _expand_context_window_lines(
                                    base_window_lines=args.fix_context_window_lines,
                                    attempt=gen_attempt,
                                    file_total_lines=total_lines,
                                )
                                sliced_text, slice_meta = _select_context_slice_for_failure(
                                    file_text=full_text,
                                    failure_details=e.details,
                                    window_lines=window_lines,
                                )
                                file_contents.setdefault(e.file_path, sliced_text)
                                if e.details is not None and slice_meta is not None:
                                    e.details = {**e.details, "file_context": slice_meta}

                            patch_text = _codex_fix_patch(
                                codex_backend=codex_backend,
                                failing_patch_text=patch_text,
                                error_message=f"Generated patch failed dry-run apply: {e}",
                                file_contents=file_contents,
                                failure_details=e.details,
                            )

                # Copy patch into orchestrator folder for traceability.
                _ensure_dir(patches_dir)
                with open(local_patch_path, "w", encoding="utf-8") as f:
                    f.write(patch_text)
                rec["patch_path"] = os.path.abspath(local_patch_path)

                progress.update(
                    {
                        "ts": datetime.now(timezone.utc).isoformat(),
                        "current_patch_path": rec.get("patch_path"),
                    }
                )
                _maybe_advance_stage(progress, "patch_saved")
                _atomic_write_json(progress_path, progress)

                # Apply immediately so later patches are generated against the updated tree.
                # If resuming mid-run and we already recorded apply_done, avoid double-applying.
                resuming_same_run = bool(args.resume) and progress.get("current_run_index") == int(i)
                if resuming_same_run and progress.get("current_stage") in {"apply_done", "pytest", "pytest_done"}:
                    print(f"[apply] skip (resume) patch={os.path.basename(local_patch_path)}")
                    rec["patch_applied"] = True
                else:
                    progress.update(
                        {
                            "ts": datetime.now(timezone.utc).isoformat(),
                        }
                    )
                    _maybe_advance_stage(progress, "apply")
                    _atomic_write_json(progress_path, progress)

                    patch_name = os.path.basename(local_patch_path).replace(".patch", "")
                    apply_attempt = 0
                    while True:
                        apply_attempt += 1
                        try:
                            updated, original = _apply_patch_transaction(patch_text)

                            undo_record_path = ""
                            if updated:
                                undo_record_path = _write_undo_record(undo_dir, patch_name, original, updated)
                                undo_records.append(undo_record_path)
                            applied.append(
                                {
                                    "patch_path": rec["patch_path"],
                                    "attempt": apply_attempt,
                                    "updated_files": updated,
                                    "fixed": apply_attempt > 1,
                                    "undo_record": undo_record_path or None,
                                }
                            )
                            print(
                                f"[apply] ok patch={os.path.basename(local_patch_path)} updated={len(updated)}"
                            )
                            rec["patch_applied"] = True

                            progress.update(
                                {
                                    "ts": datetime.now(timezone.utc).isoformat(),
                                }
                            )
                            _maybe_advance_stage(progress, "apply_done")
                            _atomic_write_json(progress_path, progress)
                            break
                        except PatchApplyError as e:
                            if apply_attempt > args.apply_fix_max_attempts + 1:
                                applied.append(
                                    {
                                        "patch_path": rec["patch_path"],
                                        "attempt": apply_attempt,
                                        "error": str(e),
                                        "fixed": True,
                                        "failed": True,
                                    }
                                )
                                print(
                                    f"[apply] FAIL patch={os.path.basename(local_patch_path)} error={e}"
                                )
                                rec["patch_applied"] = False
                                rec["patch_apply_error"] = str(e)
                                break

                            update_files = _extract_update_files(patch_text)
                            file_contents: Dict[str, str] = {}
                            for fp in update_files:
                                if os.path.isfile(fp):
                                    file_contents[fp] = _read_text(fp)
                            if e.file_path and os.path.isfile(e.file_path):
                                full_text = _read_text(e.file_path)
                                total_lines = len((full_text or "").splitlines())
                                window_lines = _expand_context_window_lines(
                                    base_window_lines=args.fix_context_window_lines,
                                    attempt=apply_attempt,
                                    file_total_lines=total_lines,
                                )
                                sliced_text, slice_meta = _select_context_slice_for_failure(
                                    file_text=full_text,
                                    failure_details=e.details,
                                    window_lines=window_lines,
                                )
                                file_contents.setdefault(e.file_path, sliced_text)
                                if e.details is not None and slice_meta is not None:
                                    e.details = {**e.details, "file_context": slice_meta}

                            patch_text = _codex_fix_patch(
                                codex_backend=codex_backend,
                                failing_patch_text=patch_text,
                                error_message=str(e),
                                file_contents=file_contents,
                                failure_details=e.details,
                            )

                            fixed_out_path = os.path.join(
                                fixed_dir,
                                f"fixed_{os.path.basename(local_patch_path).replace('.patch','')}_attempt_{apply_attempt}.patch",
                            )
                            with open(fixed_out_path, "w", encoding="utf-8") as f2:
                                f2.write(patch_text)
                            with open(local_patch_path, "w", encoding="utf-8") as f3:
                                f3.write(patch_text)

                progress.update(
                    {
                        "ts": datetime.now(timezone.utc).isoformat(),
                    }
                )
                _maybe_advance_stage(progress, "pytest" if args.pytest_after_each_run else "run_done")
                _atomic_write_json(progress_path, progress)

                # Run pytest after each run (batch of sessions) by default.
                if args.pytest_after_each_run:
                    test_start = time.time()
                    test_proc = subprocess.run(
                        [python_exe, "-m", "pytest", "-q"],
                        cwd=PROJECT_ROOT,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT,
                        text=True,
                    )
                    out_lines = (test_proc.stdout or "").splitlines()
                    per_run_tests.append(
                        {
                            "run_id": run_id,
                            "patch_path": rec.get("patch_path"),
                            "exit_code": test_proc.returncode,
                            "duration_seconds": time.time() - test_start,
                            "output_tail": out_lines[-60:],
                        }
                    )
                    rec["pytest_after_run_exit_code"] = test_proc.returncode

                    progress.update(
                        {
                            "ts": datetime.now(timezone.utc).isoformat(),
                            "last_pytest_exit": int(test_proc.returncode),
                        }
                    )
                    _maybe_advance_stage(progress, "pytest_done")
                    _atomic_write_json(progress_path, progress)

                    if test_proc.returncode != 0:
                        print(f"[test] FAIL run_id={run_id} exit={test_proc.returncode}")
                        if args.undo_last_on_pytest_fail and undo_records:
                            last_undo = undo_records.pop()
                            print(f"[undo] restoring last patch via {os.path.basename(last_undo)}")
                            _restore_undo_record(last_undo)
                            if applied:
                                applied[-1]["rolled_back"] = True
                            rec["rolled_back"] = True

                            # Verify rollback restored a passing state.
                            verify_proc = subprocess.run(
                                [python_exe, "-m", "pytest", "-q"],
                                cwd=PROJECT_ROOT,
                                stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT,
                                text=True,
                            )
                            verify_lines = (verify_proc.stdout or "").splitlines()
                            per_run_tests.append(
                                {
                                    "run_id": run_id,
                                    "patch_path": rec.get("patch_path"),
                                    "exit_code": verify_proc.returncode,
                                    "duration_seconds": None,
                                    "output_tail": verify_lines[-60:],
                                    "note": "post_rollback_verify",
                                }
                            )
                            if verify_proc.returncode != 0:
                                print(
                                    f"[test] STILL FAIL after rollback run_id={run_id} exit={verify_proc.returncode}"
                                )
                                rec["pytest_after_rollback_exit_code"] = verify_proc.returncode
                                if args.stop_on_pytest_fail:
                                    rec["stopped_on_pytest_fail"] = True
                                    raise RuntimeError(
                                        "Stopping due to pytest failure even after rollback"
                                    )
                        if args.stop_on_pytest_fail:
                            rec["stopped_on_pytest_fail"] = True
                            raise RuntimeError("Stopping due to pytest failure after run")
                    else:
                        print(f"[test] ok run_id={run_id}")

            except Exception as e:
                print(f"[patch] SKIP run_id={run_id} error={e}")
                rec["patch_error"] = str(e)

            run_records.append(rec)
            progress.update(
                {
                    "ts": datetime.now(timezone.utc).isoformat(),
                    "next_run_index": int(i) + 1,
                }
            )
            _maybe_advance_stage(progress, "run_done")
            _atomic_write_json(progress_path, progress)
    except KeyboardInterrupt:
        print("[orchestrator] interrupted")
        progress.update(
            {
                "ts": datetime.now(timezone.utc).isoformat(),
                "status": "interrupted",
            }
        )
        _atomic_write_json(progress_path, progress)
        raise

    if args.resume and int(start_i) >= int(args.runs):
        summary_path = progress.get("summary_path")
        if progress.get("status") == "done" and isinstance(summary_path, str) and os.path.exists(summary_path):
            try:
                with open(summary_path, "r", encoding="utf-8") as f:
                    existing_summary = json.load(f)
                prior_exit = existing_summary.get("tests", {}).get("exit_code", 0)
                print(f"[resume] already complete summary={summary_path} exit_code={prior_exit}")
                return int(prior_exit)
            except Exception:
                print(f"[resume] already complete summary={summary_path}")
                return 0

    print("[test] running pytest -q")
    test_proc = subprocess.run(
        [python_exe, "-m", "pytest", "-q"],
        cwd=PROJECT_ROOT,
    )

    if test_proc.returncode != 0 and args.undo_on_test_failure and undo_records:
        print(f"[undo] pytest failed; undoing {len(undo_records)} applied patches")
        for undo_path in reversed(undo_records):
            try:
                _restore_undo_record(undo_path)
            except Exception as e:
                print(f"[undo] WARN failed to restore {undo_path}: {e}")

    summary = {
        "orchestrator_id": orchestrator_id,
        "orchestrator_dir": os.path.abspath(orchestrator_dir),
        "config": {
            "batch_backend_id": batch_backend_id,
            "codex_backend_id": args.codex_backend_id,
            "runs": args.runs,
            "sessions_per_run": args.sessions_per_run,
            "max_turns": args.max_turns,
            "max_parallel": args.max_parallel,
            "personalities": personalities,
            "apply_fix_max_attempts": args.apply_fix_max_attempts,
        },
        "runs": run_records,
        "applied": applied,
        "undo_records": undo_records,
        "per_run_tests": per_run_tests,
        "tests": {
            "exit_code": test_proc.returncode,
        },
    }

    summary_path = os.path.join(orchestrator_dir, "autopatch_summary.json")
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    progress.update(
        {
            "ts": datetime.now(timezone.utc).isoformat(),
            "status": "done",
            "next_run_index": int(args.runs),
            "summary_path": os.path.abspath(summary_path),
        }
    )
    _maybe_advance_stage(progress, "done")
    _atomic_write_json(progress_path, progress)

    print(f"[done] summary={summary_path}")
    return int(test_proc.returncode)


if __name__ == "__main__":
    raise SystemExit(main())
