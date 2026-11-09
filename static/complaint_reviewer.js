/* Scoped lawyer review queue. Controls use server labels, never grant ids. */
(function () {
    var pageNumber = 1;
    var request = null;
    var applied = null;
    var workspaceRequest = null;
    var workspaceGeneration = 0;
    var issuedReview = null;

    function node(id) {
        return document.getElementById(id);
    }

    function abort() {
        if (request) request.abort();
        request = new AbortController();
        return request;
    }

    function filters() {
        return {
            state: node("lawyer-queue-state").value || "all",
            sort: node("lawyer-queue-sort").value || "priority",
            q: node("lawyer-queue-query").value || "",
            page: String(pageNumber),
            page_size: "2",
            direction: node("lawyer-queue-sort").value === "priority" ? "desc" : "asc"
        };
    }

    function queryString(values) {
        var parts = [];
        Object.keys(values).forEach(function (key) {
            parts.push(encodeURIComponent(key) + "=" + encodeURIComponent(values[key]));
        });
        return parts.join("&");
    }

    function setEmpty(text, state) {
        var section = node("lawyer-review-queue");
        var empty = node("lawyer-queue-empty");
        var list = node("lawyer-queue-list");
        section.dataset.state = state;
        list.replaceChildren();
        empty.hidden = false;
        empty.textContent = text;
        node("lawyer-queue-page").textContent = "Page 0 of 0";
        node("lawyer-queue-prev").disabled = true;
        node("lawyer-queue-next").disabled = true;
    }

    function render(payload) {
        var section = node("lawyer-review-queue");
        var list = node("lawyer-queue-list");
        var empty = node("lawyer-queue-empty");
        var status = node("lawyer-queue-status");
        status.hidden = true;
        list.replaceChildren();
        var items = payload.items || [];
        if (!items.length) {
            section.dataset.state = "empty";
            empty.hidden = false;
            empty.textContent = payload.empty_label || "No assigned cases match this queue.";
        } else {
            section.dataset.state = "ready";
            empty.hidden = true;
        }
        items.forEach(function (item) {
            var row = document.createElement("li");
            row.dataset.state = item.state || "";
            row.dataset.caseId = item.case_id || "";
            var button = document.createElement("button");
            button.type = "button";
            button.className = "lawyer-queue-open";
            button.textContent = (item.control && item.control.label) || item.display_label || item.state_label || "Assigned case";
            button.addEventListener("click", function () {
                node("lawyer-queue-status").hidden = false;
                node("lawyer-queue-status").textContent = item.state_label + ". " + item.display_label;
                section.dataset.selectedState = item.state || "";
                if (item.state === "pending" && window.complaintInvitations) {
                    window.complaintInvitations.acceptForCase(item.case_id);
                    return;
                }
                if (item.state === "authorized") openIssued(issuedReview, item.case_id);
                else clearWorkspace(item.state_label, item.state || "locked");
            });
            row.appendChild(button);
            var meta = document.createElement("p");
            meta.textContent = item.priority_label + " priority. " + item.state_label + ". " + item.scope_label + ".";
            row.appendChild(meta);
            (item.review_tasks || []).forEach(function (task) {
                var taskNode = document.createElement("p");
                taskNode.className = "lawyer-queue-task";
                taskNode.textContent = "Review task: " + task.label + " (" + task.status_label + ")";
                row.appendChild(taskNode);
            });
            (item.pending_owner_actions || []).forEach(function (action) {
                var actionNode = document.createElement("p");
                actionNode.className = "lawyer-queue-owner-action";
                actionNode.textContent = "Waiting on owner: " + action.label;
                row.appendChild(actionNode);
            });
            list.appendChild(row);
        });
        var page = payload.page || {};
        var number = page.number || 0;
        var count = page.page_count || 0;
        node("lawyer-queue-page").textContent = "Page " + number + " of " + count;
        node("lawyer-queue-prev").disabled = number <= 1;
        node("lawyer-queue-next").disabled = !count || number >= count;
        pageNumber = number || 1;
    }

    async function load(options) {
        var section = node("lawyer-review-queue");
        if (!section) return;
        var current = abort();
        var status = node("lawyer-queue-status");
        status.hidden = false;
        status.textContent = "Loading the review queue.";
        section.dataset.state = "loading";
        var values = filters();
        var path = "/api/cases/lawyer-queue";
        if (!(options && options.bare)) path += "?" + queryString(values);
        try {
            var response = await fetch(path, {
                credentials: "same-origin",
                headers: {accept: "application/json"},
                signal: current.signal
            });
            var payload = await response.json();
            if (current.signal.aborted) return;
            if (options && options.current && options.generation !== options.current()) return;
            if (!response.ok) {
                setEmpty(payload && payload.error === "lawyer_queue_unavailable"
                    ? "The review queue is unavailable."
                    : "The review queue could not be loaded.", payload && payload.error === "unauthenticated" ? "locked" : "error");
                status.hidden = true;
                return;
            }
            if (payload.role_alone_grants_cases !== false || payload.unassigned_complaints_included !== false) {
                setEmpty("The review queue could not be loaded.", "error");
                return;
            }
            render(payload);
            if (issuedReview && issuedReview.case_id) openIssued(issuedReview, issuedReview.case_id);
        } catch (error) {
            if (error && error.name === "AbortError") return;
            if (options && options.current && options.generation !== options.current()) return;
            setEmpty("The review queue could not be loaded.", "error");
        }
    }

    function workspaceSection() {
        var section = node("lawyer-review-workspace");
        if (section) return section;
        var queue = node("lawyer-review-queue");
        if (!queue) return null;
        section = document.createElement("section");
        section.id = "lawyer-review-workspace";
        section.dataset.state = "empty";
        section.dataset.plaintext = "cleared";
        section.setAttribute("aria-labelledby", "review-workspace-title");
        var title = document.createElement("h2");
        title.id = "review-workspace-title";
        title.textContent = "Evidence, facts, law, and draft";
        section.appendChild(title);
        var status = document.createElement("p");
        status.id = "review-workspace-status";
        status.setAttribute("role", "status");
        section.appendChild(status);
        var scope = document.createElement("p");
        scope.id = "review-workspace-scope";
        section.appendChild(scope);
        ["evidence", "facts", "law", "draft"].forEach(function (name) {
            var panel = document.createElement("section");
            panel.id = "review-" + name;
            var heading = document.createElement("h3");
            heading.textContent = name.charAt(0).toUpperCase() + name.slice(1);
            panel.appendChild(heading);
            var list = document.createElement("ul");
            panel.appendChild(list);
            var empty = document.createElement("p");
            empty.className = "review-panel-empty";
            empty.hidden = true;
            panel.appendChild(empty);
            section.appendChild(panel);
        });
        queue.insertAdjacentElement("afterend", section);
        return section;
    }

    function clearWorkspace(message, state) {
        workspaceGeneration += 1;
        if (workspaceRequest) workspaceRequest.abort();
        workspaceRequest = null;
        var section = node("lawyer-review-workspace");
        if (!section) return;
        section.dataset.state = state || "cleared";
        section.dataset.plaintext = "cleared";
        var status = node("review-workspace-status");
        status.textContent = message || "Review plaintext was cleared.";
        node("review-workspace-scope").textContent = "";
        ["evidence", "facts", "law", "draft"].forEach(function (name) {
            var panel = node("review-" + name);
            panel.querySelector("ul").replaceChildren();
            var empty = panel.querySelector(".review-panel-empty");
            empty.hidden = false;
            empty.textContent = "Review plaintext was cleared.";
        });
    }

    function paintWorkspace(payload) {
        var section = workspaceSection();
        section.dataset.state = "ready";
        section.dataset.plaintext = "shown";
        var status = node("review-workspace-status");
        status.textContent = "Review workspace is open for the accepted scope.";
        var labels = payload.scope_labels || [];
        node("review-workspace-scope").textContent = labels.length ? "Accepted scope: " + labels.join(", ") + "." : "";
        var panels = {
            evidence: {rows: payload.evidence || [], empty: payload.evidence_empty_label},
            facts: {rows: payload.facts || [], empty: payload.facts_empty_label},
            law: {rows: payload.law || [], empty: payload.law_empty_label}
        };
        Object.keys(panels).forEach(function (name) {
            var panel = node("review-" + name);
            var list = panel.querySelector("ul");
            list.replaceChildren();
            var empty = panel.querySelector(".review-panel-empty");
            var rows = panels[name].rows;
            if (!rows.length) {
                empty.hidden = false;
                empty.textContent = panels[name].empty || "Nothing is available in this panel.";
                return;
            }
            empty.hidden = true;
            empty.textContent = "";
            rows.forEach(function (row) {
                var item = document.createElement("li");
                item.textContent = row.text || "";
                list.appendChild(item);
            });
        });
        var draftPanel = node("review-draft");
        var draftList = draftPanel.querySelector("ul");
        var draftEmpty = draftPanel.querySelector(".review-panel-empty");
        draftList.replaceChildren();
        var draft = payload.draft || {};
        if (draft.text) {
            draftEmpty.hidden = true;
            draftEmpty.textContent = "";
            var item = document.createElement("li");
            item.textContent = draft.text;
            draftList.appendChild(item);
        } else {
            draftEmpty.hidden = false;
            draftEmpty.textContent = draft.empty_label || "No draft revision is shared with this review.";
        }
    }

    function issuedFromSearch(search) {
        var params = new URLSearchParams(search.charAt(0) === "?" ? search.slice(1) : search);
        var caseId = params.get("case_id") || "";
        if (!caseId || !params.get("tenant_id") || !params.get("resource_id") || !params.get("expected_revision") || !params.get("expected_membership_revision")) {
            return null;
        }
        return {
            case_id: caseId,
            tenant_id: params.get("tenant_id"),
            resource_id: params.get("resource_id"),
            expected_revision: params.get("expected_revision"),
            expected_membership_revision: params.get("expected_membership_revision")
        };
    }

    async function openIssued(issued, caseId) {
        var section = workspaceSection();
        var generation = workspaceGeneration + 1;
        workspaceGeneration = generation;
        if (workspaceRequest) workspaceRequest.abort();
        workspaceRequest = new AbortController();
        var current = workspaceRequest;
        if (!issued || !issued.case_id || (caseId && issued.case_id !== caseId)) {
            clearWorkspace("Open the issued review link for this case.", "unavailable");
            return;
        }
        section.dataset.state = "loading";
        section.dataset.plaintext = "cleared";
        node("review-workspace-status").textContent = "Opening the issued review workspace.";
        var query = queryString({
            tenant_id: issued.tenant_id,
            case_id: issued.case_id,
            resource_id: issued.resource_id,
            expected_revision: issued.expected_revision,
            expected_membership_revision: issued.expected_membership_revision
        });
        try {
            var response = await fetch("/api/legal-analysis/" + encodeURIComponent(issued.case_id) + "/lawyer-review-workspace?" + query, {
                credentials: "same-origin",
                headers: {accept: "application/json"},
                signal: current.signal
            });
            var payload = {};
            try {
                payload = await response.json();
            } catch (parseError) {
                payload = {};
            }
            if (current.signal.aborted || generation !== workspaceGeneration) return;
            if (!response.ok || !payload || payload.status !== "ready" || payload.plaintext_cleared === true) {
                clearWorkspace(payload && payload.error === "review_key_locked"
                    ? "The review key is locked."
                    : "This review grant does not allow the workspace.", payload && payload.plaintext_cleared ? "denied" : "denied");
                return;
            }
            if (payload.case_id !== issued.case_id || payload.owner_wallet_required !== false) {
                clearWorkspace("This review grant does not allow the workspace.", "denied");
                return;
            }
            paintWorkspace(payload);
        } catch (error) {
            if (error && error.name === "AbortError") return;
            if (generation !== workspaceGeneration) return;
            clearWorkspace("This review grant does not allow the workspace.", "error");
        }
    }

    function rememberIssued(search) {
        issuedReview = issuedFromSearch(search || "");
        return issuedReview;
    }

    function clear() {
        if (request) request.abort();
        request = null;
        pageNumber = 1;
        applied = null;
        clearWorkspace("Review plaintext was cleared.", "cleared");
        if (!node("lawyer-review-queue")) return;
        setEmpty("No assigned cases match this queue.", "empty");
        node("lawyer-queue-status").hidden = true;
        node("lawyer-queue-status").textContent = "";
    }

    var form = node("lawyer-queue-filters");
    if (form) {
        form.addEventListener("submit", function (event) {
            event.preventDefault();
            pageNumber = 1;
            applied = filters();
            load();
        });
        node("lawyer-queue-prev").addEventListener("click", function () {
            if (pageNumber > 1) {
                pageNumber -= 1;
                load();
            }
        });
        node("lawyer-queue-next").addEventListener("click", function () {
            pageNumber += 1;
            load();
        });
    }

    rememberIssued(window.location.search);
    window.complaintReviewer = {
        load: load,
        clear: clear,
        filters: filters,
        openIssued: function (search, caseId) {
            var issued = typeof search === "string" ? rememberIssued(search) : search;
            if (issued) issuedReview = issued;
            return openIssued(issuedReview, caseId || (issuedReview && issuedReview.case_id));
        },
        clearWorkspace: clearWorkspace
    };
}());
