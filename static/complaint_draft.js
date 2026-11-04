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
        var response = await fetch("/api/documents/" + encodeURIComponent(caseId) + "/complaint-outline", {
            credentials: "same-origin",
            headers: headers
        });
        var payload = await response.json();
        if (!response.ok) {
            render(host, {
                status: "error",
                draft: {present: false, text: ""},
                sections: [],
                gaps: [{reason: text(payload.detail || payload.error || "outline_unavailable"), visible: true}],
                facts: []
            });
            return payload;
        }
        render(host, payload);
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
