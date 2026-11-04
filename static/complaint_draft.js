(function () {
    "use strict";

    function text(value) {
        return value === undefined || value === null ? "" : String(value);
    }

    function node(tag, attrs) {
        var element = document.createElement(tag);
        Object.keys(attrs || {}).forEach(function (key) {
            if (key === "text") element.textContent = attrs[key];
            else element.setAttribute(key, attrs[key]);
        });
        return element;
    }

    function caseHeaders() {
        var client = window.workspaceClient;
        var context = client && client.caseContext;
        var headers = {};
        if (!context || !context.case_id) return {caseId: "", headers: headers};
        if (client.csrfToken) headers["x-csrf-token"] = client.csrfToken;
        headers["x-tenant-id"] = context.tenant_id || "";
        headers["x-case-id"] = context.case_id;
        headers["x-resource-id"] = context.resource_id || "";
        if (context.expected_revision || context.revision) {
            headers["x-expected-revision"] = String(context.expected_revision || context.revision);
        }
        return {caseId: context.case_id, headers: headers};
    }

    function revealHost(host) {
        var panel = host.closest ? host.closest("[data-tab-panel]") : null;
        if (panel) {
            var tabName = panel.getAttribute("data-tab-panel");
            document.querySelectorAll(".tab-panel").forEach(function (node) {
                node.classList.toggle("is-active", node === panel);
            });
            document.querySelectorAll(".tab-button").forEach(function (node) {
                node.classList.toggle("is-active", node.getAttribute("data-tab-target") === tabName);
            });
        }
        host.hidden = false;
        host.style.display = "block";
    }

    function render(host, payload) {
        var outline = payload && typeof payload === "object" ? payload : {};
        revealHost(host);
        host.replaceChildren();
        host.dataset.state = text(outline.status || "empty");
        host.dataset.legalSufficiency = "false";
        host.dataset.proof = "false";
        host.appendChild(node("h3", {text: "Complaint outline"}));
        var status = node("p", {
            "data-role": "outline-status",
            text: outline.status === "error"
                ? "The complaint outline could not be read. Nothing was marked complete."
                : "Missing support and unresolved gaps stay visible. Model prose and evidence labels do not complete a requirement."
        });
        host.appendChild(status);
        var layout = node("div", {"class": "complaint-outline__layout"});
        layout.style.display = "grid";
        layout.style.gridTemplateColumns = "minmax(0, 1.2fr) minmax(16rem, 0.8fr)";
        layout.style.gap = "1rem";
        var draftColumn = node("div", {"data-role": "draft-column"});
        var supportColumn = node("aside", {"data-role": "support-column", "aria-label": "Facts, evidence spans, and admitted authority"});
        var draft = outline.draft || {};
        draftColumn.appendChild(node("h4", {text: draft.present ? "Current draft" : "No current draft"}));
        draftColumn.appendChild(node("p", {
            "data-role": "draft-text",
            "data-draft-id": text(draft.draft_id),
            "data-draft-revision": text(draft.revision || 0),
            text: draft.text || "No draft text is stored for this case."
        }));
        var sections = Array.isArray(outline.sections) ? outline.sections : [];
        if (!sections.length) {
            draftColumn.appendChild(node("p", {"data-role": "missing-outline", text: "No requirement is tied to this draft yet."}));
        }
        sections.forEach(function (section) {
            var block = node("article", {
                "data-role": "outline-section",
                "data-section-id": text(section.section_id),
                "data-support-cited": section.support_cited === true ? "true" : "false",
                "data-requirement-completed": "false",
                "data-legal-sufficiency": "false"
            });
            var open = node("button", {"type": "button", "data-role": "open-section", text: text(section.heading || "Requirement")});
            var body = node("div", {"data-role": "section-body", hidden: "hidden"});
            open.addEventListener("click", function () {
                var hidden = body.hasAttribute("hidden");
                if (hidden) body.removeAttribute("hidden");
                else body.setAttribute("hidden", "hidden");
                open.setAttribute("aria-expanded", hidden ? "true" : "false");
            });
            block.appendChild(open);
            if (section.model_prose) {
                body.appendChild(node("p", {
                    "data-role": "model-prose",
                    "data-completes-requirement": "false",
                    text: "Model prose, not support: " + text(section.model_prose)
                }));
            }
            if (section.evidence_label) {
                body.appendChild(node("p", {
                    "data-role": "evidence-label",
                    "data-completes-requirement": "false",
                    text: "Evidence label, not a span: " + text(section.evidence_label)
                }));
            }
            block.appendChild(body);
            draftColumn.appendChild(block);
            var support = node("section", {
                "data-role": "requirement-support",
                "data-section-id": text(section.section_id),
                "data-requirement-completed": "false"
            });
            support.appendChild(node("h4", {text: text(section.heading || "Requirement")}));
            if (section.authority && section.authority.admitted_law === true) {
                var link = node("a", {
                    id: "admitted-authority-" + text(section.authority.passage_id),
                    href: text(section.authority.href || ("#admitted-authority-" + section.authority.passage_id)),
                    "data-role": "admitted-authority",
                    "data-admitted-law": "true",
                    "data-passage-id": text(section.authority.passage_id),
                    text: text(section.authority.citation || section.authority.passage_id)
                });
                var span = section.authority.source_span || {};
                support.appendChild(link);
                support.appendChild(node("p", {
                    "data-role": "authority-span",
                    "data-span-start": text(span.start),
                    "data-span-end": text(span.end),
                    text: "Authority span " + text(span.start) + ":" + text(span.end) + (span.text ? " " + span.text : "")
                }));
            } else {
                support.appendChild(node("p", {"data-role": "missing-authority", text: "No admitted authority is linked."}));
            }
            (section.facts || []).forEach(function (fact) {
                support.appendChild(node("p", {
                    "data-role": "fact",
                    "data-fact-id": text(fact.fact_id),
                    text: text(fact.text || fact.fact_id)
                }));
            });
            (section.evidence || []).forEach(function (item) {
                var evidenceSpan = item.span || {};
                support.appendChild(node("p", {
                    "data-role": "evidence-span",
                    "data-artifact-id": text(item.artifact_id),
                    "data-span-start": text(evidenceSpan.start),
                    "data-span-end": text(evidenceSpan.end),
                    text: text(item.artifact_id) + " [" + text(evidenceSpan.start) + ":" + text(evidenceSpan.end) + "] " + text(evidenceSpan.text)
                }));
            });
            (section.gaps || []).forEach(function (gap) {
                support.appendChild(node("p", {
                    "data-role": "gap",
                    "data-reason": text(gap.reason),
                    text: "Unresolved: " + text(gap.reason)
                }));
            });
            supportColumn.appendChild(support);
        });
        (outline.unresolved_research || []).forEach(function (gap) {
            supportColumn.appendChild(node("p", {
                "data-role": "gap",
                "data-reason": text(gap.reason),
                text: "Unresolved: " + text(gap.reason)
            }));
        });
        (outline.gaps || []).forEach(function (gap) {
            if (sections.length && (outline.unresolved_research || []).some(function (item) { return item.reason === gap.reason; })) return;
            if (sections.length && sections.some(function (section) {
                return (section.gaps || []).some(function (item) { return item.reason === gap.reason; });
            })) return;
            supportColumn.appendChild(node("p", {
                "data-role": "gap",
                "data-reason": text(gap.reason),
                text: "Unresolved: " + text(gap.reason)
            }));
        });
        (outline.facts || []).forEach(function (fact) {
            if (supportColumn.querySelector('[data-fact-id="' + text(fact.fact_id).replace(/"/g, "") + '"]')) return;
            supportColumn.appendChild(node("p", {
                "data-role": "fact",
                "data-fact-id": text(fact.fact_id),
                "data-linked": "false",
                text: text(fact.text || fact.fact_id)
            }));
        });
        layout.appendChild(draftColumn);
        layout.appendChild(supportColumn);
        host.appendChild(layout);
        mountEditor(host, arguments[2] || null, arguments[3] || null);
    }

    function ensureStyles() {
        if (document.querySelector("link[data-complaint-draft-style]")) return;
        var link = node("link", {rel: "stylesheet", href: "/static/complaint_draft.css", "data-complaint-draft-style": "true"});
        document.head.appendChild(link);
    }

    function mountEditor(host, editor) {
        ensureStyles();
        var state = editor && typeof editor === "object" ? editor : {
            save_state: "unavailable",
            head_revision: 0,
            current_text: "",
            revisions: [],
            difference: {changes: []},
            code: "editor_unavailable"
        };
        host.dataset.headRevision = text(state.head_revision || 0);
        host.dataset.draftId = text(state.draft_id || "complaint-draft");
        var panel = node("section", {"class": "complaint-draft-editor", "data-role": "draft-editor", "aria-label": "Versioned draft editor"});
        panel.appendChild(node("h4", {text: "Draft revisions"}));
        var saveState = node("p", {
            "data-role": "save-state",
            "data-save-state": text(state.save_state || "idle"),
            text: saveLabel(state)
        });
        panel.appendChild(saveState);
        var field = node("textarea", {"data-role": "draft-input", "aria-label": "Complaint draft text"});
        field.value = text(state.current_text);
        panel.appendChild(field);
        var save = node("button", {"type": "button", "data-role": "save-draft", text: "Save draft"});
        save.addEventListener("click", function () { saveDraft(host, field, saveState); });
        panel.appendChild(save);
        var revisions = node("div", {"data-role": "revision-list"});
        (state.revisions || []).forEach(function (revision) {
            var button = node("button", {
                "type": "button",
                "data-role": "compare-revision",
                "data-revision": text(revision.revision),
                text: "Revision " + text(revision.revision)
            });
            button.addEventListener("click", function () { showRevision(host, revision.revision); });
            revisions.appendChild(button);
        });
        panel.appendChild(revisions);
        panel.appendChild(renderDifference(state.difference));
        var stored = node("p", {
            "data-role": "stored-draft",
            "data-head-revision": text(state.head_revision || 0),
            "data-text-digest": text(state.text_digest),
            text: state.current_text ? text(state.current_text) : "No encrypted draft is stored yet."
        });
        panel.appendChild(stored);
        host.appendChild(panel);
        mountReviewActions(host, arguments[2] || null);
    }

    function actionCard(record, role) {
        var card = node("article", {
            "data-role": role,
            "data-record-id": text(record.record_id),
            "data-provenance": text(record.provenance),
            "data-author": text(record.author),
            "data-target-revision": text(record.target_revision),
            "data-target-author": text(record.target_author),
            "data-status": text(record.status)
        });
        card.appendChild(node("p", {
            "data-role": "suggestion-provenance",
            text: text(record.provenance) + " author " + text(record.author) + " on revision " + text(record.target_revision)
        }));
        if (record.proposed_text) {
            card.appendChild(node("p", {"data-role": "proposed-text", text: text(record.proposed_text)}));
        }
        if (record.proof_status) {
            card.appendChild(node("p", {"data-role": "proof-status", text: "Machine proof " + text(record.proof_status)}));
        }
        return card;
    }

    function mountReviewActions(host, actions) {
        var panel = node("section", {
            "class": "complaint-draft-suggestions",
            "data-role": "draft-suggestions",
            "aria-label": "AI suggestions and human review"
        });
        if (actions && actions.status !== "unavailable") {
            host.dataset.currentRevision = text(actions.target_revision || 0);
            host.dataset.targetDigest = text(actions.target_text_digest || "");
            if (actions.draft_id) host.dataset.draftId = text(actions.draft_id);
        }
        if (!actions || actions.status === "unavailable") {
            panel.appendChild(node("p", {
                "data-role": "suggestions-unavailable",
                text: "Review suggestions are unavailable. The owner's draft was not changed."
            }));
            host.appendChild(panel);
            return;
        }
        panel.appendChild(node("h4", {text: "Suggestions and review"}));
        panel.appendChild(node("p", {
            "data-role": "target-version",
            "data-target-revision": text(actions.target_revision || 0),
            "data-target-author": text(actions.target_author),
            "data-draft-id": text(actions.draft_id),
            text: "Target revision " + text(actions.target_revision || 0) + " by " + (text(actions.target_author) || "no author yet")
        }));
        var human = node("div", {"data-role": "human-reviews"});
        human.appendChild(node("h5", {text: "Human review"}));
        var humanRows = actions.human_reviews || [];
        if (!humanRows.length) human.appendChild(node("p", {"data-role": "human-empty", text: "No human review is recorded."}));
        humanRows.forEach(function (record) { human.appendChild(actionCard(record, "human-review")); });
        var proposal = node("textarea", {"data-role": "proposal-input", "aria-label": "Bounded human change"});
        var propose = node("button", {"type": "button", "data-role": "propose-change", text: "Propose bounded change"});
        propose.addEventListener("click", function () { proposeChange(host, proposal, "propose_bounded_change", "human"); });
        human.appendChild(proposal);
        human.appendChild(propose);
        human.appendChild(node("p", {"data-role": "proposal-note", text: "A proposal does not change the owner's draft."}));
        panel.appendChild(human);
        var models = node("div", {"data-role": "model-suggestions"});
        models.appendChild(node("h5", {text: "Model suggestion"}));
        var modelRows = actions.model_suggestions || [];
        if (!modelRows.length) models.appendChild(node("p", {"data-role": "model-empty", text: "No model suggestion is recorded."}));
        modelRows.forEach(function (record) {
            var card = actionCard(record, "model-suggestion");
            if (host.dataset.actorMembership === "owner" && record.status === "proposed") {
                var accept = node("button", {"type": "button", "data-role": "accept-suggestion", "data-record-id": text(record.record_id), text: "Accept suggestion"});
                accept.addEventListener("click", function () { acceptSuggestion(host, record); });
                card.appendChild(accept);
            }
            models.appendChild(card);
        });
        var modelText = node("textarea", {"data-role": "model-input", "aria-label": "Model suggestion text"});
        var modelId = node("input", {"data-role": "model-id", "aria-label": "Model id"});
        var recordModel = node("button", {"type": "button", "data-role": "record-model-suggestion", text: "Record model suggestion"});
        recordModel.addEventListener("click", function () { proposeChange(host, modelText, "record_draft_model_suggestion", "model", modelId.value); });
        models.appendChild(modelId);
        models.appendChild(modelText);
        models.appendChild(recordModel);
        panel.appendChild(models);
        var proofs = node("div", {"data-role": "machine-proofs"});
        proofs.appendChild(node("h5", {text: "Machine proof"}));
        var proofRows = actions.machine_proofs || [];
        if (!proofRows.length) proofs.appendChild(node("p", {"data-role": "proof-empty", text: "No machine proof is recorded."}));
        proofRows.forEach(function (record) { proofs.appendChild(actionCard(record, "machine-proof")); });
        var recordProof = node("button", {"type": "button", "data-role": "record-machine-proof", text: "Record machine proof"});
        recordProof.addEventListener("click", function () { proposeChange(host, null, "record_draft_machine_proof", "machine"); });
        proofs.appendChild(recordProof);
        panel.appendChild(proofs);
        var messages = node("div", {"data-role": "review-messages"});
        messages.appendChild(node("h5", {text: "Messages"}));
        var messageRows = actions.messages || [];
        if (!messageRows.length) messages.appendChild(node("p", {"data-role": "messages-empty", text: "Messages stay in correspondence, separate from suggestions."}));
        messageRows.forEach(function (record) {
            messages.appendChild(node("p", {
                "data-role": "case-message",
                "data-author": text(record.author || record.actor_principal_id),
                text: text(record.body || record.text || "Message")
            }));
        });
        panel.appendChild(messages);
        mountBoundReviews(host, panel, actions);
        humanRows.forEach(function (record) {
            if (host.dataset.actorMembership !== "owner" || record.status !== "proposed") return;
            var card = panel.querySelector("[data-role='human-review'][data-record-id='" + text(record.record_id) + "']");
            if (!card) return;
            var accept = node("button", {"type": "button", "data-role": "accept-suggestion", "data-record-id": text(record.record_id), text: "Accept suggestion"});
            accept.addEventListener("click", function () { acceptSuggestion(host, record); });
            card.appendChild(accept);
        });
        host.appendChild(panel);
    }

    function mountBoundReviews(host, panel, actions) {
        host.querySelectorAll("[data-role='evidence-comment-form'], [data-role='section-comment-form']").forEach(function (form) {
            form.remove();
        });
        var targets = actions.bound_review_targets || [];
        host.querySelectorAll("[data-role='evidence-span']").forEach(function (row) {
            var artifact = row.getAttribute("data-artifact-id") || "";
            var start = Number(row.getAttribute("data-span-start"));
            var end = Number(row.getAttribute("data-span-end"));
            var match = targets.filter(function (target) {
                return target.target_kind === "evidence_span" && target.artifact_id === artifact && target.span_start === start && target.span_end === end;
            })[0];
            var form = node("div", {"data-role": "evidence-comment-form"});
            var box = node("textarea", {"data-role": "evidence-comment", "aria-label": "Comment on evidence span"});
            var button = node("button", {
                "type": "button",
                "data-role": "comment-evidence",
                "data-qualification": match ? "exact" : "qualified",
                text: match ? "Comment on this evidence span" : "Comment with a qualified evidence target"
            });
            if (match) {
                row.setAttribute("data-artifact-version", text(match.artifact_version));
                row.setAttribute("data-target-qualification", "exact");
            }
            var version = node("input", {"data-role": "qualified-version", "aria-label": "Qualified artifact version"});
            var reason = node("input", {
                "data-role": "qualification-reason",
                "aria-label": "Qualification reason",
                value: "span_not_verified_against_artifact_bytes"
            });
            button.addEventListener("click", function () {
                if (match) {
                    postBoundReview(host, "comment_review_target", box.value, match);
                    return;
                }
                postBoundReview(host, "comment_review_target", box.value, {
                    target_kind: "qualified_evidence_span",
                    qualification: "qualified",
                    qualification_reason: reason.value,
                    artifact_id: artifact,
                    artifact_version: Number(version.value),
                    span_start: start,
                    span_end: end,
                    target_revision: Number(version.value)
                });
            });
            form.appendChild(box);
            if (!match) {
                form.appendChild(version);
                form.appendChild(reason);
            }
            form.appendChild(button);
            row.appendChild(form);
        });
        host.querySelectorAll("[data-role='outline-section']").forEach(function (section) {
            var sectionId = section.getAttribute("data-section-id") || "";
            var draft = host.querySelector("[data-role='draft-text']");
            var draftId = draft ? draft.getAttribute("data-draft-id") || "" : "";
            var revision = draft ? Number(draft.getAttribute("data-draft-revision") || "0") : 0;
            var form = node("div", {"data-role": "section-comment-form"});
            if (!sectionId || !draftId || !revision) {
                form.appendChild(node("p", {
                    "data-role": "section-comment-unavailable",
                    text: "Save a draft revision before commenting on this section."
                }));
                section.appendChild(form);
                return;
            }
            var box = node("textarea", {"data-role": "section-comment", "aria-label": "Comment on complaint section"});
            var button = node("button", {"type": "button", "data-role": "comment-section", text: "Comment on this complaint section"});
            button.addEventListener("click", function () {
                postBoundReview(host, "comment_review_target", box.value, {
                    target_kind: "complaint_section",
                    qualification: "exact",
                    section_id: sectionId,
                    draft_id: draftId,
                    target_id: sectionId,
                    target_revision: revision
                });
            });
            form.appendChild(box);
            form.appendChild(button);
            section.appendChild(form);
        });
        var bound = node("div", {"data-role": "bound-reviews"});
        bound.appendChild(node("h5", {text: "Evidence and section review"}));
        var rows = actions.section_reviews || [];
        if (!rows.length) {
            bound.appendChild(node("p", {"data-role": "bound-review-empty", text: "No review comment is tied to evidence or a complaint section."}));
        }
        rows.forEach(function (record) {
            var card = node("article", {
                "data-role": "bound-review",
                "data-record-id": text(record.record_id),
                "data-decision": text(record.decision),
                "data-status": text(record.status),
                "data-target-kind": text(record.target_kind),
                "data-actor": text(record.actor_principal_id),
                "data-target-revision": text(record.target_revision),
                "data-qualification": text(record.qualification),
                "data-artifact-id": text(record.artifact_id),
                "data-artifact-version": text(record.artifact_version),
                "data-span-start": text(record.span_start),
                "data-span-end": text(record.span_end),
                "data-section-id": text(record.section_id)
            });
            card.appendChild(node("p", {
                text: text(record.decision) + " by " + text(record.actor_principal_id) + " on " + text(record.target_kind) + " revision " + text(record.target_revision)
            }));
            if (record.body) card.appendChild(node("p", {"data-role": "bound-review-body", text: text(record.body)}));
            if (record.decision === "comment" && record.status === "commented") {
                var accept = node("button", {"type": "button", "data-role": "accept-bound-review", text: "Accept comment"});
                var reject = node("button", {"type": "button", "data-role": "reject-bound-review", text: "Reject comment"});
                accept.addEventListener("click", function () { postBoundReview(host, "accept_review_target", "", record, record.record_id); });
                reject.addEventListener("click", function () { postBoundReview(host, "reject_review_target", "", record, record.record_id); });
                card.appendChild(accept);
                card.appendChild(reject);
            }
            bound.appendChild(card);
        });
        bound.appendChild(node("p", {"data-role": "bound-review-note", text: "A review comment does not change the owner's draft or borrow the owner key."}));
        panel.appendChild(bound);
    }

    async function postBoundReview(host, operation, commentBody, target, commentId) {
        var caseId = host.dataset.caseId || "";
        var payload = {
            operation: operation,
            request_id: operation + "-" + Date.now() + "-" + Math.random().toString(16).slice(2),
            target_kind: target.target_kind,
            qualification: target.qualification || "",
            expected_target_revision: Number(target.target_revision)
        };
        if (commentBody) payload.body = commentBody;
        ["artifact_id", "section_id", "draft_id", "target_id", "qualification_reason"].forEach(function (key) {
            if (target[key]) payload[key] = target[key];
        });
        ["artifact_version", "span_start", "span_end"].forEach(function (key) {
            if (target[key] !== undefined && target[key] !== null && target[key] !== "") payload[key] = Number(target[key]);
        });
        if (commentId) payload.comment_id = commentId;
        var response = await fetch("/api/documents/" + encodeURIComponent(caseId) + "/draft-reviews", {
            method: "POST",
            credentials: "same-origin",
            headers: jsonHeaders(host),
            body: JSON.stringify(payload)
        });
        var result = null;
        try { result = await response.json(); } catch (error) { result = null; }
        var note = host.querySelector("[data-role='bound-review-note']");
        if (!response.ok) {
            if (note) note.textContent = "The review comment was not recorded. The owner's draft was not changed.";
            return result;
        }
        if (note) note.textContent = "Recorded " + operation + ". The owner's draft was not changed.";
        await refreshActions(host);
        return result;
    }

    function reviewPayload(host, operation, provenance, proposed, modelId) {
        return {
            operation: operation,
            request_id: operation + "-" + Date.now() + "-" + Math.random().toString(16).slice(2),
            draft_id: host.dataset.draftId || "complaint-draft",
            expected_revision: Number(host.dataset.currentRevision || host.dataset.headRevision || "0"),
            expected_text_digest: host.dataset.targetDigest || "",
            provenance: provenance,
            proposed_text: proposed || "",
            model_id: modelId || ""
        };
    }

    async function refreshActions(host) {
        var caseId = host.dataset.caseId || "";
        var response = await fetch("/api/documents/" + encodeURIComponent(caseId) + "/workflow-stage", {
            credentials: "same-origin",
            headers: jsonHeaders(host)
        });
        var payload = await response.json();
        var existing = host.querySelector("[data-role='draft-suggestions']");
        if (existing) existing.remove();
        var actions = response.ok && payload.draft_review_actions ? payload.draft_review_actions : {status: "unavailable"};
        mountReviewActions(host, actions);
    }

    async function proposeChange(host, field, operation, provenance, modelId) {
        var storedBefore = (host.querySelector("[data-role='stored-draft']") || {}).textContent || "";
        var caseId = host.dataset.caseId || "";
        var response = await fetch("/api/documents/" + encodeURIComponent(caseId) + "/draft-reviews", {
            method: "POST",
            credentials: "same-origin",
            headers: jsonHeaders(host),
            body: JSON.stringify(reviewPayload(host, operation, provenance, field ? field.value : "", modelId))
        });
        var payload = await response.json();
        var note = host.querySelector("[data-role='proposal-note']");
        if (!response.ok) {
            if (note) note.textContent = "The suggestion was not recorded. The owner's draft was not changed.";
            return payload;
        }
        var stored = host.querySelector("[data-role='stored-draft']");
        if (stored) stored.textContent = storedBefore;
        if (note) note.textContent = "Recorded as " + provenance + ". The owner's draft was not changed.";
        await refreshActions(host);
        return payload;
    }

    async function acceptSuggestion(host, record) {
        if (host.dataset.actorMembership !== "owner") return null;
        var caseId = host.dataset.caseId || "";
        var response = await fetch("/api/documents/" + encodeURIComponent(caseId) + "/draft-versions", {
            method: "POST",
            credentials: "same-origin",
            headers: jsonHeaders(host),
            body: JSON.stringify({
                operation: "accept_draft_suggestion",
                request_id: "accept-" + Date.now() + "-" + Math.random().toString(16).slice(2),
                proposal_id: record.record_id,
                draft_id: record.draft_id || host.dataset.draftId,
                expected_revision: Number(record.target_revision),
                expected_text_digest: record.target_text_digest || "",
                proposed_text: record.proposed_text
            })
        });
        var payload = await response.json();
        if (!response.ok || !payload.adopted_text) return payload;
        var field = host.querySelector("[data-role='draft-input']");
        var saveState = host.querySelector("[data-role='save-state']");
        if (field && saveState) {
            field.value = payload.adopted_text;
            await saveDraft(host, field, saveState);
        }
        await refreshActions(host);
        return payload;
    }

    function saveLabel(state) {
        var name = text(state.save_state || "idle");
        if (name === "saving") return "Saving the encrypted draft.";
        if (name === "saved") return "Saved to the case revision.";
        if (name === "conflict") return "Save conflict. The encrypted draft was not overwritten.";
        if (name === "unavailable") return "The draft editor cannot save because the case key or owner is unavailable.";
        return "Edits stay in the case revision owner. Browser storage is not the draft.";
    }

    function renderDifference(difference) {
        var block = node("div", {"data-role": "revision-diff"});
        var changes = difference && Array.isArray(difference.changes) ? difference.changes : [];
        if (!changes.length) {
            block.appendChild(node("p", {"data-role": "diff-empty", text: "No revision difference is stored yet."}));
            return block;
        }
        changes.forEach(function (change) {
            block.appendChild(node("p", {"data-role": "diff-line", "data-op": text(change.op), text: text(change.text)}));
        });
        return block;
    }

    function editorUrl(caseId) {
        return "/api/documents/" + encodeURIComponent(caseId) + "/draft-editor";
    }

    async function showRevision(host, revision) {
        var caseId = host.dataset.caseId || "";
        if (!caseId) return;
        var current = host.dataset.currentRevision || revision;
        var response = await fetch(editorUrl(caseId) + "?base_revision=" + encodeURIComponent(revision) + "&compare_revision=" + encodeURIComponent(current), {
            credentials: "same-origin",
            headers: jsonHeaders(host)
        });
        var payload = await response.json();
        var existing = host.querySelector("[data-role='revision-diff']");
        if (existing) existing.replaceWith(renderDifference(payload.difference));
    }

    function jsonHeaders(host) {
        var headers = {};
        try { headers = JSON.parse(host.dataset.requestHeaders || "{}"); } catch (error) { headers = {}; }
        headers["content-type"] = "application/json";
        return headers;
    }

    async function saveDraft(host, field, saveState) {
        saveState.setAttribute("data-save-state", "saving");
        saveState.textContent = saveLabel({save_state: "saving"});
        var caseId = host.dataset.caseId || "";
        var response = await fetch(editorUrl(caseId), {
            method: "POST",
            credentials: "same-origin",
            headers: jsonHeaders(host),
            body: JSON.stringify({
                request_id: "draft-" + Date.now() + "-" + Math.random().toString(16).slice(2),
                draft_id: host.dataset.draftId || "complaint-draft",
                text: field.value,
                expected_head_revision: Number(host.dataset.headRevision || "0")
            })
        });
        var payload = await response.json();
        var editor = payload.editor && payload.editor.current_text !== undefined ? payload.editor : payload;
        if (!response.ok) {
            saveState.setAttribute("data-save-state", "conflict");
            saveState.textContent = saveLabel({save_state: "conflict"});
            var diff = host.querySelector("[data-role='revision-diff']");
            if (diff && editor.difference) diff.replaceWith(renderDifference(editor.difference));
            var stored = host.querySelector("[data-role='stored-draft']");
            if (stored && editor.current_text !== undefined) {
                stored.textContent = editor.current_text || "No encrypted draft is stored yet.";
                stored.setAttribute("data-head-revision", text(editor.head_revision || 0));
            }
            if (editor.head_revision !== undefined) host.dataset.headRevision = text(editor.head_revision);
            return payload;
        }
        saveState.setAttribute("data-save-state", "saved");
        saveState.textContent = saveLabel({save_state: "saved"});
        host.dataset.headRevision = text(editor.head_revision || 0);
        host.dataset.currentRevision = text(editor.current_revision || 0);
        var draftText = host.querySelector("[data-role='draft-text']");
        if (draftText) draftText.textContent = editor.current_text || "";
        var storedSaved = host.querySelector("[data-role='stored-draft']");
        if (storedSaved) {
            storedSaved.textContent = editor.current_text || "";
            storedSaved.setAttribute("data-head-revision", text(editor.head_revision || 0));
            storedSaved.setAttribute("data-text-digest", text(editor.text_digest));
        }
        var diffSaved = host.querySelector("[data-role='revision-diff']");
        if (diffSaved) diffSaved.replaceWith(renderDifference(editor.difference));
        return payload;
    }

    async function load(options) {
        var host = document.getElementById("complaint-outline");
        if (!host) return null;
        var supplied = options || {};
        var discovered = caseHeaders();
        var caseId = supplied.caseId || discovered.caseId;
        var headers = supplied.headers || discovered.headers;
        if (!caseId) {
            render(host, {status: "empty", draft: {present: false, text: ""}, sections: [], gaps: [{reason: "no_case", visible: true}], facts: []});
            return null;
        }
        host.dataset.caseId = caseId;
        host.dataset.requestHeaders = JSON.stringify(headers);
        if (supplied.membership) host.dataset.actorMembership = supplied.membership;
        var response = await fetch("/api/documents/" + encodeURIComponent(caseId) + "/complaint-outline", {
            credentials: "same-origin",
            headers: headers
        });
        var payload = await response.json();
        var stageResponse = await fetch("/api/documents/" + encodeURIComponent(caseId) + "/workflow-stage", {
            credentials: "same-origin",
            headers: headers
        });
        var stagePayload = null;
        try { stagePayload = await stageResponse.json(); } catch (error) { stagePayload = null; }
        var actions = stageResponse.ok && stagePayload && stagePayload.draft_review_actions
            ? stagePayload.draft_review_actions
            : {status: "unavailable"};
        var editorResponse = await fetch("/api/documents/" + encodeURIComponent(caseId) + "/draft-editor", {
            credentials: "same-origin",
            headers: headers
        });
        var editorPayload = null;
        try { editorPayload = await editorResponse.json(); } catch (error) { editorPayload = null; }
        if (!editorResponse.ok) {
            editorPayload = {
                save_state: "unavailable",
                head_revision: 0,
                current_text: "",
                revisions: [],
                difference: {changes: []},
                code: editorPayload && (editorPayload.detail || editorPayload.code || editorPayload.error) || "editor_unavailable"
            };
        }
        if (!response.ok) {
            render(host, {
                status: "error",
                draft: {present: false, text: ""},
                sections: [],
                gaps: [{reason: text(payload.detail || payload.error || "outline_unavailable"), visible: true}],
                facts: []
            }, editorPayload, actions);
            return payload;
        }
        if (editorResponse.ok && editorPayload && editorPayload.durable === true) {
            payload.draft = payload.draft || {};
            payload.draft.present = true;
            payload.draft.text = editorPayload.current_text || "";
            payload.draft.revision = editorPayload.current_revision || 0;
            payload.draft.draft_id = editorPayload.draft_id || payload.draft.draft_id;
        }
        host.dataset.currentRevision = text(editorPayload && editorPayload.current_revision || 0);
        render(host, payload, editorPayload, actions);
        return payload;
    }

    function onDraftTask(event) {
        var button = event.target && event.target.closest ? event.target.closest("[data-case-task='draft']") : null;
        if (!button) return;
        load().catch(function () {
            var host = document.getElementById("complaint-outline");
            if (host) render(host, {status: "error", draft: {present: false, text: ""}, sections: [], gaps: [{reason: "outline_unavailable", visible: true}], facts: []});
        });
    }

    document.addEventListener("click", onDraftTask);
    window.ComplaintDraft = {render: render, load: load};
})();
