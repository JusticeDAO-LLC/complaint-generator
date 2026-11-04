/* Facts and timeline for the current interview projection.

   List, timeline, and the optional graph are views of one read. Changing
   the view does not write a graph. Corrections and "I don't know" go through
   the current interview owner. Confidence and a cached flag are not corroboration.
*/
(function () {
    "use strict";

    var state = {
        projection: null,
        session: null,
        selectedKey: "",
        mode: "list"
    };

    function text(value) {
        return value === undefined || value === null ? "" : String(value);
    }

    function root() {
        return document.getElementById("complaint-facts");
    }

    function setText(id, value) {
        var node = document.getElementById(id);
        if (node) node.textContent = value;
    }

    function caseId() {
        var client = window.workspaceClient;
        if (client && client.caseContext && client.caseContext.case_id) return text(client.caseContext.case_id);
        var binding = window.complaintCaseShell && window.complaintCaseShell.binding ? window.complaintCaseShell.binding() : null;
        return binding && binding.case_id ? text(binding.case_id) : "";
    }

    function rowsFrom(projection) {
        var body = projection && typeof projection === "object" ? projection : {};
        var rows = [];
        function add(bucket, item) {
            if (!item || typeof item !== "object") return;
            var provenance = item.source_provenance && typeof item.source_provenance === "object" ? item.source_provenance : {};
            var span = provenance.source_span && typeof provenance.source_span === "object" ? provenance.source_span : {};
            var adopted = item.explicitly_adopted_evidence === true && provenance.verified === true;
            var label = text(item.text || item.reason || item.kind || "Unresolved fact");
            rows.push({
                key: text(item.assertion_id || item.graph_entity_id || item.event_id || bucket + "-" + rows.length),
                bucket: bucket,
                text: label,
                assertionId: text(item.assertion_id),
                entityId: text(item.graph_entity_id),
                sourceId: text(provenance.source_id || item.immutable_source_id),
                version: text(provenance.extractor_version),
                span: text(span.text),
                activity: text(item.activity_status || item.reason || item.action),
                admitted: item.admitted_user_fact === true,
                adopted: adopted,
                uncertain: item.admitted_user_fact !== true || item.activity_status === "conflict" || item.activity_status === "unverified" || bucket === "unresolved" || bucket === "hypotheses",
                dated: dateIn(label)
            });
        }
        ["user_statements", "adopted_evidence", "allegations", "hypotheses", "evidence_revisions", "unresolved", "corrections", "contradictions"].forEach(function (bucket) {
            var items = body[bucket];
            if (!Array.isArray(items)) return;
            items.forEach(function (item) { add(bucket, item); });
        });
        var seen = {};
        return rows.filter(function (row) {
            if (!row.key || seen[row.key]) return false;
            seen[row.key] = true;
            return true;
        });
    }

    function dateIn(value) {
        var match = text(value).match(/\b(\d{4}-\d{2}-\d{2}|(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},\s+\d{4})\b/);
        return match ? match[1] : "";
    }

    function questionsFrom(session) {
        var body = session && typeof session === "object" ? session : {};
        var adaptive = body.adaptive_inquiry && typeof body.adaptive_inquiry === "object" ? body.adaptive_inquiry : {};
        var interview = body.session && body.session.shared_interview && typeof body.session.shared_interview === "object" ? body.session.shared_interview : {};
        var rows = [];
        function add(id, prompt, revision, kind) {
            var inquiryId = text(id);
            if (!inquiryId || rows.some(function (row) { return row.id === inquiryId; })) return;
            rows.push({id: inquiryId, prompt: text(prompt), revision: revision, kind: kind});
        }
        if (adaptive.pending && adaptive.inquiry_id) add(adaptive.inquiry_id, adaptive.prompt, adaptive.revision, "pending");
        var pending = interview.pending_inquiry;
        if (pending && typeof pending === "object") add(pending.inquiry_id, pending.question, pending.revision, "pending");
        (Array.isArray(adaptive.preserved_gaps) ? adaptive.preserved_gaps : []).forEach(function (gap) {
            if (!gap || typeof gap !== "object") return;
            add(gap.inquiry_id || gap.target_id || gap.id, gap.question || gap.reason || gap.prompt, gap.revision, "gap");
        });
        return rows;
    }

    function factButton(row) {
        var button = document.createElement("button");
        button.type = "button";
        button.className = "complaint-facts-fact";
        button.dataset.role = "fact";
        button.dataset.key = row.key;
        button.dataset.bucket = row.bucket;
        button.dataset.assertionId = row.assertionId;
        button.dataset.corroborated = row.adopted ? "true" : "false";
        button.dataset.uncertain = row.uncertain ? "true" : "false";
        button.dataset.admittedUserFact = row.admitted ? "true" : "false";
        button.setAttribute("aria-pressed", state.selectedKey === row.key ? "true" : "false");
        button.setAttribute("aria-controls", "complaint-facts-provenance");
        var title = document.createElement("strong");
        title.textContent = row.text;
        var meta = document.createElement("span");
        meta.textContent = row.adopted ? "Explicitly adopted evidence" : "Not corroborated";
        button.appendChild(title);
        button.appendChild(meta);
        if (row.dated) {
            var when = document.createElement("span");
            when.dataset.role = "fact-date";
            when.textContent = row.dated;
            button.appendChild(when);
        }
        button.addEventListener("click", function () {
            state.selectedKey = row.key;
            paintSelection();
            showProvenance(row);
        });
        return button;
    }

    function paintSelection() {
        var host = root();
        if (!host) return;
        Array.prototype.forEach.call(host.querySelectorAll("[data-role='fact']"), function (button) {
            button.setAttribute("aria-pressed", button.dataset.key === state.selectedKey ? "true" : "false");
        });
    }

    function showProvenance(row) {
        var panel = document.getElementById("complaint-facts-provenance");
        if (!panel) return;
        panel.hidden = false;
        panel.dataset.assertionId = row.assertionId;
        panel.dataset.corroborated = row.adopted ? "true" : "false";
        setText("complaint-facts-provenance-title", row.text);
        setText("complaint-facts-source", row.sourceId || "No source id was recorded.");
        setText("complaint-facts-version", row.version || "No extractor version was recorded.");
        setText("complaint-facts-span", row.span || "No source span was recorded.");
        setText("complaint-facts-uncertainty", row.uncertain ? ("Uncertain: " + (row.activity || "not an admitted user fact")) : "Recorded as an admitted user fact. That is not corroboration.");
        setText("complaint-facts-corroboration", row.adopted ? "Explicitly adopted evidence. Adoption is not legal proof." : "Not corroborated.");
        var target = document.getElementById("complaint-facts-target");
        if (target) target.textContent = row.assertionId ? ("Assertion " + row.assertionId) : "This row has no assertion id to correct.";
        var offer = correctionOffer();
        var graph = document.getElementById("complaint-facts-graph-revision");
        var session = document.getElementById("complaint-facts-session-revision");
        if (graph && !graph.dataset.userEdited) graph.value = text(offer.expected_graph_revision);
        if (session && !session.dataset.userEdited) session.value = offer.expected_session_revision === undefined || offer.expected_session_revision === null ? "" : String(offer.expected_session_revision);
        panel.focus();
    }

    function correctionOffer() {
        var adaptive = state.session && state.session.adaptive_inquiry;
        var offer = adaptive && adaptive.factual_correction;
        return offer && typeof offer === "object" ? offer : {};
    }

    function selectedRow() {
        return rowsFrom(state.projection).filter(function (row) { return row.key === state.selectedKey; })[0] || null;
    }

    function renderQuestions() {
        var list = document.getElementById("complaint-facts-questions");
        var host = root();
        if (!list || !host) return;
        var questions = questionsFrom(state.session);
        list.replaceChildren();
        questions.forEach(function (question) {
            var item = document.createElement("li");
            item.className = "complaint-facts-question";
            item.dataset.inquiryId = question.id;
            item.dataset.kind = question.kind;
            item.textContent = (question.kind === "gap" ? "Unanswered gap: " : "Unanswered question: ") + (question.prompt || question.id);
            list.appendChild(item);
        });
        host.dataset.unansweredCount = String(questions.length);
        if (!questions.length) {
            var empty = document.createElement("li");
            empty.className = "complaint-facts-question";
            empty.dataset.kind = "none";
            empty.textContent = "No unanswered mediator question is on this session.";
            list.appendChild(empty);
        }
    }

    function renderFacts() {
        var host = root();
        if (!host) return;
        var projection = state.projection || {};
        var rows = rowsFrom(projection);
        var persistedId = text(projection.graph_id);
        var graphId = persistedId || (projection.status === "projected" ? text(projection.case_id) : "");
        host.dataset.graphId = graphId;
        host.dataset.graphCount = persistedId ? "1" : "0";
        host.dataset.corroborationFabricated = "false";
        ["complaint-facts-list", "complaint-facts-timeline", "complaint-facts-graph-nodes"].forEach(function (id) {
            var node = document.getElementById(id);
            if (node) node.replaceChildren();
        });
        var links = document.getElementById("complaint-facts-graph-links");
        if (links) links.replaceChildren();
        rows.forEach(function (row) {
            ["complaint-facts-list", "complaint-facts-timeline", "complaint-facts-graph-nodes"].forEach(function (id) {
                var node = document.getElementById(id);
                if (!node) return;
                var item = document.createElement("li");
                if (id === "complaint-facts-timeline") item.dataset.dated = row.dated ? "true" : "false";
                item.appendChild(factButton(row));
                node.appendChild(item);
            });
        });
        var ordered = rows.slice().sort(function (left, right) {
            if (left.dated && right.dated && left.dated !== right.dated) return left.dated < right.dated ? -1 : 1;
            if (left.dated && !right.dated) return -1;
            if (!left.dated && right.dated) return 1;
            return 0;
        });
        var timeline = document.getElementById("complaint-facts-timeline");
        if (timeline) {
            timeline.replaceChildren();
            ordered.forEach(function (row) {
                var item = document.createElement("li");
                item.dataset.dated = row.dated ? "true" : "false";
                item.appendChild(factButton(row));
                timeline.appendChild(item);
            });
        }
        (Array.isArray(projection.contradictions) ? projection.contradictions : []).forEach(function (conflict) {
            if (!links || !conflict) return;
            var item = document.createElement("li");
            item.dataset.role = "contradiction";
            var ids = Array.isArray(conflict.assertion_ids) ? conflict.assertion_ids.map(text).filter(Boolean) : [];
            item.textContent = ids.length ? ("Contradiction " + ids.join(" and ")) : "Unresolved contradiction";
            links.appendChild(item);
        });
        var graph = document.getElementById("complaint-facts-graph");
        if (graph) {
            graph.dataset.graphId = graphId;
            graph.dataset.role = "facts-graph";
        }
        var empty = document.getElementById("complaint-facts-empty");
        if (empty) empty.hidden = rows.length > 0 || host.dataset.state !== "ready";
        if (state.selectedKey) {
            var selected = rows.filter(function (row) { return row.key === state.selectedKey; })[0];
            if (selected) showProvenance(selected);
        }
    }

    function setMode(mode) {
        var host = root();
        if (!host) return;
        var next = mode === "timeline" || mode === "graph" ? mode : "list";
        state.mode = next;
        host.dataset.mode = next;
        var panes = {list: "complaint-facts-list", timeline: "complaint-facts-timeline", graph: "complaint-facts-graph"};
        Object.keys(panes).forEach(function (name) {
            var pane = document.getElementById(panes[name]);
            if (pane) pane.hidden = name !== next;
            var button = document.getElementById("complaint-facts-mode-" + name);
            if (button) {
                button.setAttribute("aria-pressed", name === next ? "true" : "false");
                button.tabIndex = name === next ? 0 : -1;
            }
        });
    }

    function paintState(name, message) {
        var host = root();
        if (!host) return;
        host.dataset.state = name;
        host.dataset.corroborationFabricated = "false";
        setText("complaint-facts-status", message);
        ["complaint-facts-empty", "complaint-facts-error", "complaint-facts-locked"].forEach(function (id) {
            var node = document.getElementById(id);
            if (!node) return;
            var show = (id === "complaint-facts-empty" && name === "empty") || (id === "complaint-facts-error" && (name === "error" || name === "unavailable")) || (id === "complaint-facts-locked" && name === "locked");
            node.hidden = !show;
        });
    }

    function applyPayload(projection, session) {
        state.projection = projection && typeof projection === "object" ? projection : null;
        state.session = session && typeof session === "object" ? session : null;
        var host = root();
        if (!host) return;
        if (!state.projection || state.projection.status === "unavailable") {
            state.projection = state.projection || {user_statements: [], adopted_evidence: []};
            host.dataset.graphId = "";
            host.dataset.graphCount = "0";
            paintState(state.projection.error === "unlock_needed" || state.projection.error === "key_unavailable" ? "locked" : "unavailable", "The factual projection is not available. Nothing was marked corroborated.");
            renderQuestions();
            renderFacts();
            return;
        }
        paintState("ready", "Facts loaded from the current interview projection.");
        renderQuestions();
        renderFacts();
        var offer = correctionOffer();
        if (Number.isSafeInteger(Number(offer.expected_session_revision))) state.sessionRevision = Number(offer.expected_session_revision);
        var graph = document.getElementById("complaint-facts-graph-revision");
        var sessionField = document.getElementById("complaint-facts-session-revision");
        if (graph && !graph.dataset.userEdited) graph.value = text(offer.expected_graph_revision);
        if (sessionField && !sessionField.dataset.userEdited) sessionField.value = offer.expected_session_revision === undefined || offer.expected_session_revision === null ? "" : String(offer.expected_session_revision);
    }

    async function refresh() {
        var host = root();
        var client = window.workspaceClient;
        var id = caseId();
        if (!host) return;
        if (!client || typeof client._request !== "function" || !id) {
            paintState("empty", "Sign in and open a case before loading facts.");
            return;
        }
        try {
            var projection = await client._request("/api/complaint-workspace/factual-graph?case_id=" + encodeURIComponent(id), {method: "GET"});
            var session = await client._request("/api/complaint-workspace/session?case_id=" + encodeURIComponent(id), {method: "GET"});
            if (caseId() !== id) return;
            applyPayload(projection, session);
            if (!state.projection || state.projection.status === "unavailable") return;
            if (!rowsFrom(projection).length) paintState("empty", "No recorded facts are on this projection. Unanswered questions stay listed.");
        } catch (error) {
            if (caseId() !== id) return;
            var code = text(error && (error.code || error.message));
            var locked = code === "unlock_needed" || code === "key_unavailable";
            applyPayload({status: "unavailable", error: code, user_statements: [], adopted_evidence: [], graph_id: ""}, state.session);
            paintState(locked ? "locked" : "unavailable", locked ? "The case key is locked. Facts stay hidden." : "The factual projection could not be read. No corroboration was added.");
        }
    }

    function mirrorCorrection(replacement, graphRevision, sessionRevision, target, actor) {
        var fields = {
            "factual-correction-replacement": replacement,
            "factual-correction-graph-revision": graphRevision,
            "factual-correction-session-revision": sessionRevision,
            "factual-correction-target": target,
            "factual-correction-actor": actor
        };
        Object.keys(fields).forEach(function (id) {
            var node = document.getElementById(id);
            if (node) node.value = fields[id];
        });
    }

    async function correct() {
        var status = document.getElementById("complaint-facts-edit-status");
        var client = window.workspaceClient;
        var row = selectedRow();
        var offer = correctionOffer();
        var replacementNode = document.getElementById("complaint-facts-replacement");
        var replacement = replacementNode ? text(replacementNode.value).trim() : "";
        var graphRevision = text((document.getElementById("complaint-facts-graph-revision") || {}).value).trim() || text(offer.expected_graph_revision);
        var sessionText = text((document.getElementById("complaint-facts-session-revision") || {}).value).trim();
        var sessionRevision = sessionText === "" ? Number(offer.expected_session_revision) : Number(sessionText);
        if (!Number.isSafeInteger(sessionRevision) && Number.isSafeInteger(state.sessionRevision)) sessionRevision = state.sessionRevision;
        var beforeGraph = text(state.projection && (state.projection.graph_id || (state.projection.status === "projected" ? state.projection.case_id : "")));
        if (status) {
            status.dataset.status = "";
            status.dataset.graphIdChanged = "false";
            status.dataset.corroborationFabricated = "false";
        }
        if (!row || !row.assertionId) {
            if (status) status.textContent = "Select a recorded assertion before correcting it.";
            return;
        }
        if (!replacement || !graphRevision || !Number.isSafeInteger(sessionRevision)) {
            if (status) status.textContent = "A correction needs the replacement and the expected graph and session revisions.";
            return;
        }
        if (!client || typeof client.submitCanonicalGraphCorrection !== "function") {
            if (status) status.textContent = "The interview owner is not available for this correction.";
            return;
        }
        var actor = text(offer.actor_principal_id);
        mirrorCorrection(replacement, graphRevision, String(sessionRevision), row.assertionId, actor);
        var userId = (client.caseContext && client.caseContext.tenant_id) || client.activePrincipalId || "";
        var result;
        try {
            result = await client.submitCanonicalGraphCorrection(userId, replacement, {
                question_id: row.assertionId,
                target_stable_id: row.assertionId,
                actor_principal_id: actor,
                expected_graph_revision: graphRevision,
                expected_session_revision: sessionRevision
            });
        } catch (error) {
            if (status) {
                status.dataset.status = "refused";
                status.dataset.graphIdChanged = "false";
                status.dataset.corroborationFabricated = "false";
                status.textContent = "The interview owner refused the correction. The prior fact stays.";
            }
            var hostOnError = root();
            if (hostOnError) hostOnError.dataset.graphIdChanged = "false";
            return;
        }
        var accepted = Boolean(result && result.accepted === true);
        var graphField = document.getElementById("complaint-facts-graph-revision");
        var sessionField = document.getElementById("complaint-facts-session-revision");
        if (graphField) delete graphField.dataset.userEdited;
        if (sessionField) delete sessionField.dataset.userEdited;
        if (Number.isSafeInteger(sessionRevision)) state.sessionRevision = sessionRevision;
        await refresh();
        var host = root();
        if (host && beforeGraph && host.dataset.graphId && host.dataset.graphId !== beforeGraph) {
            host.dataset.graphIdChanged = "true";
        } else if (host) {
            host.dataset.graphIdChanged = "false";
        }
        if (status) {
            status.dataset.status = accepted ? "applied" : "refused";
            status.dataset.graphIdChanged = host ? host.dataset.graphIdChanged : "false";
            status.dataset.corroborationFabricated = "false";
            status.textContent = accepted ? "The interview owner recorded the correction on the current graph." : ("The interview owner refused the correction (" + text((result && result.conflict) || "refused") + "). The prior fact stays.");
        }
    }

    async function unknown() {
        var status = document.getElementById("complaint-facts-edit-status");
        var questions = questionsFrom(state.session).filter(function (question) { return question.kind === "pending"; });
        if (!questions.length || typeof window.answerAdaptiveInquiry !== "function") {
            if (status) status.textContent = "There is no unanswered mediator question to mark unknown.";
            return;
        }
        var before = questions.map(function (question) { return question.id; });
        await window.answerAdaptiveInquiry("unknown");
        await refresh();
        var after = questionsFrom(state.session);
        var host = root();
        if (host) host.dataset.corroborationFabricated = "false";
        if (status) {
            status.dataset.gapPreserved = "true";
            status.dataset.droppedQuestions = before.some(function (id) {
                return !after.some(function (question) { return question.id === id; }) && !after.some(function (question) { return question.kind === "pending" || question.kind === "gap"; });
            }) ? "true" : "false";
            status.textContent = status.dataset.droppedQuestions === "true"
                ? "The unknown answer did not keep an unanswered question."
                : "I don't know was sent through the interview. Unanswered questions remain, and nothing was marked corroborated.";
        }
    }

    function bind() {
        var host = root();
        if (!host || host.dataset.bound === "true") return;
        host.dataset.bound = "true";
        host.dataset.mode = "list";
        host.dataset.graphCount = "0";
        host.dataset.graphWrites = "0";
        host.dataset.corroborationFabricated = "false";
        setMode("list");
        host.addEventListener("click", function (event) {
            var button = event.target.closest("button");
            if (!button || !host.contains(button)) return;
            if (button.dataset.factsMode) {
                setMode(button.dataset.factsMode);
                return;
            }
            if (button.id === "complaint-facts-refresh") refresh();
            else if (button.id === "complaint-facts-correct") correct();
            else if (button.id === "complaint-facts-unknown") unknown();
            else if (button.id === "complaint-facts-close") {
                var panel = document.getElementById("complaint-facts-provenance");
                if (panel) panel.hidden = true;
                var selected = host.querySelector("[data-role='fact'][aria-pressed='true']");
                if (selected) selected.focus();
            }
        });
        ["complaint-facts-graph-revision", "complaint-facts-session-revision"].forEach(function (id) {
            var field = document.getElementById(id);
            if (!field) return;
            field.addEventListener("input", function () { field.dataset.userEdited = "true"; });
        });
        host.addEventListener("keydown", function (event) {
            var button = event.target.closest("[data-facts-mode]");
            if (!button || event.altKey || event.ctrlKey || event.metaKey) return;
            var modes = ["list", "timeline", "graph"];
            var index = modes.indexOf(button.dataset.factsMode);
            if (index < 0) return;
            if (event.key === "ArrowRight" || event.key === "ArrowDown") index += 1;
            else if (event.key === "ArrowLeft" || event.key === "ArrowUp") index -= 1;
            else if (event.key === "Home") index = 0;
            else if (event.key === "End") index = modes.length - 1;
            else return;
            event.preventDefault();
            var mode = modes[(index + modes.length) % modes.length];
            setMode(mode);
            var next = document.getElementById("complaint-facts-mode-" + mode);
            if (next) next.focus();
        });
        document.addEventListener("click", function (event) {
            var task = event.target.closest && event.target.closest("[data-case-task='facts']");
            if (task) refresh();
        });
        paintState("empty", "Facts have not been loaded.");
    }

    window.complaintFacts = {
        refresh: refresh,
        setMode: setMode,
        render: function (projection, session) {
            applyPayload(projection, session);
            setMode(state.mode || "list");
        }
    };

    if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", bind);
    else bind();
})();
