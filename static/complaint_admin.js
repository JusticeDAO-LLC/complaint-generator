(function () {
    var csrf = "";
    var signedIn = false;

    function $(id) { return document.getElementById(id); }

    function setError(text) { $("admin-error").textContent = text || ""; }

    function setStatus(text) { $("admin-status").textContent = text || ""; }

    function setWorkspaceState(state, text) {
        var directory = $("directory");
        if (directory) directory.dataset.state = state;
        var node = $("workspace-state");
        if (node) node.textContent = text || "";
    }

    function lockWorkspace() {
        signedIn = false;
        csrf = "";
        $("admin-auth-status").textContent = "Signed out";
        $("directory").hidden = true;
        $("operations-panel").hidden = true;
        $("audit-panel").hidden = true;
        setWorkspaceState("locked", "Sign in to load the operational directory.");
    }

    async function call(method, path, body) {
        var options = { method: method, credentials: "same-origin", headers: {} };
        if (csrf) options.headers["x-csrf-token"] = csrf;
        if (body !== undefined) {
            options.headers["content-type"] = "application/json";
            options.body = JSON.stringify(body);
        }
        var response = await fetch(path, options);
        var payload = {};
        try { payload = await response.json(); } catch (error) { payload = {}; }
        if (response.status === 401) lockWorkspace();
        if (!response.ok) {
            var failure = new Error(payload.error || "request_failed");
            failure.payload = payload;
            throw failure;
        }
        return payload;
    }

    function filterQuery() {
        var params = new URLSearchParams();
        [
            ["principal_id", $("principal-query").value.trim()],
            ["account_kind", $("filter-account-kind").value],
            ["status", $("filter-status").value],
            ["assignment", $("filter-assignment").value],
            ["assignment_status", $("filter-assignment-status").value],
            ["min_assigned_cases", $("filter-min-cases").value.trim()],
            ["audit_right", $("filter-audit").value],
            ["case_id", $("filter-case-id").value.trim()]
        ].forEach(function (pair) {
            if (pair[1] && pair[1] !== "any") params.set(pair[0], pair[1]);
        });
        var query = params.toString();
        return "/api/admin/workspace" + (query ? "?" + query : "");
    }

    function renderSummary(payload) {
        var host = $("analysis-summary");
        host.replaceChildren();
        var caseCounts = payload.case_counts || {};
        var assignment = (payload.assignment_status || {}).counts || {};
        var review = payload.content_review || {};
        var rows = [
            ["Matching accounts", payload.filtered_account_count],
            ["Complainants", (payload.role_counts || {}).complainant],
            ["Lawyers", (payload.role_counts || {}).lawyer],
            ["Operational admins", (payload.role_counts || {}).operational_admin],
            ["Active", (payload.status_counts || {}).active],
            ["Disabled", (payload.status_counts || {}).disabled],
            ["Sealed owner indexes", caseCounts.sealed_owner_indexes],
            ["Assigned cases", caseCounts.assigned_case_count],
            ["Pending assignments", assignment.pending],
            ["Accepted assignments", assignment.accepted],
            ["Content review exposed", review.exposed],
            ["Explicit case grant required", review.requires_explicit_case_grant]
        ];
        rows.forEach(function (pair) {
            var list = document.createElement("dl");
            var term = document.createElement("dt");
            term.textContent = pair[0];
            var detail = document.createElement("dd");
            detail.textContent = pair[1] === null || pair[1] === undefined ? "unobserved" : String(pair[1]);
            list.appendChild(term);
            list.appendChild(detail);
            host.appendChild(list);
        });
    }

    function renderAccounts(payload) {
        var rows = $("account-rows");
        rows.replaceChildren();
        var accounts = payload.accounts || [];
        accounts.forEach(function (account) {
            var tr = document.createElement("tr");
            tr.dataset.principalId = account.principal_id;
            ["principal_id", "roles", "status", "assigned_case_count", "revision", "audit_right"].forEach(function (field) {
                var cell = document.createElement("td");
                var value = account[field];
                cell.textContent = Array.isArray(value) ? value.join(",") : (value === null || value === undefined ? "unobserved" : String(value));
                tr.appendChild(cell);
            });
            var actions = document.createElement("td");
            var kind = document.createElement("select");
            kind.setAttribute("aria-label", "Server role for " + account.principal_id);
            ["complainant", "lawyer", "operational_admin"].forEach(function (name) {
                var option = document.createElement("option");
                option.value = name;
                option.textContent = name;
                if ((account.roles || [])[0] === name) option.selected = true;
                kind.appendChild(option);
            });
            var apply = document.createElement("button");
            apply.type = "button";
            apply.textContent = "Set server role";
            apply.addEventListener("click", function () {
                setWorkspaceState("loading", "Saving the server role.");
                call("POST", "/api/admin/accounts/" + account.principal_id + "/role", {
                    account_kind: kind.value,
                    expected_revision: account.revision
                }).then(loadWorkspace).catch(function (error) {
                    setWorkspaceState("error", error.message);
                    setError(error.message);
                });
            });
            var disable = document.createElement("button");
            disable.type = "button";
            disable.textContent = account.status === "active" ? "Disable account" : "Restore account";
            disable.addEventListener("click", function () {
                setWorkspaceState("loading", "Saving account status.");
                call("POST", "/api/admin/accounts/" + account.principal_id + "/status", {
                    status: account.status === "active" ? "disabled" : "active",
                    expected_revision: account.revision
                }).then(loadWorkspace).catch(function (error) {
                    setWorkspaceState("error", error.message);
                    setError(error.message);
                });
            });
            actions.appendChild(kind);
            actions.appendChild(apply);
            actions.appendChild(disable);
            tr.appendChild(actions);
            rows.appendChild(tr);
        });
        $("empty-accounts").hidden = accounts.length !== 0;
        $("admin-limitations").textContent = (payload.limitations || []).join(" ");
        $("audit-panel").hidden = false;
        $("operations-panel").hidden = false;
        renderSummary(payload);
        if (payload.state === "empty") {
            setWorkspaceState("empty", "No accounts match these filters.");
        } else if (payload.state === "assignment_unobserved") {
            setWorkspaceState("assignment_unobserved", "Assignment records are unobserved, so assignment filters returned no rows.");
        } else if (payload.state === "error") {
            setWorkspaceState("error", "The operational directory could not be loaded.");
        } else {
            setWorkspaceState("ready", "Operational directory loaded. Case content stays withheld.");
        }
    }

    function renderOperations(payload) {
        var counts = $("operations-counts");
        counts.replaceChildren();
        var caseCounts = payload.case_counts || {};
        var assignment = (payload.assignment_status || {}).counts || {};
        var storage = payload.storage || {};
        var workers = payload.workers || {};
        var rows = [
            ["Sealed owner indexes", caseCounts.sealed_owner_indexes],
            ["Assigned cases", caseCounts.assigned_case_count],
            ["Exact case count", caseCounts.exact_case_count_available],
            ["Envelopes opened", caseCounts.envelopes_opened],
            ["Pending assignments", assignment.pending],
            ["Accepted assignments", assignment.accepted],
            ["Storage readiness", storage.readiness],
            ["Durable receipts", storage.durable_count],
            ["Unresolved receipts", storage.unresolved_count],
            ["Worker state", workers.state],
            ["Worker queue", workers.queue_depth],
            ["Case content granted", payload.case_content_granted],
            ["Owner impersonated", payload.impersonated_case_owner]
        ];
        rows.forEach(function (pair) {
            var term = document.createElement("dt");
            term.textContent = pair[0];
            var detail = document.createElement("dd");
            detail.textContent = pair[1] === null || pair[1] === undefined ? "unobserved" : String(pair[1]);
            counts.appendChild(term);
            counts.appendChild(detail);
        });
        var codes = (payload.support_diagnostics || []).map(function (item) {
            return item.code + ":" + item.count;
        });
        $("operations-diagnostics").textContent = codes.join(" ");
    }

    function loadOperations() {
        return call("GET", "/api/admin/operations").then(renderOperations);
    }

    function loadWorkspace() {
        setError("");
        setWorkspaceState("loading", "Loading operational accounts.");
        return call("GET", filterQuery()).then(renderAccounts).catch(function (error) {
            $("account-rows").replaceChildren();
            $("analysis-summary").replaceChildren();
            $("empty-accounts").hidden = true;
            setWorkspaceState("error", error.message || "request_failed");
            setError(error.message || "request_failed");
            throw error;
        });
    }

    $("admin-login").addEventListener("submit", function (event) {
        event.preventDefault();
        setError("");
        setWorkspaceState("loading", "Checking the credential.");
        fetch("/api/complaint-workspace/auth/login", {
            method: "POST",
            credentials: "same-origin",
            headers: { "content-type": "application/json" },
            body: JSON.stringify({ credential: $("admin-credential").value })
        }).then(function (response) { return response.json().then(function (payload) { return { response: response, payload: payload }; }); })
          .then(function (result) {
              $("admin-credential").value = "";
              if (!result.response.ok) {
                  setWorkspaceState("locked", "Sign in required.");
                  throw new Error(result.payload.error || "login_failed");
              }
              csrf = result.payload.csrf_token || "";
              signedIn = true;
              $("admin-auth-status").textContent = "Signed in";
              $("directory").hidden = false;
              $("operations-panel").hidden = false;
              return loadWorkspace().then(loadOperations);
          }).catch(function (error) { setError(error.message || "login_failed"); });
    });

    $("workspace-filters").addEventListener("submit", function (event) {
        event.preventDefault();
        setError("");
        if (!signedIn) {
            setWorkspaceState("locked", "Sign in to load the operational directory.");
            return;
        }
        loadWorkspace().catch(function () {});
    });

    $("provision-account").addEventListener("submit", function (event) {
        event.preventDefault();
        setError("");
        setWorkspaceState("loading", "Provisioning the account.");
        call("POST", "/api/admin/accounts", { account_kind: $("account-kind").value })
            .then(loadWorkspace)
            .catch(function (error) {
                setWorkspaceState("error", error.message);
                setError(error.message);
            });
    });

    $("load-operations").addEventListener("click", function () {
        setError("");
        loadOperations().catch(function (error) { setError(error.message); });
    });

    $("operations-incident").addEventListener("submit", function (event) {
        event.preventDefault();
        setError("");
        call("POST", "/api/admin/operations/incidents", {
            scope: $("incident-scope").value,
            code: $("incident-code").value
        }).then(function (payload) {
            var incident = payload.incident || {};
            $("incident-result").textContent = [
                incident.code,
                incident.scope,
                "impersonated=" + incident.impersonated_case_owner,
                "content=" + incident.case_content_granted
            ].join(" ");
            renderOperations(payload);
        }).catch(function (error) { setError(error.message); });
    });

    function ensureContentAccess() {
        var panel = $("audit-panel");
        if (!panel || $("content-access-decision")) {
            return;
        }
        var form = document.createElement("form");
        form.id = "content-access-decision";
        form.innerHTML = [
            "<label for=\"content-access-case\">Case</label>",
            "<input id=\"content-access-case\" name=\"case_id\" autocomplete=\"off\">",
            "<label for=\"content-access-subject\">Subject</label>",
            "<input id=\"content-access-subject\" name=\"subject_principal_id\" autocomplete=\"off\">",
            "<label for=\"content-access-purpose\">Purpose</label>",
            "<select id=\"content-access-purpose\" name=\"purpose\">",
            "<option value=\"operational_administration\">operational administration</option>",
            "<option value=\"legal_content_review\">legal content review</option>",
            "<option value=\"assignment_observation\">assignment observation</option>",
            "</select>",
            "<button type=\"submit\">Record content-access decision</button>"
        ].join("");
        var result = document.createElement("p");
        result.id = "content-access-result";
        result.setAttribute("role", "status");
        var reload = document.createElement("button");
        reload.id = "load-content-access";
        reload.type = "button";
        reload.textContent = "Load content-access audit";
        var list = document.createElement("ol");
        list.id = "content-access-events";
        panel.appendChild(form);
        panel.appendChild(result);
        panel.appendChild(reload);
        panel.appendChild(list);
        form.addEventListener("submit", function (event) {
            event.preventDefault();
            setError("");
            result.textContent = "";
            if (!signedIn) {
                setWorkspaceState("locked", "Sign in before recording a content-access decision.");
                return;
            }
            setWorkspaceState("loading", "Recording the content-access decision.");
            call("POST", "/api/admin/content-access", {
                case_id: $("content-access-case").value,
                subject_principal_id: $("content-access-subject").value,
                purpose: $("content-access-purpose").value
            }).then(function (payload) {
                var decision = payload.decision || {};
                result.textContent = [
                    decision.purpose,
                    decision.decision,
                    decision.reason,
                    "content=" + decision.content_permitted,
                    "key_bypassed=" + decision.key_bypassed,
                    decision.tenant_id,
                    decision.case_id,
                    decision.actor_principal_id
                ].join(" ");
                setWorkspaceState("ready", "Content-access decision recorded. Case content stays withheld.");
                return loadContentAccess();
            }).catch(function (error) {
                result.textContent = "";
                setWorkspaceState("error", error.message || "content_access_denied");
                setError(error.message || "content_access_denied");
                loadContentAccess().catch(function () {});
            });
        });
        reload.addEventListener("click", function () {
            setError("");
            loadContentAccess().catch(function (error) { setError(error.message); });
        });
    }

    function renderContentAccess(payload) {
        var list = $("content-access-events");
        if (!list) {
            return;
        }
        list.replaceChildren();
        (payload.decisions || []).forEach(function (item) {
            var line = document.createElement("li");
            line.textContent = [
                item.at,
                item.actor_principal_id,
                item.subject_principal_id,
                item.purpose,
                item.decision,
                item.reason,
                item.tenant_id,
                item.case_id,
                item.assignment_status,
                "content=" + item.content_permitted,
                "key_bypassed=" + item.key_bypassed,
                item.authority
            ].join(" ");
            list.appendChild(line);
        });
    }

    function loadContentAccess() {
        return call("GET", "/api/admin/content-access").then(renderContentAccess);
    }

    $("load-audit").addEventListener("click", function () {
        setError("");
        call("GET", "/api/admin/audit").then(function (payload) {
            var list = $("audit-events");
            list.replaceChildren();
            (payload.events || []).forEach(function (item) {
                var line = document.createElement("li");
                line.textContent = [
                    item.action,
                    item.subject_principal_id,
                    item.detail,
                    item.revision,
                    item.tenant_id || "",
                    item.case_id || "",
                    item.decision || ""
                ].join(" ");
                list.appendChild(line);
            });
        }).catch(function (error) { setError(error.message); });
    });

    ensureContentAccess();

    setWorkspaceState("locked", "Sign in to load the operational directory.");
})();
