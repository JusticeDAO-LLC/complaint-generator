#!/usr/bin/env python3
"""Build a local legal corpus vector index for semantic grounding searches.

This script downloads or loads available legal corpus data from configured
sources and builds a vector index file suitable for use with
``constrain_assertions_to_corpus`` via the
``COMPLAINT_LEGAL_VECTOR_INDEX_DIR`` environment variable.

Usage
-----
::

    python scripts/build_legal_corpus_index.py [--output-dir DIR] [--source SOURCE] [--max-records N]

Arguments
---------
--output-dir DIR
    Directory to write the index files to.  Defaults to
    ``./datasets/legal_corpus_index``.

--source SOURCE
    Legal data source to index.  One of:
    ``us_code`` (default), ``federal_register``, ``state_laws``, ``all``.

--state STATE
    Two-letter US state code to restrict state-law indexing (only used when
    ``--source`` is ``state_laws`` or ``all``).

--max-records N
    Maximum number of corpus records to embed and index.  Defaults to 5000.
    Use 0 for no limit (may be slow).

--model MODEL
    Embedding model name.  Defaults to ``thenlper/gte-small``.

--dry-run
    Print the plan without downloading or writing any files.

The script writes two files to the output directory:

* ``legal_corpus.vectors.npy`` — numpy float32 array (N × D)
* ``legal_corpus.records.jsonl`` — one JSON record per line with at minimum
  ``id``, ``title``, ``text``, and ``source`` keys

These files are loaded by
:func:`integrations.ipfs_datasets.vector_store.search_vector_index` when the
``legal_corpus`` index is requested.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("build_legal_corpus_index")

DEFAULT_OUTPUT_DIR = Path("datasets") / "legal_corpus_index"
DEFAULT_MAX_RECORDS = 5000
DEFAULT_EMBEDDING_MODEL = "thenlper/gte-small"

VALID_SOURCES = ("us_code", "federal_register", "state_laws", "all")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _try_import_numpy():
    try:
        import numpy as np
        return np
    except ImportError:
        logger.error("numpy is required: pip install numpy")
        sys.exit(1)


def _build_embedding_fn(model_name: str):
    """Return a function that embeds a list of texts → list of float vectors."""
    try:
        from integrations.ipfs_datasets.vector_store import get_embeddings_router
        router = get_embeddings_router()
        if router is not None:
            def _embed_via_router(texts: List[str]) -> List[List[float]]:
                vectors: List[List[float]] = []
                for text in texts:
                    result = router.embed(text, model=model_name)
                    if hasattr(result, "tolist"):
                        vectors.append(result.tolist())
                    elif isinstance(result, (list, tuple)):
                        vectors.append([float(x) for x in result])
                    else:
                        vectors.append([])
                return vectors
            logger.info("Using workspace embeddings router with model '%s'", model_name)
            return _embed_via_router
    except Exception as exc:
        logger.debug("Router embed unavailable (%s), falling back to sentence-transformers", exc)

    try:
        from sentence_transformers import SentenceTransformer  # type: ignore
        st_model = SentenceTransformer(model_name)
        def _embed_via_st(texts: List[str]) -> List[List[float]]:
            embeddings = st_model.encode(texts, convert_to_tensor=False)
            return [list(v) for v in embeddings]
        logger.info("Using sentence-transformers with model '%s'", model_name)
        return _embed_via_st
    except ImportError:
        pass

    logger.error(
        "No embedding backend found.  Install sentence-transformers or configure the workspace "
        "embeddings router:\n  pip install sentence-transformers"
    )
    sys.exit(1)


# ---------------------------------------------------------------------------
# Corpus loaders
# ---------------------------------------------------------------------------


def _load_us_code_records(max_records: int) -> List[Dict[str, Any]]:
    records: List[Dict[str, Any]] = []
    try:
        from integrations.ipfs_datasets.legal import search_us_code
        results = search_us_code(
            "civil rights employment discrimination",
            max_results=min(max_records, 200),
        )
        for item in results or []:
            records.append(
                {
                    "id": str(item.get("id") or item.get("citation") or ""),
                    "title": str(item.get("title") or item.get("section") or "US Code Section"),
                    "text": str(item.get("excerpt") or item.get("text") or ""),
                    "source": "us_code",
                    "citation": str(item.get("citation") or ""),
                }
            )
            if max_records and len(records) >= max_records:
                break
    except Exception as exc:
        logger.warning("US Code loader error: %s", exc)
    logger.info("Loaded %d US Code records", len(records))
    return records


def _load_federal_register_records(max_records: int) -> List[Dict[str, Any]]:
    records: List[Dict[str, Any]] = []
    try:
        from integrations.ipfs_datasets.legal import search_federal_register
        results = search_federal_register(
            "civil rights employment workplace",
            max_results=min(max_records, 200),
        )
        for item in results or []:
            records.append(
                {
                    "id": str(item.get("id") or item.get("document_number") or ""),
                    "title": str(item.get("title") or "Federal Register Document"),
                    "text": str(item.get("excerpt") or item.get("abstract") or item.get("text") or ""),
                    "source": "federal_register",
                    "citation": str(item.get("citation") or item.get("document_number") or ""),
                }
            )
            if max_records and len(records) >= max_records:
                break
    except Exception as exc:
        logger.warning("Federal Register loader error: %s", exc)
    logger.info("Loaded %d Federal Register records", len(records))
    return records


def _load_state_laws_records(
    state: Optional[str],
    max_records: int,
) -> List[Dict[str, Any]]:
    records: List[Dict[str, Any]] = []
    queries = [
        "employment discrimination",
        "civil rights",
        "workplace harassment",
    ]
    try:
        from integrations.ipfs_datasets.legal import search_state_laws
        for query in queries:
            results = search_state_laws(
                query,
                state=state,
                max_results=min(max_records // len(queries) + 1, 100),
                allow_live_scrape_fallback=True,
            )
            for item in results or []:
                records.append(
                    {
                        "id": str(item.get("id") or item.get("citation") or ""),
                        "title": str(item.get("title") or "State Law Section"),
                        "text": str(item.get("excerpt") or item.get("text") or ""),
                        "source": "state_laws",
                        "state": str(state or item.get("state") or "").upper(),
                        "citation": str(item.get("citation") or ""),
                    }
                )
            if max_records and len(records) >= max_records:
                break
    except Exception as exc:
        logger.warning("State laws loader error: %s", exc)
    logger.info("Loaded %d state laws records", len(records))
    return records


def _load_corpus_records(
    source: str,
    state: Optional[str],
    max_records: int,
) -> List[Dict[str, Any]]:
    records: List[Dict[str, Any]] = []
    if source in ("us_code", "all"):
        records.extend(_load_us_code_records(max_records))
    if source in ("federal_register", "all"):
        remaining = max(0, max_records - len(records)) if max_records else max_records
        records.extend(_load_federal_register_records(remaining))
    if source in ("state_laws", "all"):
        remaining = max(0, max_records - len(records)) if max_records else max_records
        records.extend(_load_state_laws_records(state, remaining))
    if max_records and len(records) > max_records:
        records = records[:max_records]
    return records


# ---------------------------------------------------------------------------
# Index builder
# ---------------------------------------------------------------------------


def build_index(
    output_dir: Path,
    source: str,
    state: Optional[str],
    max_records: int,
    model_name: str,
    dry_run: bool,
) -> None:
    logger.info("Building legal corpus vector index")
    logger.info("  source:     %s", source)
    logger.info("  state:      %s", state or "(all)")
    logger.info("  max_records: %d", max_records)
    logger.info("  model:      %s", model_name)
    logger.info("  output_dir: %s", output_dir)

    if dry_run:
        logger.info("Dry-run mode — no files written.")
        return

    np = _try_import_numpy()

    records = _load_corpus_records(source, state, max_records)
    if not records:
        logger.error("No corpus records loaded.  Cannot build index.")
        sys.exit(1)

    logger.info("Loaded %d corpus records total", len(records))

    # Filter out records with empty text
    records = [r for r in records if str(r.get("text") or "").strip()]
    logger.info("%d records have non-empty text", len(records))

    texts = [str(r.get("text") or "") for r in records]
    embed_fn = _build_embedding_fn(model_name)

    logger.info("Embedding %d texts …", len(texts))
    batch_size = 64
    all_vectors: List[List[float]] = []
    for i in range(0, len(texts), batch_size):
        batch = texts[i : i + batch_size]
        vecs = embed_fn(batch)
        all_vectors.extend(vecs)
        logger.info("  Embedded %d / %d", min(i + batch_size, len(texts)), len(texts))

    # Validate embedding dimension consistency
    dims = {len(v) for v in all_vectors if v}
    if len(dims) != 1:
        logger.error("Inconsistent embedding dimensions: %s", dims)
        sys.exit(1)
    dim = dims.pop()
    logger.info("Embedding dimension: %d", dim)

    vector_array = np.array(all_vectors, dtype=np.float32)

    output_dir.mkdir(parents=True, exist_ok=True)
    vectors_path = output_dir / "legal_corpus.vectors.npy"
    records_path = output_dir / "legal_corpus.records.jsonl"

    np.save(str(vectors_path), vector_array)
    logger.info("Saved vectors: %s  (shape %s)", vectors_path, vector_array.shape)

    with records_path.open("w", encoding="utf-8") as fh:
        for record in records:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    logger.info("Saved records: %s", records_path)

    logger.info("Legal corpus vector index built successfully.")
    logger.info("")
    logger.info("To use the index, set:")
    logger.info("  export COMPLAINT_LEGAL_VECTOR_INDEX_DIR=%s", output_dir.resolve())


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build a local legal corpus vector index for semantic grounding searches.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--output-dir",
        default=str(DEFAULT_OUTPUT_DIR),
        help=f"Output directory for index files (default: {DEFAULT_OUTPUT_DIR})",
    )
    parser.add_argument(
        "--source",
        default="us_code",
        choices=VALID_SOURCES,
        help="Legal data source to index (default: us_code)",
    )
    parser.add_argument(
        "--state",
        default=None,
        help="Two-letter US state code for state-law indexing (e.g. CA, TX)",
    )
    parser.add_argument(
        "--max-records",
        type=int,
        default=DEFAULT_MAX_RECORDS,
        help=f"Maximum corpus records to embed (default: {DEFAULT_MAX_RECORDS}; 0 = no limit)",
    )
    parser.add_argument(
        "--model",
        default=DEFAULT_EMBEDDING_MODEL,
        help=f"Sentence embedding model (default: {DEFAULT_EMBEDDING_MODEL})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the plan without downloading or writing files",
    )
    args = parser.parse_args()

    # Ensure PYTHONPATH includes the workspace root
    repo_root = Path(__file__).resolve().parent.parent
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))

    build_index(
        output_dir=Path(args.output_dir),
        source=args.source,
        state=args.state,
        max_records=args.max_records,
        model_name=args.model,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    main()
