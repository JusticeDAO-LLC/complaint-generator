# REF-119 Swallowed Exception Review

Date: 2026-07-22
Source finding: `integrations/ipfs_datasets/documents.py:1148`
Evidence: `/home/barberb/complaint-generator/data/refactor_supervisor/discovery/2026-07-22-ref-119-codebase-scan-13e95d4f65f7.md`

## Decision

PDF ingestion performs optional OCR when its initial parse contains little text.
OCR process, decoding, and filesystem failures are expected operational failures:
they should not discard a usable initial parse, but callers need the failure
details to decide whether to retry or obtain another source document. These
failures are now retained as structured `ocr_error` metadata, and failed OCR
marks the record as still needing OCR. A nonzero `ocrmypdf` exit and a missing
output PDF are reported through the same contract.

The broad `Exception` handler also concealed unexpected parser and programming
failures. The handler now catches only `OSError`, `UnicodeError`, and
`subprocess.SubprocessError`; unrelated failures propagate for diagnosis. The
temporary OCR directory is still removed in every case.

## Focused Validation

`tests/test_ref_119_documents_ocr.py` verifies that expected OCR exceptions and
nonzero command exits preserve the initial parse and persist actionable error
metadata, and that a missing OCR output is reported. It also verifies cleanup
and confirms that an unexpected OCR parser failure is no longer swallowed.

Required syntax validation:

```text
python3 -m py_compile integrations/ipfs_datasets/documents.py
```
