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
        mountEditor(host, arguments[2] || null);
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
        var response = await fetch("/api/documents/" + encodeURIComponent(caseId) + "/complaint-outline", {
            credentials: "same-origin",
            headers: headers
        });
        var payload = await response.json();
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
            }, editorPayload);
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
        render(host, payload, editorPayload);
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
