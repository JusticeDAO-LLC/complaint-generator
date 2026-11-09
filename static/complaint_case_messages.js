(function () {
    "use strict";

    var csrf = "";
    var actor = "";
    var authGeneration = 0;
    var privacyEpoch = 0;
    var currentCursor = 0;
    var nextCursor = null;
    var pollTimer = 0;
    var pollGeneration = 0;
    var viewToken = 0;
    var chain = Promise.resolve();

    function enqueue(work) {
        var run = chain.then(work, work);
        chain = run.then(function () {}, function () {});
        return run;
    }
    var READ_PREFIX = "cimp-gui-44-read:";

    function $(id) { return document.getElementById(id); }

    function setStatus(text) { $("inbox-status").textContent = text || ""; }
    function setError(text) { $("inbox-error").textContent = text || ""; }

    function capture() {
        return { view: viewToken, privacy: privacyEpoch, actor: actor, generation: authGeneration,
            csrf: csrf, caseId: caseId(), threadId: threadId(),
            membership: $("membership-grant-id").value.trim(), version: $("membership-version").value.trim() };
    }

    function current(value) {
        return Boolean(value && csrf && actor && value.view === viewToken && value.privacy === privacyEpoch
            && value.actor === actor && value.generation === authGeneration && value.csrf === csrf
            && value.caseId === caseId() && value.threadId === threadId()
            && value.membership === $("membership-grant-id").value.trim()
            && value.version === $("membership-version").value.trim());
    }

    function clearView(clearThreads) {
        viewToken += 1;
        pollGeneration += 1;
        if (pollTimer) window.clearInterval(pollTimer);
        pollTimer = 0;
        currentCursor = 0;
        nextCursor = null;
        $("message-list").replaceChildren();
        if (clearThreads) $("thread-list").replaceChildren();
        $("unread-count").textContent = "Unread 0";
        $("page-meta").textContent = "";
        $("inbox-limitations").textContent = "";
        $("message-text").value = "";
        $("next-page").disabled = true;
        setStatus("");
    }

    function clearIdentity() {
        privacyEpoch += 1;
        actor = "";
        authGeneration = 0;
        csrf = "";
        clearView(true);
        ["case-id", "thread-id", "membership-grant-id", "membership-version"].forEach(function (id) { $(id).value = ""; });
        $("case-select").replaceChildren();
        $("inbox-auth-status").textContent = "Sign in required";
    }

    function failed(value, error) {
        if (!current(value)) return;
        if (error && error.status === 401) clearIdentity();
        else clearView(true);
        setError(error && error.message || "request_failed");
    }

    function caseId() { return $("case-id").value.trim(); }
    function threadId() { return $("thread-id").value.trim(); }

    function membershipFields(value) {
        var fields = {};
        var grant = value ? value.membership : $("membership-grant-id").value.trim();
        var version = value ? value.version : $("membership-version").value.trim();
        if (grant) fields.membership_grant_id = grant;
        if (version) fields.expected_membership_version = Number(version);
        return fields;
    }

    function pageLimit() {
        var value = Number($("page-limit").value);
        if (!Number.isInteger(value) || value < 1) return 10;
        return Math.min(value, 20);
    }

    function pollMs() {
        var value = Number($("poll-ms").value);
        if (!Number.isFinite(value) || value < 200) return 4000;
        return value;
    }

    function readCursor(id) {
        var raw = sessionStorage.getItem(READ_PREFIX + encodeURIComponent(actor) + ":" + id);
        if (raw === null || !/^[0-9]+$/.test(raw)) return 0;
        return Number(raw);
    }

    function rememberRead(id, sequence) {
        sessionStorage.setItem(READ_PREFIX + encodeURIComponent(actor) + ":" + id, String(sequence));
    }

    async function api(path, options, value) {
        if (value && !current(value)) throw new Error("view_changed");
        var headers = { "accept": "application/json" };
        var method = (options && options.method) || "GET";
        if (method !== "GET") {
            headers["content-type"] = "application/json";
            headers["x-csrf-token"] = value ? value.csrf : csrf;
        }
        var response = await fetch(path, {
            method: method,
            headers: headers,
            body: options && options.body ? JSON.stringify(options.body) : undefined,
            credentials: "same-origin",
            cache: "no-store"
        });
        var payload = await response.json();
        if (value && !current(value)) throw new Error("view_changed");
        if (!response.ok) { var error = new Error(payload.error || "request_failed"); error.status = response.status; throw error; }
        return payload;
    }

    function query(path, extra, value) {
        var params = new URLSearchParams();
        params.set("case_id", value ? value.caseId : caseId());
        var fields = membershipFields(value);
        Object.keys(fields).forEach(function (key) { params.set(key, String(fields[key])); });
        Object.keys(extra || {}).forEach(function (key) {
            if (extra[key] !== undefined && extra[key] !== null) params.set(key, String(extra[key]));
        });
        return path + "?" + params.toString();
    }

    function showLimitations(payload) {
        var items = payload && payload.limitations;
        $("inbox-limitations").textContent = Array.isArray(items) ? items.join(" ") : "";
    }

    function renderMessages(messages, mode) {
        var list = $("message-list");
        if (mode !== "append") list.replaceChildren();
        var known = {};
        list.querySelectorAll("[data-message-id]").forEach(function (node) {
            known[node.getAttribute("data-message-id")] = true;
        });
        var cursor = readCursor(threadId());
        messages.forEach(function (message) {
            if (known[message.message_id]) return;
            var item = document.createElement("li");
            item.setAttribute("data-message-id", message.message_id);
            item.setAttribute("data-sequence", String(message.sequence));
            var unread = Number(message.sequence) > cursor;
            item.setAttribute("data-unread", unread ? "true" : "false");
            if (unread) item.className = "unread";
            var sender = document.createElement("span");
            sender.textContent = message.sender_principal_id + " #" + message.sequence + " ";
            var body = document.createElement("span");
            body.className = "message-text";
            body.textContent = message.text;
            item.appendChild(sender);
            item.appendChild(body);
            list.appendChild(item);
        });
        updateUnreadCount();
    }

    function updateUnreadCount() {
        var count = document.querySelectorAll("#message-list [data-unread='true']").length;
        $("unread-count").textContent = "Unread " + count;
    }

    function applyReadState() {
        var cursor = readCursor(threadId());
        document.querySelectorAll("#message-list [data-sequence]").forEach(function (item) {
            var unread = Number(item.getAttribute("data-sequence")) > cursor;
            item.setAttribute("data-unread", unread ? "true" : "false");
            item.className = unread ? "unread" : "";
        });
        updateUnreadCount();
    }

    function highestSequence() {
        var max = 0;
        document.querySelectorAll("#message-list [data-sequence]").forEach(function (item) {
            max = Math.max(max, Number(item.getAttribute("data-sequence")));
        });
        return max;
    }

    async function loadPage(cursor, mode, value) {
        value = value || capture();
        if (!current(value)) return null;
        var payload = await api(query("/api/cases/messages/threads/" + encodeURIComponent(value.threadId) + "/messages", {
            cursor: cursor,
            limit: pageLimit()
        }, value), undefined, value);
        if (!current(value)) return null;
        if (payload.case_id !== value.caseId || payload.thread_id !== value.threadId || payload.actor_principal_id !== value.actor) throw new Error("view_changed");
        showLimitations(payload);
        currentCursor = cursor;
        nextCursor = payload.next_cursor === undefined ? null : payload.next_cursor;
        $("page-meta").textContent = "cursor " + payload.cursor + " next " + (nextCursor === null ? "none" : nextCursor);
        $("next-page").disabled = nextCursor === null;
        renderMessages(payload.messages || [], mode);
        return payload;
    }

    async function poll(value) {
        value = value || capture();
        if (!current(value) || !value.threadId || !value.caseId) return;
        var generation = pollGeneration;
        try {
            if (nextCursor === null && highestSequence() > 0) await loadPage(highestSequence(), "append", value);
            else await loadPage(currentCursor, "replace", value);
            if (current(value) && generation === pollGeneration) setStatus("Polled messages over HTTP");
            if (current(value)) setError("");
        } catch (error) {
            failed(value, error);
        }
    }

    function startPolling(value) {
        pollGeneration += 1;
        if (pollTimer) window.clearInterval(pollTimer);
        pollTimer = window.setInterval(function () { enqueue(function () { return poll(value); }); }, pollMs());
    }

    async function loadThreads(value) {
        value = value || capture();
        var payload = await api(query("/api/cases/messages/threads", {}, value), undefined, value);
        if (!current(value)) return;
        if (payload.case_id !== value.caseId || payload.actor_principal_id !== value.actor) throw new Error("view_changed");
        showLimitations(payload);
        var list = $("thread-list");
        list.replaceChildren();
        (payload.threads || []).forEach(function (thread) {
            var item = document.createElement("li");
            var button = document.createElement("button");
            button.type = "button";
            button.textContent = thread.thread_id + " (" + thread.message_count + ")";
            button.addEventListener("click", function () {
                if (value.actor !== actor || value.privacy !== privacyEpoch || value.caseId !== caseId()) return;
                clearView(false);
                $("thread-id").value = thread.thread_id;
            });
            item.appendChild(button);
            list.appendChild(item);
        });
        setStatus("Loaded " + (payload.threads || []).length + " threads");
    }

    async function refreshCases(value) {
        var payload = await api("/api/cases", undefined, value);
        if (!current(value)) return;
        var select = $("case-select");
        select.replaceChildren();
        var blank = document.createElement("option");
        blank.value = "";
        blank.textContent = "Select a case";
        select.appendChild(blank);
        (payload.cases || []).forEach(function (item) {
            var option = document.createElement("option");
            option.value = item.case_id;
            option.textContent = item.label || item.case_id;
            select.appendChild(option);
        });
    }

    $("case-select").addEventListener("change", function () {
        var selected = $("case-select").value;
        clearView(true);
        $("case-id").value = selected;
        $("thread-id").value = "";
        $("membership-grant-id").value = "";
        $("membership-version").value = "";
    });

    $("inbox-login").addEventListener("submit", async function (event) {
        event.preventDefault();
        var credential = $("inbox-credential").value;
        clearIdentity();
        var attempt = privacyEpoch;
        $("inbox-credential").value = "";
        setError("");
        try {
            var response = await fetch("/api/complaint-workspace/auth/login", {
                method: "POST",
                credentials: "same-origin",
                headers: { "content-type": "application/json", "accept": "application/json" },
                body: JSON.stringify({ credential: credential })
            });
            var payload = await response.json();
            if (attempt !== privacyEpoch) return;
            if (!response.ok || payload.authenticated !== true || typeof payload.principal_id !== "string" || !Number.isSafeInteger(payload.generation) || !payload.csrf_token) throw new Error(payload.error || "login_failed");
            actor = payload.principal_id;
            authGeneration = payload.generation;
            csrf = payload.csrf_token;
            $("inbox-credential").value = "";
            $("inbox-auth-status").textContent = "Signed in";
            var signedIn = capture();
            await refreshCases(signedIn);
            if (current(signedIn)) setStatus("Signed in");
        } catch (error) {
            if (attempt !== privacyEpoch) return;
            if (error.message === "view_changed") return;
            clearIdentity();
            $("inbox-auth-status").textContent = "Sign in required";
            setError(error.message || "login_failed");
        }
    });

    $("load-threads").addEventListener("click", function () {
        var value = capture();
        enqueue(function () { return loadThreads(value); }).catch(function (error) { failed(value, error); });
    });

    $("create-thread").addEventListener("click", function () {
        clearView(false);
        var value = capture();
        enqueue(async function () {
            if (!current(value)) return;
            setError("");
            var payload = await api("/api/cases/messages/threads", {method: "POST", body: Object.assign({
                case_id: value.caseId, idempotency_key: "thread-" + Date.now()
            }, membershipFields(value))}, value);
            if (!current(value) || payload.case_id !== value.caseId) return;
            $("thread-id").value = payload.thread_id;
            var created = capture();
            await loadThreads(created);
            if (current(created)) setStatus("Created thread");
        }).catch(function (error) { failed(value, error); });
    });

    $("open-thread").addEventListener("click", function () {
        clearView(false);
        var value = capture();
        enqueue(async function () {
            if (!current(value)) return;
            setError("");
            await loadPage(0, "replace", value);
            if (!current(value)) return;
            startPolling(value);
            setStatus("Opened thread");
        }).catch(function (error) { failed(value, error); });
    });

    $("next-page").addEventListener("click", function () {
        var cursor = nextCursor;
        viewToken += 1;
        var value = capture();
        enqueue(async function () {
            if (!current(value) || cursor === null) return;
            setError("");
            await loadPage(cursor, "replace", value);
            if (current(value)) { startPolling(value); setStatus("Loaded next page"); }
        }).catch(function (error) { failed(value, error); });
    });

    $("refresh-messages").addEventListener("click", function () {
        var value = capture();
        enqueue(function () { return poll(value); });
    });

    $("mark-read").addEventListener("click", function () {
        if (!threadId()) return;
        rememberRead(threadId(), highestSequence());
        applyReadState();
        setStatus("Marked visible messages read");
    });

    $("send-message").addEventListener("submit", function (event) {
        event.preventDefault();
        var text = $("message-text").value;
        var value = capture();
        enqueue(async function () {
            if (!current(value)) return;
            setError("");
            await api("/api/cases/messages/threads/" + encodeURIComponent(value.threadId) + "/messages", {
                method: "POST", body: Object.assign({case_id: value.caseId,
                    text: text, idempotency_key: "send-" + Date.now()}, membershipFields(value))}, value);
            if (!current(value)) return;
            $("message-text").value = "";
            if (nextCursor === null) await loadPage(highestSequence(), "append", value);
            else await loadPage(currentCursor, "replace", value);
            if (current(value)) setStatus("Sent message");
        }).catch(function (error) { failed(value, error); });
    });

    ["case-id", "thread-id", "membership-grant-id", "membership-version"].forEach(function (id) {
        $(id).addEventListener("input", function () {
            clearView(id !== "thread-id");
            if (id === "case-id") { $("thread-id").value = ""; $("membership-grant-id").value = ""; $("membership-version").value = ""; }
        });
    });
    window.addEventListener("pagehide", function () {
        clearIdentity();
    });
})();
