# Consolidation sibling modules

Each row is a sibling module extracted by the repository consolidation and the owner it was extracted from. Root shims re-export the `complaint_phases` bodies. Versioned interfaces use `INTERFACE_SCHEMA` `complaint-generator/module-interface@1` and `INTERFACE_VERSION` `1.0.0`.

| Sibling | Extracted from |
| --- | --- |
| `complaint_phases/intake_status.py` | `intake_status.py` |
| `complaint_phases/workflow_phase_guidance.py` | `workflow_phase_guidance.py` |
| `complaint_phases/document_pipeline.py` | `document_pipeline.py` |
| `complaint_phases/document_optimization.py` | `document_optimization.py` |
| `mediator/claim_support_review.py` | `claim_support_review.py` |
| `complaint_phases/document_pipeline_guidance.py` | `complaint_phases/document_pipeline.py` |
| `mediator/claim_support_review_sections.py` | `mediator/claim_support_review.py` |
| `complaint_phases/document_pipeline_readiness.py` | `complaint_phases/document_pipeline.py` |
| `complaint_phases/document_optimization_summaries.py` | `complaint_phases/document_optimization.py` |
| `applications/complaint_workspace_drafting.py` | `applications/complaint_workspace.py` |
| `mediator/intake_question_flow.py` | `mediator/mediator.py` |
| `complaint_phases/denoiser_questions.py` | `complaint_phases/denoiser.py` |
| `mediator/claim_support_diagnostics.py` | `mediator/claim_support_hooks.py` |

Session reports live in `docs/archive/sessions`. Plans and profiles live in `docs/archive/reports`.
