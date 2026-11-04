/* Scoped lawyer review queue. Controls use server labels, never grant ids. */
(function () {
    var pageNumber = 1;
    var request = null;
    var applied = null;

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
        } catch (error) {
            if (error && error.name === "AbortError") return;
            if (options && options.current && options.generation !== options.current()) return;
            setEmpty("The review queue could not be loaded.", "error");
        }
    }

    function clear() {
        if (request) request.abort();
        request = null;
        pageNumber = 1;
        applied = null;
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

    window.complaintReviewer = {load: load, clear: clear, filters: filters};
}());
