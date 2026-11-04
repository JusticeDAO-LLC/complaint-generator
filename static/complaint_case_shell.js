(function () {
    "use strict";

    var TASKS = [
        ["overview", "Overview"],
        ["mediator", "Mediator"],
        ["evidence", "Evidence"],
        ["facts", "Facts and timeline"],
        ["legal", "Legal requirements"],
        ["draft", "Draft"],
        ["team", "Team/messages"]
    ];

    var state = {
        authenticated: false,
        principalId: "",
        roles: [],
        relationship: "none",
        caseId: "",
        caseLabel: "",
        privacy: "Privacy state is unavailable until you sign in",
        stage: "Sign-in required",
        next: "Sign in",
        nextKind: "sign-in",
        session: null,
        assignment: null,
        gaps: [],
        catalog: [],
        binding: null
    };
    var PRESENTATION_MODES = ["chat-only", "chat-plus-context", "full-workspace"];
    var presentationMode = "full-workspace";
    var PRIMARY = {overview: true, mediator: true, evidence: true, draft: true};
    var refreshToken = 0;
    var refreshTimer = 0;
    var retiringWorkspace = false;
    var activeController = null;
    var committed = {principalId: "", caseId: "", access: ""};

    function text(value) {
        return value === undefined || value === null ? "" : String(value);
    }

    function ordinaryFlow() {
        var params = new URLSearchParams(window.location.search || "");
        var query = text(params.get("shell_mode") || params.get("app_shell_mode")).toLowerCase();
        if (query === "operator" || query === "client") return query !== "operator";
        var bodyMode = document.body && document.body.dataset ? text(document.body.dataset.workspaceShellMode) : "";
        if (bodyMode === "operator") return false;
        try {
            if (window.localStorage && window.localStorage.getItem("complaintGenerator.shellMode") === "operator") return false;
        } catch (error) {
            return true;
        }
        return true;
    }

    function applyAudience() {
        document.body.dataset.caseTaskFlow = ordinaryFlow() ? "ordinary" : "operator";
        if (document.body.dataset.caseTaskFlow !== "ordinary") return;
        var nodes = document.querySelectorAll("a, button, summary, span, h2, h3");
        Array.prototype.forEach.call(nodes, function (node) {
            if (node.closest("#complaint-case-shell")) return;
            var sample = text(node.textContent).replace(/\s+/g, " ").trim();
            if (sample.length > 160) return;
            if (/\b(CLI|MCP|SDK playground|UX Audit|debug panel|Developer tools)\b/i.test(sample)) {
                node.setAttribute("data-case-shell-diagnostic", "true");
            }
        });
        ["integrations", "ux-review"].forEach(function (name) {
            var panel = document.querySelector('[data-tab-panel="' + name + '"]');
            if (panel) panel.setAttribute("data-case-shell-diagnostic", "true");
        });
    }

    function shellHost() {
        return document.getElementById("complaint-case-shell");
    }

    function mount() {
        var host = shellHost();
        if (!host || host.dataset.mounted === "true") return host;
        host.dataset.mounted = "true";
        host.className = "case-shell";
        host.setAttribute("aria-label", "Case workspace");
        var nav = TASKS.map(function (item) {
            var tier = PRIMARY[item[0]] ? "primary" : "secondary";
            return '<button type="button" class="case-shell__task" data-case-task="' + item[0] + '" data-tier="' + tier + '">' + item[1] + "</button>";
        }).join("");
        var panels = TASKS.map(function (item) {
            return '<section class="case-shell__panel" data-case-panel="' + item[0] + '" hidden><h3>' + item[1] + '</h3><div class="case-shell__panel-body"></div></section>';
        }).join("");
        host.innerHTML = ''
            + '<p class="case-shell__access"><a href="/cases">My cases</a> <a href="/cases#notifications">Inbox</a> <a href="#complaint-case-shell-privacy">Account/privacy</a></p>'
            + '<section id="complaint-entry" data-entry="first-run" data-ready-badge="false" data-browser-cache="ignored" data-consent="visible-not-granted" aria-labelledby="complaint-entry-title">'
            + '<h2 id="complaint-entry-title">Begin a complaint</h2>'
            + '<p id="complaint-entry-detail">Sign in and choose the case from the catalog. If its keys are locked, an authorized local key owner must unlock them before this page can resume the saved server question.</p>'
            + '<p id="complaint-entry-boundary" role="status">Sign in to begin or to open a case you already have.</p>'
            + '<p id="complaint-entry-question" hidden></p>'
            + '<p id="complaint-entry-consent">This page does not grant remote processing. Purpose-scoped choices stay with the case privacy controls.</p>'
            + '<p><button type="button" id="complaint-entry-begin">Begin a complaint</button></p>'
            + '<div id="complaint-entry-key-access">'
            + '<button type="button" id="complaint-entry-check-key">Check private key access / resume</button>'
            + '<p id="complaint-entry-key-result" role="status"></p>'
            + '</div>'
            + '</section>'
            + '<div class="case-shell__identity">'
            + '<p><span>Case</span> <strong id="complaint-case-shell-case" data-bound="empty">No case selected</strong></p>'
            + '<p><span>Actor</span> <strong id="complaint-case-shell-actor" data-relationship="none">Not signed in</strong></p>'
            + '<p><span>Privacy</span> <strong id="complaint-case-shell-privacy">Privacy state is unavailable until you sign in</strong></p>'
            + '<p><span>Stage</span> <strong id="complaint-case-shell-stage">Sign-in required</strong></p>'
            + '<label class="case-shell__switch" for="complaint-case-shell-catalog">Switch case <select id="complaint-case-shell-catalog"></select></label>'
            + '<button type="button" id="complaint-case-shell-next">Sign in</button>'
            + "</div>"
            + '<div id="complaint-presentation-modes" role="radiogroup" aria-label="Workspace view">'
            + '<button type="button" role="radio" data-presentation-mode="chat-only" aria-checked="false">Chat</button>'
            + '<button type="button" role="radio" data-presentation-mode="chat-plus-context" aria-checked="false">Chat and context</button>'
            + '<button type="button" role="radio" data-presentation-mode="full-workspace" aria-checked="true">Full workspace</button>'
            + "</div>"
            + '<p id="complaint-presentation-status" role="status">Full workspace uses the same encrypted session.</p>'
            + '<aside id="complaint-presentation-context" hidden aria-label="Selected case context">'
            + '<h3>Selected context</h3>'
            + '<p id="complaint-presentation-inquiry"></p>'
            + '<p id="complaint-presentation-evidence"></p>'
            + '<p id="complaint-presentation-draft"></p>'
            + "</aside>"
            + '<div class="case-shell__body">'
            + '<nav id="complaint-case-shell-nav" aria-label="Case tasks">' + nav
            + '<details id="complaint-case-shell-more" class="case-shell__more"><summary>More</summary></details>'
            + "</nav>"
            + '<div id="complaint-case-shell-panels">' + panels + "</div>"
            + "</div>";
        host.querySelector("#complaint-case-shell-catalog").addEventListener("change", function (event) {
            var caseId = event.target.value;
            if (!caseId || caseId === state.caseId) return;
            // Drop the previous case's rendered text before the catalog request returns.
            clearPagePlaintext();
            committed.caseId = "";
            if (typeof window.complaintCasesSelect === "function") window.complaintCasesSelect(caseId);
        });
        host.querySelector("#complaint-case-shell-more").addEventListener("toggle", applyViewport);
        host.querySelector("#complaint-case-shell-nav").addEventListener("click", function (event) {
            var button = event.target.closest("[data-case-task]");
            if (!button) return;
            showTask(button.getAttribute("data-case-task"));
        });
        host.querySelector("#complaint-case-shell-next").addEventListener("click", runNext);
        host.querySelector("#complaint-entry-begin").addEventListener("click", beginComplaint);
        host.querySelector("#complaint-entry-check-key").addEventListener("click", checkPrivateKeyAccessAndResume);
        host.querySelector("#complaint-presentation-modes").addEventListener("click", function (event) {
            var button = event.target.closest("[data-presentation-mode]");
            if (!button) return;
            setPresentationMode(button.getAttribute("data-presentation-mode"));
        });
        host.querySelector("#complaint-presentation-modes").addEventListener("keydown", function (event) {
            var button = event.target.closest("[data-presentation-mode]");
            if (!button || event.altKey || event.ctrlKey || event.metaKey) return;
            var index = PRESENTATION_MODES.indexOf(button.getAttribute("data-presentation-mode"));
            if (index < 0) return;
            if (event.key === "ArrowRight" || event.key === "ArrowDown") index += 1;
            else if (event.key === "ArrowLeft" || event.key === "ArrowUp") index -= 1;
            else if (event.key === "Home") index = 0;
            else if (event.key === "End") index = PRESENTATION_MODES.length - 1;
            else return;
            event.preventDefault();
            var mode = PRESENTATION_MODES[(index + PRESENTATION_MODES.length) % PRESENTATION_MODES.length];
            setPresentationMode(mode).then(function (changed) {
                // Keep the real continuity/access checks and do not steal
                // focus if the person tabbed away during the session read.
                if (!changed || document.activeElement !== button) return;
                var selected = document.querySelector('#complaint-presentation-modes [data-presentation-mode="' + mode + '"]');
                if (selected) selected.focus();
            });
        });
        showTask("overview");
        applyPresentation();
        applyViewport();
        return host;
    }

    function applyViewport() {
        // Match the CSS breakpoints. innerWidth can drop below the layout
        // viewport when a scrollbar is present, which would mis-label tablet.
        var desktop = window.matchMedia("(min-width: 1100px)").matches;
        var tablet = window.matchMedia("(min-width: 768px)").matches;
        var mode = desktop ? "desktop" : (tablet ? "tablet" : "mobile");
        document.documentElement.dataset.caseViewport = mode;
        var more = document.getElementById("complaint-case-shell-more");
        var showSecondary = mode !== "mobile" || (more && more.open);
        if (more && mode !== "mobile") more.open = false;
        Array.prototype.forEach.call(document.querySelectorAll(".case-shell__task[data-tier='secondary']"), function (button) {
            button.hidden = !showSecondary;
        });
    }

    function forgetEntryCache() {
        ["localStorage", "sessionStorage"].forEach(function (name) {
            try {
                var storage = window[name];
                ["complaint-entry-passphrase", "complaint-entry-question"].forEach(function (key) { storage.removeItem(key); });
            } catch (error) { /* An unavailable browser store is never a case record. */ }
        });
    }

    function clearPagePlaintext(keepFields) {
        var host = shellHost();
        if (host) {
            Array.prototype.forEach.call(host.querySelectorAll(".case-shell__panel-body"), function (node) {
                node.textContent = "";
            });
        }
        var assignment = document.getElementById("assignment-content");
        if (assignment) assignment.textContent = "";
        if (keepFields) return;
        forgetEntryCache();
        var question = document.getElementById("complaint-entry-question");
        if (question) {
            question.textContent = "";
            question.hidden = true;
            question.dataset.inquiryId = "";
        }
        var keyResult = document.getElementById("complaint-entry-key-result");
        if (keyResult) keyResult.textContent = "";
        ["case-draft", "gap-input"].forEach(function (id) {
            var field = document.getElementById(id);
            if (field) field.value = "";
        });
        ["unresolved-gaps", "selected-case-label", "complaint-presentation-inquiry", "complaint-presentation-evidence", "complaint-presentation-draft"].forEach(function (id) {
            var node = document.getElementById(id);
            if (!node) return;
            if (node.tagName === "UL" || node.tagName === "OL") node.replaceChildren();
            else node.textContent = "";
        });
        var selectedCase = document.getElementById("selected-case");
        if (selectedCase) {
            selectedCase.hidden = true;
            delete selectedCase.dataset.actorPrincipalId;
            delete selectedCase.dataset.caseId;
        }
    }

    function retireUnverifiedView(clearCatalog) {
        if (typeof window.retireComplaintCaseRequests === "function") window.retireComplaintCaseRequests();
        clearPagePlaintext(false);
        if (clearCatalog) {
            ["case-list", "assignment-list", "notification-list"].forEach(function (id) {
                var node = document.getElementById(id);
                if (node) node.replaceChildren();
            });
            var list = document.getElementById("case-list");
            if (list && list.dataset.state !== "error") list.dataset.state = "unavailable";
            var empty = document.getElementById("case-list-empty");
            if (empty) {
                empty.hidden = false;
                empty.textContent = "The case catalog must be read again for this account.";
            }
            var badge = document.getElementById("notification-badge");
            if (badge) badge.textContent = "0";
        }
        if (typeof window.resetPrivateWorkspaceView === "function"
                && (["ready", "partial"].indexOf(document.body.dataset.workspaceHydrated) !== -1
                    || window.complaintCanonicalSession)) {
            retiringWorkspace = true;
            try {
                window.resetPrivateWorkspaceView("unavailable", "Private case access changed or could not be verified. Reload to reconnect.");
            } finally { retiringWorkspace = false; }
        }
    }

    function noteBoundary(principalId, caseId, access) {
        var actorChanged = committed.principalId && committed.principalId !== principalId;
        var caseChanged = committed.caseId && committed.caseId !== caseId;
        // Reviewers use the grant owner rather than the owner-only private
        // session probe; its unattempted default is not a reviewer failure.
        var privateUnavailable = state.relationship === "owner"
            && (access === "unavailable" || access === "disconnected");
        var closed = access === "locked" || access === "revoked" || access === "logged-out" || privateUnavailable;
        var fields = document.getElementById("selected-case");
        // Preserve only fields already rendered from this actor/case's real
        // catalog response. A refresh can discover a change from another view.
        var currentFields = Boolean(fields && principalId && caseId
            && fields.dataset.actorPrincipalId === principalId && fields.dataset.caseId === caseId);
        if (closed || ((actorChanged || caseChanged) && !currentFields)) {
            var catalog = document.getElementById("case-list");
            retireUnverifiedView(access === "logged-out" || (actorChanged && catalog
                && catalog.dataset.actorPrincipalId !== principalId));
        } else if (actorChanged || caseChanged) clearPagePlaintext(true);
        committed.principalId = principalId || "";
        committed.caseId = caseId || "";
        committed.access = access || "";
    }

    function showTask(name) {
        var host = shellHost();
        if (!host) return;
        Array.prototype.forEach.call(host.querySelectorAll("[data-case-task]"), function (button) {
            var on = button.getAttribute("data-case-task") === name;
            button.setAttribute("aria-current", on ? "page" : "false");
        });
        Array.prototype.forEach.call(host.querySelectorAll("[data-case-panel]"), function (panel) {
            panel.hidden = panel.getAttribute("data-case-panel") !== name;
        });
        fillPanel(name);
        var tab = {mediator: "intake", evidence: "evidence", draft: "draft", legal: "review", facts: "review"}[name];
        if (tab) {
            var existing = document.querySelector('.tab-button[data-tab-target="' + tab + '"]');
            if (existing && existing.getAttribute("data-case-shell-diagnostic") !== "true") existing.click();
        }
        var anchor = {mediator: "adaptive-inquiry", evidence: "evidence-title", draft: "draft-status", team: "assignments"}[name];
        var node = anchor ? document.getElementById(anchor) : null;
        if (node && name !== "overview") node.scrollIntoView({block: "nearest"});
    }

    function fillPanel(name) {
        var host = shellHost();
        var panel = host && host.querySelector('[data-case-panel="' + name + '"] .case-shell__panel-body');
        if (!panel) return;
        if (name === "overview") {
            panel.textContent = state.caseId
                ? "This case is " + (state.caseLabel || state.caseId) + ". Stage: " + state.stage + ". Open readiness and next actions for unanswered questions, missing evidence, unreviewed sources, and draft blockers."
                : "No case is selected for this actor.";
        } else if (name === "mediator") {
            var pending = pendingInquiry();
            panel.textContent = pending ? "Current question: " + (inquiryText(pending) || "A server question is pending.") : "No actionable mediator question is loaded.";
        } else if (name === "evidence") {
            panel.textContent = "Evidence stays in the case evidence workspace. Receipt is not proof.";
        } else if (name === "facts") {
            var questions = state.session && Array.isArray(state.session.questions) ? state.session.questions.length : 0;
            panel.textContent = questions ? ("The interview has " + questions + " recorded questions. Gaps: " + (state.gaps.join("; ") || "none listed.")) : "No factual timeline is loaded for this actor.";
        } else if (name === "legal") {
            var matrix = supportMatrix();
            panel.textContent = matrix.length ? ("Review support items: " + matrix.map(function (item) { return text(item.label || item.element || "item"); }).join("; ") + ". These are not admitted governing law.") : "No admitted legal requirements are available.";
        } else if (name === "draft") {
            var draft = state.session && state.session.session && state.session.session.draft;
            panel.textContent = draft ? "A draft exists on the canonical session." : "No draft is stored for this case.";
        } else if (name === "team") {
            panel.textContent = state.assignment ? ("Assignment " + text(state.assignment.state) + " as " + text(state.assignment.party) + ".") : "No assignment is visible for this actor.";
        }
    }

    function supportMatrix() {
        var review = state.session && state.session.review;
        var matrix = review && review.support_matrix;
        return Array.isArray(matrix) ? matrix : [];
    }

    function pendingInquiry() {
        var session = state.session && state.session.session;
        var shared = session && session.shared_interview;
        if (!shared || typeof shared !== "object") return null;
        var pending = shared.pending_inquiry || shared.pending;
        if (!pending || typeof pending !== "object") return null;
        if (pending.pending === false) return null;
        return pending.inquiry_id || pending.prompt || pending.question ? pending : null;
    }

    function inquiryText(pending) {
        return text(pending && (pending.question || pending.prompt || pending.text));
    }

    function entryKind() {
        if (window.complaintEntryHold === "denied" && !state.authenticated) return "denied";
        if (state.entry) return state.entry;
        if (!state.authenticated) return "first-run";
        if (state.nextKind === "check-key") return "missing-key";
        if (state.nextKind === "denied") return "denied";
        if (state.nextKind === "unavailable" || state.nextKind === "retry" || state.nextKind === "reconnect") return "unavailable";
        if (!state.caseId) return state.catalog.length ? "select" : "first-run";
        if (pendingInquiry()) return "resume";
        return "continue";
    }

    function paintEntry() {
        var entry = document.getElementById("complaint-entry");
        if (!entry) return;
        var kind = entryKind();
        var title = document.getElementById("complaint-entry-title");
        var detail = document.getElementById("complaint-entry-detail");
        var boundary = document.getElementById("complaint-entry-boundary");
        var question = document.getElementById("complaint-entry-question");
        var begin = document.getElementById("complaint-entry-begin");
        var keyAccess = document.getElementById("complaint-entry-key-access");
        var pending = kind === "resume" ? pendingInquiry() : null;
        var copy = {
            "first-run": ["Begin a complaint", "Name the case and start with what happened. No legal theory is required first, and no empty case is created until you submit the case form."],
            "select": ["Choose the case to resume", "Pick the case from the catalog. The page does not open a blank replacement case."],
            "missing-key": ["Private key access is locked", "An authorized local key owner must unlock the private keys outside this page. Then check access here to resume the saved server question. This page never receives a passphrase or opens a replacement case."],
            "denied": ["This session is denied", "The account cannot open case content. No replacement case is shown as ready."],
            "unavailable": ["This capability is unavailable", "The case catalog or private session could not be read. Nothing was replaced with an empty case."],
            "resume": ["Resume the pending question", "The question below is the current server inquiry for the selected case."],
            "continue": ["Continue this case", "The selected case has no actionable mediator question right now."]
        };
        var pair = copy[kind] || copy["unavailable"];
        var boundaryCopy = {
            "denied": "Sign-in was denied. No replacement case was opened.",
            "missing-key": "The private key is missing. No replacement case was opened.",
            "unavailable": "This capability is unavailable. No replacement case was opened."
        };
        entry.dataset.entry = kind;
        entry.dataset.readyBadge = "false";
        entry.dataset.browserCache = "ignored";
        entry.dataset.consent = "not-modified";
        entry.dataset.caseId = state.caseId || "";
        title.textContent = pair[0];
        detail.textContent = pair[1];
        boundary.textContent = boundaryCopy[kind] || (state.privacy + " " + state.stage);
        question.hidden = !pending;
        question.textContent = pending ? inquiryText(pending) : "";
        question.dataset.inquiryId = pending ? text(pending.inquiry_id) : "";
        begin.hidden = kind !== "first-run";
        keyAccess.hidden = kind !== "missing-key" && kind !== "resume";
    }

    function beginComplaint() {
        var label = document.getElementById("case-label");
        var form = document.getElementById("create-case");
        if (label && form) {
            form.hidden = false;
            label.focus();
            return;
        }
        window.location.assign("/cases#create-case");
    }

    async function checkPrivateKeyAccessAndResume() {
        forgetEntryCache();
        var checking = refresh();
        var token = refreshToken;
        await checking;
        if (token !== refreshToken) return;
        var result = document.getElementById("complaint-entry-key-result");
        var pending = pendingInquiry();
        if (result && entryKind() === "missing-key") {
            result.textContent = "Private key access is still locked. An authorized local key owner must unlock it outside this page. No replacement case was opened.";
        } else if (result && pending) {
            result.textContent = "Private key access is available. The pending question was read from this case's saved server inquiry.";
        }
        if (pending) showTask("mediator");
    }

    async function readJson(path, headers, signal) {
        var response = await fetch(path, {credentials: "same-origin", signal: signal, headers: Object.assign({accept: "application/json"}, headers || {})});
        var payload = null;
        try { payload = await response.json(); } catch (error) { payload = null; }
        return {ok: response.ok, status: response.status, body: payload};
    }

    function allowedCase(record) {
        return record && text(record.case_id) && record.plaintext_available !== false;
    }

    function pickAssignment(rows, principalId) {
        var visible = (rows || []).filter(function (row) {
            return row && (row.party === "recipient" || row.member_principal_id === principalId) && (row.state === "accepted" || row.state === "pending");
        });
        visible.sort(function (a, b) {
            if (a.state === b.state) return text(a.case_id).localeCompare(text(b.case_id));
            return a.state === "accepted" ? -1 : 1;
        });
        return visible[0] || null;
    }

    function derive(actor, catalog, assignments, workspaceSession, contentState) {
        var next = {
            authenticated: Boolean(actor && actor.authenticated),
            principalId: actor && actor.principal_id ? text(actor.principal_id) : "",
            roles: actor && Array.isArray(actor.roles) ? actor.roles.map(text) : [],
            relationship: "none",
            caseId: "",
            caseLabel: "",
            privacy: "Privacy state is unavailable until you sign in",
            stage: "Sign-in required",
            next: "Sign in",
            nextKind: "sign-in",
            session: workspaceSession,
            assignment: null,
            gaps: [],
            catalog: [],
            entry: "continue",
            binding: null
        };
        var cases = catalog && Array.isArray(catalog.cases) ? catalog.cases : [];
        next.catalog = cases.filter(allowedCase).map(function (item) {
            return {case_id: text(item.case_id), label: text(item.label || item.case_id)};
        });
        if (!next.authenticated) {
            next.entry = "first-run";
            return next;
        }
        var selectedId = catalog && catalog.selected_case_id ? text(catalog.selected_case_id) : "";
        var owned = cases.filter(allowedCase);
        var selected = owned.find(function (item) { return item.case_id === selectedId; }) || null;
        var clientCase = window.workspaceClient && window.workspaceClient.caseContext;
        if (!selected && clientCase && clientCase.case_id) {
            selected = owned.find(function (item) { return item.case_id === clientCase.case_id; }) || null;
        }
        var assignment = pickAssignment(assignments && assignments.assignments, next.principalId);
        if (selected) {
            next.relationship = "owner";
            next.caseId = text(selected.case_id);
            next.caseLabel = text(selected.label || selected.case_id);
            next.binding = {
                tenant_id: text(selected.tenant_id),
                case_id: text(selected.case_id),
                resource_id: text(selected.resource_id),
                directory_revision: selected.directory_revision
            };
            next.gaps = contentState === "available" && Array.isArray(selected.unresolved_gaps) ? selected.unresolved_gaps.map(text) : [];
            next.privacy = "Local private is the default";
        } else if (assignment && assignment.case_id) {
            next.relationship = "reviewer";
            next.assignment = assignment;
            next.caseId = text(assignment.case_id);
            next.caseLabel = "Assigned case";
            if (assignment.state === "pending") {
                next.privacy = "Locked until you accept the assignment";
            } else if (assignment.key_grant === "admitted") {
                next.privacy = "Key grant admitted for this assignment";
            } else {
                next.privacy = "Locked until a key grant is admitted";
            }
        } else {
            next.privacy = "Local private is the default";
            next.stage = "No case selected";
            next.next = "Select a case";
            next.nextKind = "select";
            next.entry = next.catalog.length ? "select" : "first-run";
            return next;
        }
        if (next.relationship === "owner" && contentState === "locked") {
            next.session = null;
            next.gaps = [];
            next.privacy = "Locked until the private key is available";
            next.stage = "Locked";
            next.next = "Check private key access";
            next.nextKind = "check-key";
            next.entry = "missing-key";
            return next;
        }
        if (next.relationship === "owner" && (contentState === "unavailable" || contentState === "disconnected")) {
            next.session = null;
            next.privacy = contentState === "disconnected" ? "Private workspace is disconnected" : "Private case content is unavailable";
            next.stage = contentState === "disconnected" ? "Disconnected" : "Unavailable";
            next.next = contentState === "disconnected" ? "Reconnect to the case" : "Retry the case";
            next.nextKind = contentState === "disconnected" ? "reconnect" : "retry";
            next.entry = "unavailable";
            return next;
        }
        if (next.relationship === "reviewer" && assignment.state === "pending") {
            next.stage = "Assignment pending";
            next.next = "Accept the assignment";
            next.nextKind = "accept";
            next.entry = "continue";
            return next;
        }
        if (next.relationship === "reviewer") {
            next.stage = "Assigned review";
            next.next = "Open the assigned review";
            next.nextKind = "review";
            next.entry = "continue";
            return next;
        }
        var pending = pendingInquiryFrom(workspaceSession);
        var draft = workspaceSession && workspaceSession.session && workspaceSession.session.draft;
        var overview = workspaceSession && workspaceSession.review && workspaceSession.review.overview || {};
        var evidenceCount = Number(overview.testimony_items || 0) + Number(overview.document_items || 0);
        if (pending) {
            next.stage = "Mediator question";
            next.next = "Answer the current question";
            next.nextKind = "mediator";
            next.entry = "resume";
        } else if (draft) {
            next.stage = "Draft";
            next.next = "Continue the draft";
            next.nextKind = "draft";
        } else if (evidenceCount > 0) {
            next.stage = "Evidence";
            next.next = "Review evidence";
            next.nextKind = "evidence";
        } else {
            next.stage = "Overview";
            next.next = "Open the mediator";
            next.nextKind = "mediator";
        }
        if (!next.entry) next.entry = "continue";
        return next;
    }

    function pendingInquiryFrom(sessionPayload) {
        var previous = state.session;
        state.session = sessionPayload;
        var found = pendingInquiry();
        state.session = previous;
        return found;
    }

    function paint() {
        var host = shellHost();
        if (!host) return;
        var caseNode = document.getElementById("complaint-case-shell-case");
        var actorNode = document.getElementById("complaint-case-shell-actor");
        var privacyNode = document.getElementById("complaint-case-shell-privacy");
        var stageNode = document.getElementById("complaint-case-shell-stage");
        var nextNode = document.getElementById("complaint-case-shell-next");
        caseNode.textContent = state.caseId ? (state.caseLabel || state.caseId) : "No case selected";
        caseNode.dataset.bound = state.caseId ? "case" : "empty";
        caseNode.dataset.caseId = state.caseId;
        var actorLabel = state.relationship === "owner" ? "Owner" : (state.relationship === "reviewer" ? "Assigned reviewer" : (state.authenticated ? "Signed in" : "Not signed in"));
        actorNode.textContent = actorLabel;
        actorNode.dataset.relationship = state.relationship;
        actorNode.dataset.principalId = state.principalId;
        actorNode.dataset.roles = state.roles.join(",");
        privacyNode.textContent = state.privacy;
        stageNode.textContent = state.stage;
        nextNode.textContent = state.next;
        nextNode.dataset.kind = state.nextKind;
        var kind = entryKind();
        host.dataset.state = kind;
        host.dataset.readyBadge = "false";
        var legacy = document.getElementById("workspace-case-context-value");
        var legacyHost = document.getElementById("workspace-case-context");
        if (legacy) {
            legacy.textContent = state.caseId ? caseNode.textContent : "No case selected";
            if (legacyHost) legacyHost.dataset.state = state.caseId && kind !== "missing-key" && kind !== "denied" && kind !== "unavailable" ? "current" : (state.caseId ? kind : "empty");
        }
        var caseContext = document.getElementById("case-context");
        if (caseContext && state.caseId && (kind === "missing-key" || kind === "denied" || kind === "unavailable")) {
            caseContext.dataset.state = kind === "missing-key" ? "locked" : kind;
        }
        renderCatalog(state.catalog, state.caseId);
        paintEntry();
        noteReadinessShell();
        applyPresentation();
        var active = host.querySelector("[data-case-task][aria-current='page']");
        fillPanel(active ? active.getAttribute("data-case-task") : "overview");
    }

    function noteReadinessShell() {
        if (!window.ComplaintDraft || typeof window.ComplaintDraft.noteShell !== "function") return;
        window.ComplaintDraft.noteShell({
            entry: entryKind(),
            caseId: state.caseId,
            relationship: state.relationship,
            session: state.session,
            authenticated: state.authenticated
        });
    }

    function applyPresentation() {
        document.documentElement.dataset.workspacePresentation = presentationMode;
        var host = shellHost();
        if (host) host.dataset.presentation = presentationMode;
        Array.prototype.forEach.call(document.querySelectorAll("[data-presentation-mode]"), function (button) {
            var on = button.getAttribute("data-presentation-mode") === presentationMode;
            button.setAttribute("aria-checked", on ? "true" : "false");
            button.tabIndex = on ? 0 : -1;
        });
        var context = document.getElementById("complaint-presentation-context");
        if (context) context.hidden = presentationMode !== "chat-plus-context";
    }

    function presentationLabel(mode) {
        if (mode === "chat-only") return "Chat";
        if (mode === "chat-plus-context") return "Chat and context";
        return "Full workspace";
    }

    function continuityDom() {
        var pending = document.getElementById("adaptive-pending");
        var draft = document.getElementById("draft-body");
        var title = document.getElementById("draft-title");
        var list = document.getElementById("evidence-list");
        var host = shellHost();
        return {
            sessionKey: host ? (host.dataset.sessionKey || "") : "",
            inquiryId: pending ? (pending.dataset.inquiryId || "") : "",
            inquiryRevision: pending ? (pending.dataset.revision || "") : "",
            evidenceId: list ? (list.dataset.selectedId || "") : "",
            draftTitle: title ? title.value : "",
            draftBody: draft ? draft.value : ""
        };
    }

    function sameContinuity(first, second) {
        return first.sessionKey === second.sessionKey && first.inquiryId === second.inquiryId
            && first.inquiryRevision === second.inquiryRevision && first.evidenceId === second.evidenceId
            && first.draftTitle === second.draftTitle && first.draftBody === second.draftBody;
    }

    function paintPresentationContext() {
        var inquiry = document.getElementById("complaint-presentation-inquiry");
        var evidence = document.getElementById("complaint-presentation-evidence");
        var draft = document.getElementById("complaint-presentation-draft");
        if (!inquiry || !evidence || !draft) return;
        var kind = entryKind();
        var blocked = presentationMode !== "chat-plus-context" || kind === "missing-key" || kind === "denied" || kind === "unavailable" || !state.authenticated;
        if (blocked) {
            inquiry.textContent = "";
            evidence.textContent = "";
            draft.textContent = "";
            return;
        }
        var pending = document.getElementById("adaptive-pending");
        inquiry.textContent = pending && pending.dataset.inquiryId
            ? ("Inquiry " + pending.dataset.inquiryId + " revision " + (pending.dataset.revision || ""))
            : "No pending inquiry is loaded.";
        var list = document.getElementById("evidence-list");
        var selectedId = list ? (list.dataset.selectedId || "") : "";
        var button = selectedId && list ? list.querySelector('[data-evidence-id="' + selectedId.replace(/"/g, "") + '"]') : null;
        evidence.textContent = button ? ("Selected evidence: " + text(button.innerText).replace(/\s+/g, " ").trim()) : "No evidence item is selected.";
        var body = document.getElementById("draft-body");
        var title = document.getElementById("draft-title");
        draft.textContent = body && body.value
            ? ("Draft: " + (title && title.value ? title.value + ". " : "") + body.value)
            : "No draft is loaded.";
    }

    function presentationReadIsCurrent(guard) {
        return guard.token === refreshToken && guard.principalId === state.principalId
            && guard.caseId === state.caseId && guard.binding === state.binding
            && guard.client === window.workspaceClient && guard.epoch === guard.client._privacyEpoch;
    }

    async function retireFailedPresentationRead(error, guard) {
        if ([401, 403, 409, 503].indexOf(error && error.status) === -1 || !presentationReadIsCurrent(guard)) return;
        // A fresh refused read cannot keep a previously decrypted case open.
        // Re-derive the actual locked/denied/unavailable state through its owner.
        retireUnverifiedView(true);
        await refresh();
    }

    async function setPresentationMode(mode) {
        var status = document.getElementById("complaint-presentation-status");
        if (PRESENTATION_MODES.indexOf(mode) === -1) {
            if (status) status.textContent = "That workspace view is not available.";
            return false;
        }
        var kind = entryKind();
        var blocked = kind === "missing-key" || kind === "denied" || kind === "unavailable" || !state.authenticated;
        var before = continuityDom();
        var focused = document.activeElement && document.activeElement.id;
        var client = window.workspaceClient;
        var readGuard = {token: refreshToken, principalId: state.principalId,
            caseId: state.caseId, binding: state.binding, client: client, epoch: client && client._privacyEpoch};
        var serverBefore = null;
        if (!blocked && client && typeof client.readCanonicalSession === "function" && state.binding && state.binding.case_id) {
            try {
                serverBefore = await client.readCanonicalSession(state.binding);
            } catch (error) {
                if (!presentationReadIsCurrent(readGuard)) return false;
                await retireFailedPresentationRead(error, readGuard);
                if (status) status.textContent = "The workspace session could not be read. The view stayed on " + presentationLabel(presentationMode) + ".";
                return false;
            }
        }
        var previous = presentationMode;
        presentationMode = mode;
        applyPresentation();
        paintPresentationContext();
        var after = continuityDom();
        if (!sameContinuity(before, after)) {
            presentationMode = previous;
            applyPresentation();
            paintPresentationContext();
            if (status) status.textContent = "The view stayed on " + presentationLabel(previous) + " because the open case changed.";
            return false;
        }
        if (serverBefore) {
            try {
                var serverAfter = await client.readCanonicalSession(state.binding);
                if (JSON.stringify(serverBefore.continuity) !== JSON.stringify(serverAfter.continuity)) {
                    presentationMode = previous;
                    applyPresentation();
                    paintPresentationContext();
                    if (status) status.textContent = "The encrypted session changed. The view stayed on " + presentationLabel(previous) + ".";
                    return false;
                }
            } catch (error) {
                if (!presentationReadIsCurrent(readGuard)) return false;
                presentationMode = previous;
                applyPresentation();
                paintPresentationContext();
                await retireFailedPresentationRead(error, readGuard);
                if (status) status.textContent = "The workspace session could not be confirmed. The view stayed on " + presentationLabel(previous) + ".";
                return false;
            }
        }
        if (focused && focused !== document.activeElement.id) {
            var node = document.getElementById(focused);
            if (node && node.getClientRects && node.getClientRects().length && node.focus) node.focus();
        }
        if (status) {
            status.textContent = blocked
                ? "The view changed without opening case content."
                : (presentationLabel(mode) + " uses the same encrypted session.");
        }
        return true;
    }

    function renderCatalog(cases, selectedId) {
        var select = document.getElementById("complaint-case-shell-catalog");
        if (!select) return;
        var rows = Array.isArray(cases) ? cases : [];
        var signature = rows.map(function (item) { return item.case_id; }).join("|") + "#" + (selectedId || "");
        if (select.dataset.signature === signature) return;
        select.dataset.signature = signature;
        select.replaceChildren();
        var placeholder = document.createElement("option");
        placeholder.value = "";
        placeholder.textContent = rows.length ? "Switch case" : "No cases in the catalog";
        select.appendChild(placeholder);
        rows.forEach(function (item) {
            var option = document.createElement("option");
            option.value = item.case_id;
            option.textContent = item.label || item.case_id;
            select.appendChild(option);
        });
        select.value = selectedId && rows.some(function (item) { return item.case_id === selectedId; }) ? selectedId : "";
    }

    function sameActor(first, current) {
        return Boolean(first && current && first.authenticated === true && current.authenticated === true
            && first.principal_id && first.principal_id === current.principal_id
            && first.tenant_id === current.tenant_id && first.generation === current.generation
            && first.expires_at === current.expires_at
            && JSON.stringify(first.roles || []) === JSON.stringify(current.roles || []));
    }

    function currentContext() {
        return JSON.stringify(window.workspaceClient && window.workspaceClient.caseContext || null);
    }

    function invalidate() {
        if (activeController) activeController.abort();
        activeController = new AbortController();
        ++refreshToken;
        state = derive(null, null, null, null);
        paint();
        var host = shellHost();
        if (host) {
            host.dataset.refreshState = "loading";
            host.setAttribute("aria-busy", "true");
        }
        if (document.getElementById("complaint-state-surface")) {
            showStateSurface({kind: "loading", operation: "shell-refresh", permitCancel: true});
        }
    }

    function finished() {
        var host = shellHost();
        if (host) {
            host.dataset.refreshState = "settled";
            host.setAttribute("aria-busy", "false");
        }
    }

    function rejected(token) {
        if (token !== refreshToken) return;
        invalidate();
        scheduleRefresh();
    }

    function isLocked(response) {
        return Boolean(response && !response.ok && response.body && ["unlock_needed", "key_unavailable"].indexOf(response.body.error) !== -1);
    }

    function sessionIdentity(payload) {
        var session = payload && payload.session || {};
        var shared = session.shared_interview || {};
        return JSON.stringify([session.user_id, session.case_id || "", session.private_revision || "",
            shared.session_revision === undefined ? null : shared.session_revision]);
    }

    function boundaryAccess(contentState, assignment) {
        if (contentState === "locked") return "locked";
        if (assignment && (assignment.state === "removed" || assignment.revoked === true || assignment.key_grant === "revoked")) return "revoked";
        return contentState || "";
    }

    async function privateSession(record, signal) {
        if (window.workspaceClient && window.workspaceClient._privacyActive === false) {
            return {contentState: "disconnected", session: null};
        }
        if (!Number.isSafeInteger(record.directory_revision) || record.directory_revision < 1) {
            return {contentState: "unavailable", session: null};
        }
        var headers = {"x-tenant-id": record.tenant_id, "x-case-id": record.case_id,
            "x-resource-id": text(record.resource_id), "x-expected-revision": text(record.directory_revision)};
        // The cookie supplies the actor; the case headers select its canonical
        // storage owner. A tenant user_id query would be a forged actor claim.
        var path = "/api/complaint-workspace/session?case_id=" + encodeURIComponent(record.case_id);
        var before = await readJson(path, headers, signal);
        if (isLocked(before)) return {contentState: "locked", session: null};
        if (!before.ok || !before.body || !before.body.session
                || before.body.session.user_id !== record.tenant_id) {
            return {contentState: "unavailable", session: null};
        }
        // Reopen through the actual key/authorization owner before publishing
        // plaintext. A changed key or persisted revision retires the first read.
        var after = await readJson(path, headers, signal);
        if (isLocked(after)) return {contentState: "locked", session: null};
        if (!after.ok || !after.body || !after.body.session
                || after.body.session.user_id !== record.tenant_id
                || sessionIdentity(before.body) !== sessionIdentity(after.body)) {
            return {contentState: "unavailable", session: null};
        }
        return {contentState: "available", session: after.body};
    }

    async function refresh() {
        mount();
        applyAudience();
        invalidate();
        var token = refreshToken;
        var signal = activeController ? activeController.signal : undefined;
        var context = currentContext();
        try {
            var actor = await readJson("/api/complaint-workspace/auth/session", null, signal);
            if (token !== refreshToken) return;
            if (!actor.ok) {
                noteBoundary("", "", "logged-out");
                state = derive(null, null, null, null);
                if (actor.status === 403 || (actor.body && actor.body.error === "authorization_denied")) {
                    state.entry = "denied";
                    state.stage = "Session denied";
                    state.privacy = "This session cannot open a case";
                    state.next = "Sign in with an allowed account";
                    state.nextKind = "denied";
                }
                paint();
                finished();
                return;
            }
            var catalog = await readJson("/api/cases/session", null, signal);
            var assignments = await readJson("/api/cases/assignments", null, signal);
            if (token !== refreshToken) return;
            if ((catalog.ok && catalog.body.actor_principal_id !== actor.body.principal_id)
                    || (assignments.ok && assignments.body.actor_principal_id !== actor.body.principal_id)) {
                rejected(token);
                return;
            }
            if (!catalog.ok) {
                retireUnverifiedView(true);
                state = derive(actor.body, {cases: [], selected_case_id: ""}, {assignments: []}, null, "unavailable");
                state.entry = "unavailable";
                state.catalog = [];
                state.caseId = "";
                state.caseLabel = "";
                state.stage = "Case catalog is unavailable";
                state.privacy = "No replacement case was opened";
                state.next = "Retry";
                state.nextKind = "unavailable";
                paint();
                finished();
                return;
            }
            var catalogBody = catalog.body;
            var assignmentBody = assignments.ok ? assignments.body : {assignments: []};
            var preview = derive(actor.body, catalogBody, assignmentBody, null);
            var content = {contentState: "unavailable", session: null};
            if (preview.caseId && preview.relationship === "owner") {
                var match = (catalogBody.cases || []).find(function (item) { return item.case_id === preview.caseId; });
                if (match && match.tenant_id) content = await privateSession(match, signal);
            }
            if (token !== refreshToken) return;
            var currentActor = await readJson("/api/complaint-workspace/auth/session", null, signal);
            var currentCatalog = await readJson("/api/cases/session", null, signal);
            if (token !== refreshToken) return;
            if (!currentActor.ok || !sameActor(actor.body, currentActor.body) || context !== currentContext()
                    || currentCatalog.ok !== catalog.ok
                    || (currentCatalog.ok && (currentCatalog.body.actor_principal_id !== actor.body.principal_id
                        || currentCatalog.body.selected_case_id !== catalogBody.selected_case_id))) {
                rejected(token);
                return;
            }
            if (content.contentState === "locked" && document.body.dataset.workspaceHydrated !== "locked"
                    && typeof window.resetPrivateWorkspaceView === "function") {
                // The existing workspace privacy boundary retires its cached
                // view only after this authenticated owner reports a real lock.
                retiringWorkspace = true;
                try {
                    window.resetPrivateWorkspaceView("locked", "Private keys remain locked. Reload after unlocking to reconnect.");
                } finally { retiringWorkspace = false; }
                if (token !== refreshToken) return;
            }
            state = derive(currentActor.body, catalogBody, assignmentBody, content.session, content.contentState);
            var access = boundaryAccess(content.contentState, state.assignment);
            if (committed.access === "reviewer" && state.relationship !== "reviewer") access = "revoked";
            noteBoundary(state.principalId, state.caseId, access);
            if (state.caseId && state.relationship === "owner") committed.access = access === "locked" ? "locked" : "owner";
            else if (state.relationship === "reviewer") committed.access = "reviewer";
            var sessionNode = shellHost();
            if (sessionNode) {
                sessionNode.dataset.sessionKey = content.session ? sessionIdentity(content.session) : "";
            }
            paint();
            finished();
            if (content.session && state.relationship === "owner" && content.contentState === "available"
                    && document.getElementById("draft-body")
                    && typeof window.renderCanonicalComplaintSession === "function") {
                window.renderCanonicalComplaintSession(content.session, state.binding, currentActor.body);
                paintPresentationContext();
            }
        } catch (error) {
            if (error && error.name === "AbortError") return;
            if (token !== refreshToken) return;
            // A failed refresh must not retain another actor's case or content.
            retireUnverifiedView(true);
            state = derive(null, null, null, null);
            state.entry = "unavailable";
            state.stage = "Workspace could not be read";
            state.privacy = "No replacement case was opened";
            state.next = "Retry";
            state.nextKind = "unavailable";
            paint();
            finished();
        }
    }

    function scheduleRefresh() {
        if (retiringWorkspace) return;
        window.clearTimeout(refreshTimer);
        invalidate();
        refreshTimer = window.setTimeout(function () { refresh(); }, 30);
    }

    function runNext() {
        var kind = state.nextKind;
        if (kind === "reconnect") {
            window.location.reload();
            return;
        }
        if (kind === "retry" || kind === "unavailable") {
            refresh();
            return;
        }
        if (kind === "sign-in") {
            var credential = document.getElementById("case-credential");
            if (credential) credential.focus();
            else window.location.assign("/cases");
            return;
        }
        if (kind === "select") {
            var choice = document.querySelector("#case-list button, #complaint-case-shell-case");
            if (choice && choice.focus) choice.focus();
            showTask("overview");
            return;
        }
        if (kind === "accept") {
            var accept = Array.prototype.find.call(document.querySelectorAll("#assignment-list button"), function (button) {
                return button.textContent.trim() === "Accept scope";
            });
            if (accept) accept.click();
            else showTask("team");
            return;
        }
        if (kind === "check-key" || kind === "missing-key") {
            checkPrivateKeyAccessAndResume();
            return;
        }
        if (kind === "review") {
            showTask("team");
            var assignments = document.getElementById("assignments") || document.getElementById("workspace-locked-state");
            if (assignments) assignments.focus && assignments.focus();
            return;
        }
        if (kind === "evidence") showTask("evidence");
        else if (kind === "draft") showTask("draft");
        else showTask("mediator");
    }

    document.addEventListener("click", function (event) {
        var button = event.target.closest && event.target.closest("[data-evidence-id]");
        var list = document.getElementById("evidence-list");
        if (!button || !list || !list.contains(button)) return;
        list.dataset.selectedId = button.getAttribute("data-evidence-id") || "";
        Array.prototype.forEach.call(list.querySelectorAll("[data-evidence-id]"), function (node) {
            node.setAttribute("aria-pressed", node === button ? "true" : "false");
        });
        if (presentationMode === "chat-plus-context") paintPresentationContext();
    });

    var RETRY_LIMIT = 3;
    var retryCounts = {};
    var surfaceGeneration = 0;
    var replayController = null;
    var lastReplay = null;
    var nativeFetch = null;

    var STATE_COPY = {
        loading: ["Loading", "The case state is still being read. You can cancel this check."],
        empty: ["Nothing to show yet", "This view is empty. An empty result is not a confirmed or complete case."],
        error: ["The action did not finish", "Your unsent text is unchanged. You can retry a limited number of times."],
        locked: ["Private key access is locked", "An authorized local key owner must unlock the private keys outside this page. No replacement case was opened."],
        key: ["A private key is required", "An authorized local key owner must unlock the private keys outside this page. This page never receives a passphrase."],
        access: ["Access is not available", "This session cannot open that case content. No replacement case was opened."],
        denied: ["This session is denied", "The account cannot open case content. No replacement case is shown as complete."],
        unavailable: ["This capability is unavailable", "The case service could not complete the request. Nothing was replaced with an empty case."],
        conflict: ["This case conflicts with the server", "The case changed elsewhere. Your unsent text is unchanged. You can retry a limited number of times."],
        cancelled: ["The request was cancelled", "Your unsent text is unchanged. Nothing was confirmed."]
    };

    function ensureStateSurface() {
        var existing = document.getElementById("complaint-state-surface");
        if (existing) return existing;
        var host = document.createElement("section");
        host.id = "complaint-state-surface";
        host.className = "case-state";
        host.setAttribute("role", "status");
        host.setAttribute("aria-live", "polite");
        host.setAttribute("aria-labelledby", "complaint-state-title");
        host.innerHTML = ''
            + '<h2 id="complaint-state-title">Loading</h2>'
            + '<p id="complaint-state-detail"></p>'
            + '<p id="complaint-state-intent" hidden>Your unsent text is still in the composer.</p>'
            + '<div class="case-state__actions">'
            + '<button type="button" id="complaint-state-retry" hidden>Retry</button>'
            + '<button type="button" id="complaint-state-cancel" hidden>Cancel</button>'
            + '<button type="button" id="complaint-state-check-key" hidden>Check private key access</button>'
            + '</div>';
        var parent = document.querySelector("main") || document.body;
        parent.insertBefore(host, parent.firstChild);
        return host;
    }

    function wireStateSurface(host) {
        if (!host || host.dataset.wired === "true") return;
        host.dataset.wired = "true";
        host.querySelector("#complaint-state-retry").addEventListener("click", retryLastFailure);
        host.querySelector("#complaint-state-cancel").addEventListener("click", cancelActiveCall);
        host.querySelector("#complaint-state-check-key").addEventListener("click", function () {
            if (typeof checkPrivateKeyAccessAndResume === "function") checkPrivateKeyAccessAndResume();
        });
    }

    function intentFields() {
        return ["message-text", "draft-body", "case-label"].map(function (id) {
            return document.getElementById(id);
        }).filter(function (node) {
            return node && "value" in node;
        });
    }

    function rememberIntent() {
        var kept = false;
        intentFields().forEach(function (node) {
            node.dataset.preservedIntent = node.value;
            if (node.value) kept = true;
        });
        return kept;
    }

    function restoreIntent() {
        var kept = false;
        intentFields().forEach(function (node) {
            if (node.dataset.preservedIntent === undefined) return;
            if (node.value !== node.dataset.preservedIntent) node.value = node.dataset.preservedIntent;
            if (node.value) kept = true;
        });
        return kept;
    }

    function classifyFailure(status, body) {
        var code = text(body && (body.error || body.code || body.detail)).toLowerCase();
        if (code === "unlock_needed" || code === "key_unavailable" || code === "key_owner_required" || code === "missing_key") return "key";
        if (status === 409 || code.indexOf("conflict") !== -1 || code === "replay_mismatch" || code === "stale_revision") return "conflict";
        if (status === 401 || status === 403 || code.indexOf("denied") !== -1 || code.indexOf("not_permitted") !== -1 || code === "missing_case") return "access";
        if (status === 503 || status === 502 || status === 0 || code.indexOf("unavailable") !== -1) return "unavailable";
        return "error";
    }

    function denySuccessPaint() {
        ["complaint-readiness", "complaint-entry", "send-message", "complaint-state-surface"].forEach(function (id) {
            var node = document.getElementById(id);
            if (!node) return;
            node.dataset.outcome = "failed";
            if ("legalSufficiency" in node.dataset || id === "complaint-readiness") node.dataset.legalSufficiency = "false";
            if ("courtReady" in node.dataset || id === "complaint-readiness") node.dataset.courtReady = "false";
            if ("filingSucceeded" in node.dataset || id === "complaint-readiness") node.dataset.filingSucceeded = "false";
            node.dataset.ready = "false";
            node.dataset.supported = "false";
            node.dataset.verified = "false";
        });
        var composer = document.getElementById("composer-state");
        if (composer && /ready|supported|verified/i.test(composer.textContent || "")) {
            composer.textContent = "The action did not finish.";
        }
        var send = document.getElementById("send-message");
        if (send) send.dataset.state = "failed";
    }

    function showStateSurface(model) {
        var host = ensureStateSurface();
        wireStateSurface(host);
        var kind = STATE_COPY[model.kind] ? model.kind : "error";
        var pair = STATE_COPY[kind];
        var failed = kind !== "loading" && kind !== "empty";
        var kept = failed ? rememberIntent() : restoreIntent();
        if (failed) restoreIntent();
        host.hidden = false;
        host.dataset.kind = kind;
        host.dataset.outcome = failed ? "failed" : (kind === "loading" ? "pending" : "empty");
        host.dataset.operation = model.operation || "";
        var attempts = retryCounts[model.operation || kind] || 0;
        var retryPermitted = failed && (kind === "conflict" || kind === "unavailable" || kind === "error") && attempts < RETRY_LIMIT && !!lastReplay && lastReplay.operation === (model.operation || kind);
        if (model.kind === "loading") retryPermitted = false;
        var cancelPermitted = kind === "loading" || !!model.permitCancel;
        host.dataset.retryPermitted = retryPermitted ? "true" : "false";
        host.dataset.cancelPermitted = cancelPermitted ? "true" : "false";
        host.dataset.retryCount = String(attempts);
        host.dataset.retryLimit = String(RETRY_LIMIT);
        host.dataset.ready = "false";
        host.dataset.supported = "false";
        host.dataset.verified = "false";
        host.dataset.intentPreserved = kept ? "true" : "false";
        document.getElementById("complaint-state-title").textContent = attempts >= RETRY_LIMIT && failed && (kind === "conflict" || kind === "unavailable" || kind === "error")
            ? "Retry limit reached"
            : pair[0];
        var detail = pair[1];
        if (attempts >= RETRY_LIMIT && retryPermitted === false && failed && kind !== "key" && kind !== "access" && kind !== "locked" && kind !== "denied" && kind !== "cancelled") {
            detail = "The retry limit for this action was reached. Your unsent text is unchanged.";
        }
        document.getElementById("complaint-state-detail").textContent = detail;
        var intent = document.getElementById("complaint-state-intent");
        intent.hidden = !kept;
        document.getElementById("complaint-state-retry").hidden = !retryPermitted;
        document.getElementById("complaint-state-cancel").hidden = !cancelPermitted;
        var checkKey = document.getElementById("complaint-state-check-key");
        checkKey.hidden = kind !== "key" && kind !== "locked";
        if (failed) denySuccessPaint();
        host.dataset.technicalHidden = "true";
    }

    function noteFailure(model) {
        if (model.generation !== undefined && model.generation !== surfaceGeneration) return;
        var operation = (model.method || "GET") + " " + (model.url || "");
        var status = model.status;
        var body = model.body;
        if (status === 401 && /\/auth\/session$/.test(model.url || "")) return;
        retryCounts[operation] = (retryCounts[operation] || 0) + 1;
        if (model.url && model.url.indexOf("/auth/login") === -1) {
            lastReplay = {
                url: model.url,
                method: model.method || "GET",
                headers: model.headers || {},
                body: model.requestBody || "",
                operation: operation
            };
        }
        showStateSurface({
            kind: classifyFailure(status, body),
            status: status,
            operation: operation
        });
    }

    function retryLastFailure() {
        if (!lastReplay) return;
        var operation = lastReplay.operation;
        if ((retryCounts[operation] || 0) >= RETRY_LIMIT) {
            showStateSurface({kind: classifyFailure(409, {error: "revision_conflict"}), operation: operation});
            return;
        }
        surfaceGeneration += 1;
        if (replayController) replayController.abort();
        replayController = new AbortController();
        showStateSurface({kind: "loading", operation: operation, permitCancel: true});
        var headers = lastReplay.headers || {};
        window.fetch(lastReplay.url, {
            method: lastReplay.method,
            credentials: "same-origin",
            headers: headers,
            body: lastReplay.method === "GET" || lastReplay.method === "HEAD" ? undefined : lastReplay.body,
            signal: replayController.signal
        }).catch(function (error) {
            if (error && error.name === "AbortError") return;
        });
    }

    function cancelActiveCall() {
        surfaceGeneration += 1;
        if (activeController) activeController.abort();
        if (replayController) replayController.abort();
        restoreIntent();
        showStateSurface({kind: "cancelled", operation: "cancelled", permitCancel: false});
        var host = document.getElementById("complaint-state-surface");
        if (host) {
            host.dataset.outcome = "cancelled";
            host.dataset.ready = "false";
            host.dataset.supported = "false";
            host.dataset.verified = "false";
        }
    }

    function headerRecord(headers) {
        var record = {};
        if (!headers) return record;
        if (typeof headers.forEach === "function") {
            headers.forEach(function (value, key) { record[key] = value; });
            return record;
        }
        Object.keys(headers).forEach(function (key) { record[key] = headers[key]; });
        return record;
    }

    function installFetchObserver() {
        if (window.fetch && window.fetch.__complaintStateObserved) return;
        nativeFetch = window.fetch.bind(window);
        function wrapped(input, init) {
            var url = typeof input === "string" ? input : (input && input.url) || "";
            var method = ((init && init.method) || (input && input.method) || "GET").toUpperCase();
            if (url.indexOf("/api/") === -1) return nativeFetch(input, init);
            var requestBody = init && typeof init.body === "string" ? init.body : "";
            var headers = headerRecord(init && init.headers);
            var generation = surfaceGeneration;
            return nativeFetch(input, init).then(function (response) {
                if (response.ok) {
                    if (url.indexOf("/messages/threads") !== -1 && method === "GET") {
                        response.clone().json().then(function (payload) {
                            if (generation !== surfaceGeneration) return;
                            var threads = payload && payload.threads;
                            var host = document.getElementById("complaint-state-surface");
                            if (host && host.dataset.outcome !== "failed" && Array.isArray(threads) && threads.length === 0) {
                                showStateSurface({kind: "empty", operation: method + " " + url});
                            }
                        }).catch(function () { /* A non-JSON success is not an empty case. */ });
                    }
                    return response;
                }
                response.clone().json().then(function (payload) {
                    noteFailure({status: response.status, body: payload, url: url, method: method, requestBody: requestBody, headers: headers, generation: generation});
                }).catch(function () {
                    noteFailure({status: response.status, body: null, url: url, method: method, requestBody: requestBody, headers: headers, generation: generation});
                });
                return response;
            }, function (error) {
                if (!error || error.name !== "AbortError") {
                    noteFailure({status: 0, body: {error: "unavailable"}, url: url, method: method, requestBody: requestBody, headers: headers, generation: generation});
                }
                throw error;
            });
        }
        wrapped.__complaintStateObserved = true;
        window.fetch = wrapped;
    }

    function watchSuccessWords() {
        var composer = document.getElementById("composer-state");
        var surface = document.getElementById("complaint-state-surface");
        if (!composer || !surface || composer.dataset.stateWatch === "true") return;
        composer.dataset.stateWatch = "true";
        var observer = new MutationObserver(function () {
            if (surface.dataset.outcome === "failed" && /ready|supported|verified/i.test(composer.textContent || "")) {
                composer.textContent = "The action did not finish.";
            }
        });
        observer.observe(composer, {childList: true, characterData: true, subtree: true});
    }

    installFetchObserver();
    ensureStateSurface();
    wireStateSurface(document.getElementById("complaint-state-surface"));
    watchSuccessWords();
    mount();
    applyAudience();
    window.complaintCaseShell = {
        refresh: refresh,
        invalidate: invalidate,
        scheduleRefresh: scheduleRefresh,
        showTask: showTask,
        noteReadiness: noteReadinessShell,
        applyViewport: applyViewport,
        setPresentationMode: setPresentationMode,
        binding: function () { return state.binding; },
        clearPlaintext: clearPagePlaintext,
        snapshot: function () {
            var shellCase = document.getElementById("complaint-case-shell-case");
            var shellActor = document.getElementById("complaint-case-shell-actor");
            var surface = document.getElementById("complaint-state-surface");
            return {
                case: shellCase ? shellCase.textContent.trim() : "",
                caseId: shellCase ? (shellCase.dataset.caseId || "") : "",
                actor: shellActor ? shellActor.textContent.trim() : "",
                relationship: shellActor ? shellActor.dataset.relationship : "",
                principalId: shellActor ? (shellActor.dataset.principalId || "") : "",
                privacy: document.getElementById("complaint-case-shell-privacy") ? document.getElementById("complaint-case-shell-privacy").textContent.trim() : "",
                stage: document.getElementById("complaint-case-shell-stage") ? document.getElementById("complaint-case-shell-stage").textContent.trim() : "",
                next: document.getElementById("complaint-case-shell-next") ? document.getElementById("complaint-case-shell-next").textContent.trim() : "",
                nextCount: document.querySelectorAll("#complaint-case-shell-next").length,
                surfaceKind: surface ? surface.dataset.kind : "",
                surfaceOutcome: surface ? surface.dataset.outcome : ""
            };
        }
    };
    window.addEventListener("resize", applyViewport);
    if (shellHost()) {
        if (document.readyState === "loading") {
            document.addEventListener("DOMContentLoaded", function () {
                watchSuccessWords();
                scheduleRefresh();
            });
        } else {
            scheduleRefresh();
        }
    }
})();
