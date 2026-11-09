(function () {
    "use strict";

    var csrf = "";
    var actor = "";
    var authGeneration = 0;
    var privacyEpoch = 0;
    var pollTimer = 0;
    var pollGeneration = 0;
    var viewToken = 0;
    var chain = Promise.resolve();
    var sendState = null;
    var pollAbort = null;
    var sendAbort = null;
    var openContextId = "";
    var adoptionKeys = {};
    var MAX_SEND_ATTEMPTS = 2;

    var ATTRIBUTION = {
        human_message: { attribution: "human", label: "Human" },
        ai_mediator_turn: { attribution: "ai", label: "AI mediator" },
        review_decision: { attribution: "review", label: "Review decision" },
        case_action: { attribution: "action", label: "Case action" }
    };

    function enqueue(work) {
        var run = chain.then(work, work);
        chain = run.then(function () {}, function () {});
        return run;
    }

    function $(id) { return document.getElementById(id); }

    function setStatus(text) { $("inbox-status").textContent = text || ""; }

    function setError(text) {
        var node = $("inbox-error");
        node.textContent = text || "";
        if (text) node.focus();
    }

    function setComposer(state, text) {
        var form = $("send-message");
        form.setAttribute("data-state", state);
        form.setAttribute("aria-busy", state === "pending" || state === "retrying" ? "true" : "false");
        $("composer-state").textContent = text;
        $("send-button").disabled = state === "pending" || state === "retrying";
        $("retry-send").hidden = state !== "error";
    }

    function capture() {
        return {
            view: viewToken,
            privacy: privacyEpoch,
            actor: actor,
            generation: authGeneration,
            csrf: csrf,
            caseId: caseId(),
            threadId: threadId(),
            membership: $("membership-grant-id").value.trim(),
            version: $("membership-version").value.trim()
        };
    }

    function current(value) {
        return Boolean(value && csrf && actor && value.view === viewToken && value.privacy === privacyEpoch
            && value.actor === actor && value.generation === authGeneration && value.csrf === csrf
            && value.caseId === caseId() && value.threadId === threadId()
            && value.membership === $("membership-grant-id").value.trim()
            && value.version === $("membership-version").value.trim());
    }

    function stopPoll() {
        pollGeneration += 1;
        if (pollTimer) window.clearInterval(pollTimer);
        pollTimer = 0;
        if (pollAbort) pollAbort.abort();
        pollAbort = null;
    }

    function clearConversation() {
        openContextId = "";
        var panel = $("workflow-context");
        if (panel) panel.remove();
        $("message-list").replaceChildren();
        $("empty-conversation").hidden = true;
        $("source-status").textContent = "";
        $("inbox-limitations").textContent = "";
        var attention = $("inbox-attention");
        if (attention) attention.textContent = "";
    }

    function clearView(clearThreads) {
        viewToken += 1;
        sendState = null;
        stopPoll();
        if (sendAbort) sendAbort.abort();
        sendAbort = null;
        clearConversation();
        if (clearThreads) $("thread-list").replaceChildren();
        $("message-text").value = "";
        setComposer("idle", "Ready");
        setStatus("");
    }

    function clearIdentity() {
        privacyEpoch += 1;
        actor = "";
        authGeneration = 0;
        csrf = "";
        clearView(true);
        ["case-id", "thread-id", "membership-grant-id", "membership-version"].forEach(function (id) {
            $(id).value = "";
        });
        $("case-select").replaceChildren();
        $("inbox-auth-status").textContent = "Sign in required";
    }

    function clearingError(error) {
        if (!error) return false;
        if (error.status === 401) return true;
        return error.status === 403 && (
            error.message === "membership_removed" || error.message === "missing_case" ||
            error.message === "missing_grant" || error.message === "action_not_permitted" ||
            error.message === "grant_expired" || error.message === "message_unavailable" ||
            error.message === "case_key_grant_required"
        );
    }

    function failed(value, error) {
        if (!current(value)) return;
        if (error && error.message === "view_changed") return;
        if (error && error.message === "aborted") return;
        if (clearingError(error)) {
            if (error.status === 401) clearIdentity();
            else clearView(true);
        }
        setComposer("idle", "Ready");
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

    function pollMs() {
        var value = Number($("poll-ms").value);
        if (!Number.isFinite(value) || value < 200) return 4000;
        return Math.min(value, 60000);
    }

    function newKey(prefix) {
        var bytes = new Uint8Array(8);
        window.crypto.getRandomValues(bytes);
        var hex = Array.prototype.map.call(bytes, function (item) {
            return item.toString(16).padStart(2, "0");
        }).join("");
        return prefix + hex;
    }

    async function api(path, options, value) {
        if (value && !current(value)) throw new Error("view_changed");
        var headers = { "accept": "application/json" };
        var method = (options && options.method) || "GET";
        var lane = method === "GET" ? "poll" : "send";
        if (method !== "GET") {
            headers["content-type"] = "application/json";
            headers["x-csrf-token"] = value ? value.csrf : csrf;
        }
        if (options && options.lane) lane = options.lane;
        var controller = new AbortController();
        if (lane === "send") sendAbort = controller;
        else if (lane === "poll") pollAbort = controller;
        var timer = window.setTimeout(function () { controller.abort(); }, 15000);
        try {
            var response = await fetch(path, {
                method: method,
                headers: headers,
                body: options && options.body ? JSON.stringify(options.body) : undefined,
                credentials: "same-origin",
                cache: "no-store",
                signal: controller.signal
            });
            var payload = await response.json();
            if (value && !current(value)) throw new Error("view_changed");
            if (!response.ok) {
                var error = new Error(payload.error || "request_failed");
                error.status = response.status;
                throw error;
            }
            return payload;
        } catch (error) {
            if (error && error.name === "AbortError") {
                var aborted = new Error("aborted");
                aborted.status = 0;
                throw aborted;
            }
            throw error;
        } finally {
            window.clearTimeout(timer);
            if (lane === "send" && sendAbort === controller) sendAbort = null;
            if (lane === "poll" && pollAbort === controller) pollAbort = null;
        }
    }

    function query(path, extra, value) {
        var params = new URLSearchParams();
        params.set("case_id", value ? value.caseId : caseId());
        var fields = membershipFields(value);
        Object.keys(fields).forEach(function (key) { params.set(key, String(fields[key])); });
        Object.keys(extra || {}).forEach(function (key) {
            if (extra[key] !== undefined && extra[key] !== null && extra[key] !== "") params.set(key, String(extra[key]));
        });
        return path + "?" + params.toString();
    }

    function showLimitations(payload) {
        var items = payload && payload.limitations;
        $("inbox-limitations").textContent = Array.isArray(items) ? items.join(" ") : "";
    }

    function attentionHost() {
        var node = $("inbox-attention");
        if (node) return node;
        node = document.createElement("p");
        node.id = "inbox-attention";
        node.setAttribute("role", "status");
        node.dataset.channel = "in_app";
        node.dataset.externalDelivery = "false";
        $("source-status").insertAdjacentElement("afterend", node);
        return node;
    }

    function showAttention(payload) {
        var attention = payload && payload.attention;
        var node = attentionHost();
        if (!attention) {
            node.textContent = "";
            return;
        }
        node.dataset.channel = "in_app";
        node.dataset.externalDelivery = "false";
        node.textContent = "Unread " + Number(attention.unread_count || 0)
            + ". Review needed " + Number(attention.review_needed_count || 0)
            + ". Updates " + Number(attention.update_count || 0)
            + ". In-app only.";
    }

    function showSources(payload) {
        var sources = payload && payload.sources;
        if (!sources) {
            $("source-status").textContent = "";
            return;
        }
        $("source-status").textContent = "AI mediator " + sources.ai_mediator_turns
            + ". Human messages " + sources.human_messages
            + ". Reviews " + sources.review_decisions
            + ". Case actions " + sources.case_actions
            + ". Projection is not authority.";
    }

    function entryVisible(entry, value) {
        if (!entry || !ATTRIBUTION[entry.record_type]) return false;
        if (entry.record_type !== "human_message") return true;
        return !value.threadId || entry.thread_id === value.threadId;
    }

    function renderEntries(entries, value) {
        var list = $("message-list");
        list.replaceChildren();
        var visible = (entries || []).filter(function (entry) { return entryVisible(entry, value); });
        visible.forEach(function (entry) {
            var kind = ATTRIBUTION[entry.record_type];
            var item = document.createElement("li");
            item.className = "correspondence__message";
            item.setAttribute("data-source-id", String(entry.source_id || ""));
            item.setAttribute("data-record-type", entry.record_type);
            item.setAttribute("data-attribution", kind.attribution);
            item.setAttribute("data-state", "recorded");
            var title = document.createElement("p");
            title.className = "correspondence__kind";
            title.textContent = kind.label;
            var lineage = document.createElement("p");
            lineage.className = "correspondence__lineage";
            var actorText = entry.actor_principal_id || "unknown actor";
            var ownerText = entry.canonical_owner_principal_id || "unknown owner";
            var extra = entry.record_type === "ai_mediator_turn" && entry.invocation_id
                ? " Invocation " + entry.invocation_id + "."
                : "";
            var disposition = entry.disposition ? " Disposition " + entry.disposition + "." : "";
            var workflow = entry.workflow || {};
            item.setAttribute("data-adopted", workflow.adopted === true ? "true" : "false");
            item.setAttribute("data-eligible", workflow.eligible === true ? "true" : "false");
            var attention = entry.attention || {};
            var attentionState = attention.state || "none";
            item.setAttribute("data-attention", attentionState);
            item.setAttribute("data-acknowledged", attention.acknowledged === true ? "true" : "false");
            item.setAttribute("data-external-delivery", "false");
            if (entry.disposition) item.setAttribute("data-disposition", entry.disposition);
            lineage.textContent = "Actor " + actorText + ". Encrypted owner " + ownerText + "."
                + (entry.actor_is_encrypted_owner ? " Actor is the encrypted owner." : " Actor is not the encrypted owner.")
                + extra + disposition
                + (entry.record_type === "human_message" ? " Conversation until an explicit adoption. Not evidence." : "")
                + (entry.record_type === "ai_mediator_turn" ? " Not a human message. Not evidence." : "");
            var body = document.createElement("p");
            body.className = "correspondence__body message-text";
            body.textContent = typeof entry.text === "string" && entry.text !== "" ? entry.text : "No readable text on this record.";
            item.appendChild(title);
            item.appendChild(lineage);
            item.appendChild(body);
            if (workflow.exact === true && workflow.context_kind) {
                var open = document.createElement("button");
                open.type = "button";
                open.className = "correspondence__context-open";
                open.setAttribute("data-source-id", String(entry.source_id || ""));
                open.textContent = "Open " + workflow.context_kind + " context";
                open.addEventListener("click", function () {
                    openContextId = String(entry.source_id || "");
                    showContext(entry, value);
                });
                item.appendChild(open);
            }
            if (attentionState !== "none" && attention.acknowledged !== true) {
                var acknowledge = document.createElement("button");
                acknowledge.type = "button";
                acknowledge.className = "correspondence__acknowledge";
                acknowledge.setAttribute("data-source-id", String(entry.source_id || ""));
                acknowledge.textContent = attentionState === "unread"
                    ? "Acknowledge unread"
                    : (attentionState === "review_needed" ? "Acknowledge review" : "Acknowledge update");
                acknowledge.addEventListener("click", function () {
                    acknowledgeEntry(entry, value);
                });
                item.appendChild(acknowledge);
            }
            if (workflow.eligible === true && workflow.adopted !== true && entry.record_type === "human_message") {
                var adopt = document.createElement("button");
                adopt.type = "button";
                adopt.className = "correspondence__adopt";
                adopt.setAttribute("data-source-id", String(entry.source_id || ""));
                adopt.textContent = "Adopt eligible material";
                adopt.addEventListener("click", function () {
                    adoptMaterial(entry, value);
                });
                item.appendChild(adopt);
            }
            list.appendChild(item);
        });
        if (sendState && current(value)) appendPending(sendState);
        $("empty-conversation").hidden = list.childElementCount !== 0;
        if (openContextId) {
            var opened = visible.filter(function (entry) { return String(entry.source_id || "") === openContextId; })[0];
            if (opened) showContext(opened, value);
        }
    }

    function contextPanel() {
        var panel = $("workflow-context");
        if (panel) return panel;
        panel = document.createElement("section");
        panel.id = "workflow-context";
        panel.tabIndex = -1;
        panel.setAttribute("aria-label", "Workflow context");
        $("message-log").appendChild(panel);
        return panel;
    }

    function showContext(entry, value) {
        var workflow = entry.workflow || {};
        var navigation = workflow.navigation || {};
        var panel = contextPanel();
        panel.replaceChildren();
        panel.setAttribute("data-source-id", String(entry.source_id || ""));
        panel.setAttribute("data-context-kind", String(workflow.context_kind || ""));
        panel.setAttribute("data-context-id", String(workflow.context_id || ""));
        panel.setAttribute("data-context-revision", String(workflow.context_revision == null ? "" : workflow.context_revision));
        panel.setAttribute("data-attribution", String(workflow.attribution || ""));
        panel.setAttribute("data-adopted", workflow.adopted === true ? "true" : "false");
        panel.setAttribute("data-eligible", workflow.eligible === true ? "true" : "false");
        panel.setAttribute("data-case-id", value && value.caseId ? value.caseId : "");
        if (navigation.span) panel.setAttribute("data-span", String(navigation.span));
        else panel.removeAttribute("data-span");
        if (navigation.section_id) panel.setAttribute("data-section-id", String(navigation.section_id));
        else panel.removeAttribute("data-section-id");
        var heading = document.createElement("h3");
        heading.textContent = workflow.exact === true
            ? "Exact " + workflow.context_kind + " context"
            : "No workflow context";
        var detail = document.createElement("p");
        detail.className = "workflow-context__identity";
        if (workflow.exact === true) {
            detail.textContent = "Case " + (navigation.case_id || "")
                + ". " + workflow.context_kind + " " + workflow.context_id
                + ". Revision " + workflow.context_revision
                + (navigation.span ? ". Span " + navigation.span : "")
                + (navigation.section_id ? ". Section " + navigation.section_id : "")
                + ".";
        } else {
            detail.textContent = "This record has no exact evidence, draft, or inquiry context.";
        }
        var boundary = document.createElement("p");
        boundary.className = "workflow-context__boundary";
        boundary.textContent = workflow.adopted === true
            ? "Adopted by an explicit authorized action. Display did not adopt it."
            : "Opening this context does not adopt it. Displayed text is not evidence or an accepted fact.";
        if (entry.record_type === "ai_mediator_turn") {
            boundary.textContent += " AI text stays AI text and is not a human message.";
        }
        if (entry.record_type === "human_message") {
            boundary.textContent += " The human message stays conversation.";
        }
        panel.appendChild(heading);
        panel.appendChild(detail);
        panel.appendChild(boundary);
        panel.hidden = false;
        if (document.activeElement && document.activeElement.classList
            && (document.activeElement.classList.contains("correspondence__context-open")
                || document.activeElement.id === "workflow-context")) {
            panel.focus();
        }
    }

    function adoptMaterial(entry, value) {
        var workflow = entry.workflow || {};
        if (!workflow.eligible || entry.record_type !== "human_message" || !value.threadId) return;
        var sourceId = String(entry.source_id || "");
        if (!adoptionKeys[sourceId]) adoptionKeys[sourceId] = newKey("adopt-");
        openContextId = sourceId;
        enqueue(async function () {
            if (!current(value)) return;
            setError("");
            setStatus("Adopting linked material");
            var payload = await api(
                "/api/cases/messages/threads/" + encodeURIComponent(value.threadId) + "/messages/" + encodeURIComponent(sourceId) + "/workflow-adoption",
                {
                    method: "POST",
                    lane: "adopt",
                    body: Object.assign({
                        case_id: value.caseId,
                        idempotency_key: adoptionKeys[sourceId],
                        context_kind: workflow.context_kind,
                        context_id: workflow.context_id,
                        context_revision: workflow.context_revision,
                        section_id: workflow.section_id,
                        span: workflow.span,
                        expected_message_version: entry.revision
                    }, membershipFields(value))
                },
                value
            );
            if (!current(value)) return;
            if (payload.adopted !== true || payload.explicit !== true || payload.accepted_by_display !== false) {
                throw new Error("adoption_rejected");
            }
            if (payload.disposition !== "conversation" || payload.attribution !== "human") {
                throw new Error("adoption_rejected");
            }
            if (payload.context.context_id !== workflow.context_id || payload.context.context_revision !== workflow.context_revision) {
                throw new Error("workflow_context_mismatch");
            }
            await loadProjection(value);
            if (!current(value)) return;
            setStatus("Adopted linked material");
            setError("");
        }).catch(function (error) {
            if (!current(value)) return;
            if (error && (error.message === "action_not_permitted" || error.message === "workflow_context_required" || error.message === "material_not_eligible" || error.message === "display_is_not_adoption")) {
                setStatus("Adoption was not authorized");
                setError(error.message);
                return;
            }
            failed(value, error);
        });
    }

    function appendPending(state) {
        var list = $("message-list");
        var item = document.createElement("li");
        item.className = "correspondence__message";
        item.setAttribute("data-state", state.phase);
        item.setAttribute("data-attribution", "human");
        item.setAttribute("data-record-type", "pending_human_message");
        var title = document.createElement("p");
        title.className = "correspondence__kind";
        title.textContent = state.phase === "error" ? "Human send failed" : "Human send pending";
        var body = document.createElement("p");
        body.className = "correspondence__body";
        body.textContent = state.text;
        item.appendChild(title);
        item.appendChild(body);
        list.appendChild(item);
        $("empty-conversation").hidden = true;
    }

    function acknowledgeEntry(entry, value) {
        var attention = entry.attention || {};
        if (!attention.state || attention.state === "none" || attention.acknowledged === true) return;
        var sourceId = String(entry.source_id || "");
        var generation = pollGeneration;
        enqueue(async function () {
            if (!current(value) || generation !== pollGeneration) return;
            setError("");
            setStatus("Acknowledging");
            var payload = await api("/api/cases/correspondence/acknowledgements", {
                method: "POST",
                lane: "ack",
                body: Object.assign({
                    case_id: value.caseId,
                    source_id: sourceId,
                    record_type: entry.record_type,
                    revision: entry.revision
                }, membershipFields(value))
            }, value);
            if (!current(value) || generation !== pollGeneration) return;
            if (payload.acknowledged !== true || payload.external_delivery !== false || payload.case_id !== value.caseId) {
                throw new Error("acknowledgement_rejected");
            }
            if (payload.email !== false || payload.sms !== false) throw new Error("acknowledgement_rejected");
            await loadProjection(value);
            if (!current(value) || generation !== pollGeneration) return;
            setStatus("Acknowledged");
            setError("");
        }).catch(function (error) {
            if (!current(value) || generation !== pollGeneration) return;
            failed(value, error);
        });
    }

    async function loadProjection(value) {
        value = value || capture();
        var generation = pollGeneration;
        if (!current(value) || !value.caseId) return null;
        var payload = await api(query("/api/cases/correspondence", {}, value), undefined, value);
        if (!current(value) || generation !== pollGeneration) return null;
        if (payload.case_id !== value.caseId || payload.actor_principal_id !== value.actor) throw new Error("view_changed");
        if (payload.projection_is_authority !== false) throw new Error("projection_rejected");
        if (payload.external_delivery !== false) throw new Error("projection_rejected");
        showLimitations(payload);
        showSources(payload);
        showAttention(payload);
        renderEntries(payload.entries || [], value);
        return payload;
    }

    async function poll(value) {
        value = value || capture();
        if (!current(value) || !value.caseId) return;
        var generation = pollGeneration;
        try {
            await loadProjection(value);
            if (current(value) && generation === pollGeneration) setStatus("Polled correspondence over HTTP");
            if (current(value)) setError("");
        } catch (error) {
            failed(value, error);
        }
    }

    function startPolling(value) {
        stopPoll();
        var generation = pollGeneration;
        pollTimer = window.setInterval(function () {
            if (generation !== pollGeneration) return;
            enqueue(function () { return poll(value); });
        }, pollMs());
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
            button.setAttribute("data-thread-id", thread.thread_id);
            button.textContent = "Thread " + thread.thread_id + ", " + thread.message_count + " messages";
            button.addEventListener("click", function () {
                if (value.actor !== actor || value.privacy !== privacyEpoch || value.caseId !== caseId()) return;
                openThread(thread.thread_id);
            });
            item.appendChild(button);
            list.appendChild(item);
        });
        setStatus("Loaded " + (payload.threads || []).length + " threads");
        await loadProjection(capture());
    }

    function openThread(id) {
        stopPoll();
        viewToken += 1;
        sendState = null;
        $("thread-id").value = id;
        $("message-text").value = "";
        setComposer("idle", "Ready");
        setError("");
        var value = capture();
        enqueue(async function () {
            if (!current(value)) return;
            await loadProjection(value);
            if (!current(value)) return;
            startPolling(value);
            setStatus("Opened thread");
            $("message-text").focus();
        }).catch(function (error) { failed(value, error); });
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

    function retriable(error) {
        if (!error || error.message === "view_changed" || error.message === "aborted") return false;
        if (error.message === "message_unavailable" || clearingError(error)) return false;
        return error.status === 502 || error.status === 503 || error.status === 504 || error.status === 0;
    }

    async function deliver(value, text, key, attempt) {
        // The composer stays pending through an automatic retry. The transport
        // bridge does not yield to the page until the first response returns,
        // so a retrying attribute would already have replaced pending before
        // the caller can observe the in-flight send.
        sendState = { phase: "pending", text: text, key: key, threadId: value.threadId };
        setComposer("pending", attempt > 1 ? "Retrying send" : "Sending");
        renderEntries(projectedEntries.slice(), value);
        try {
            var payload = await api("/api/cases/messages/threads/" + encodeURIComponent(value.threadId) + "/messages", {
                method: "POST",
                body: Object.assign({
                    case_id: value.caseId,
                    text: text,
                    idempotency_key: key
                }, membershipFields(value))
            }, value);
            if (!current(value)) return;
            if (payload.case_id !== value.caseId || payload.thread_id !== value.threadId) throw new Error("view_changed");
            if (payload.sender_principal_id !== value.actor) throw new Error("actor_mismatch");
            sendState = null;
            $("message-text").value = "";
            setComposer("sent", "Sent");
            await loadProjection(value);
            if (!current(value)) return;
            setStatus("Sent message");
            setError("");
            $("message-text").focus();
        } catch (error) {
            if (!current(value) || error.message === "view_changed" || error.message === "aborted") return;
            if (clearingError(error)) {
                failed(value, error);
                return;
            }
            if (attempt < MAX_SEND_ATTEMPTS && retriable(error)) {
                setComposer("pending", "Retrying send");
                // Yield while the composer is still pending. The same-origin
                // bridge blocks the page for the whole first response, so the
                // caller can observe the disabled pending control only in this
                // gap before the retry request starts.
                await new Promise(function (resolve) { window.setTimeout(resolve, 400); });
                if (!current(value)) return;
                return deliver(value, text, key, attempt + 1);
            }
            sendState = { phase: "error", text: text, key: key, threadId: value.threadId };
            $("message-text").value = text;
            setComposer("error", "Send failed");
            renderEntries(projectedEntries.slice(), value);
            setError(error.message || "request_failed");
            $("retry-send").focus();
        }
    }

    var projectedEntries = [];

    function lastEntries(value) {
        return projectedEntries.filter(function (entry) { return entryVisible(entry, value); });
    }

    var originalRender = renderEntries;
    renderEntries = function (entries, value) {
        projectedEntries = entries.slice();
        originalRender(entries, value);
    };

    function beginSend(existingKey) {
        var text = $("message-text").value;
        if (text.trim() === "") return;
        var value = capture();
        if (!value.threadId || !value.caseId) {
            setError("thread_required");
            return;
        }
        if (sendState && (sendState.phase === "pending" || sendState.phase === "retrying")) return;
        var key = existingKey || (sendState && sendState.phase === "error" ? sendState.key : "") || newKey("compose-");
        sendState = { phase: "pending", text: text, key: key, threadId: value.threadId };
        setError("");
        setComposer("pending", existingKey ? "Retrying send" : "Sending");
        renderEntries(projectedEntries.slice(), value);
        enqueue(function () { return deliver(value, text, key, 1); }).catch(function (error) { failed(value, error); });
    }

    $("case-select").addEventListener("change", function () {
        var selected = $("case-select").value;
        clearView(true);
        $("case-id").value = selected;
        $("thread-id").value = "";
    });

    $("inbox-login").addEventListener("submit", function (event) {
        event.preventDefault();
        var credential = $("inbox-credential").value;
        clearIdentity();
        var attempt = privacyEpoch;
        $("inbox-credential").value = "";
        setError("");
        enqueue(async function () {
            var response = await fetch("/api/complaint-workspace/auth/login", {
                method: "POST",
                credentials: "same-origin",
                headers: { "content-type": "application/json", "accept": "application/json" },
                body: JSON.stringify({ credential: credential })
            });
            var payload = await response.json();
            if (attempt !== privacyEpoch) return;
            if (!response.ok || payload.authenticated !== true || typeof payload.principal_id !== "string"
                || !Number.isSafeInteger(payload.generation) || !payload.csrf_token) {
                throw new Error(payload.error || "login_failed");
            }
            actor = payload.principal_id;
            authGeneration = payload.generation;
            csrf = payload.csrf_token;
            $("inbox-auth-status").textContent = "Signed in";
            var signedIn = capture();
            await refreshCases(signedIn);
            if (current(signedIn)) {
                setStatus("Signed in");
                $("case-select").focus();
            }
        }).catch(function (error) {
            if (attempt !== privacyEpoch) return;
            clearIdentity();
            $("inbox-auth-status").textContent = "Sign in required";
            setError(error.message || "login_failed");
        });
    });

    $("load-threads").addEventListener("click", function () {
        var value = capture();
        enqueue(function () { return loadThreads(value); }).catch(function (error) { failed(value, error); });
    });

    $("create-thread").addEventListener("click", function () {
        var value = capture();
        var key = newKey("thread-");
        enqueue(async function () {
            if (!current(value)) return;
            setError("");
            setStatus("Creating thread");
            var payload = await api("/api/cases/messages/threads", {
                method: "POST",
                body: Object.assign({ case_id: value.caseId, idempotency_key: key }, membershipFields(value))
            }, value);
            if (!current(value) || payload.case_id !== value.caseId) return;
            await loadThreads(capture());
            openThread(payload.thread_id);
        }).catch(function (error) { failed(value, error); });
    });

    $("refresh-messages").addEventListener("click", function () {
        var value = capture();
        enqueue(function () { return poll(value); });
    });

    $("send-message").addEventListener("submit", function (event) {
        event.preventDefault();
        beginSend();
    });

    $("message-text").addEventListener("keydown", function (event) {
        if ((event.ctrlKey || event.metaKey) && event.key === "Enter") {
            event.preventDefault();
            beginSend();
        }
    });

    $("retry-send").addEventListener("click", function () {
        if (!sendState || sendState.phase !== "error") return;
        beginSend(sendState.key);
    });

    ["case-id", "thread-id", "membership-grant-id", "membership-version"].forEach(function (id) {
        $(id).addEventListener("input", function () {
            clearView(id !== "thread-id");
            if (id === "case-id") {
                $("thread-id").value = "";
                $("membership-grant-id").value = "";
                $("membership-version").value = "";
            }
        });
    });

    window.addEventListener("pagehide", function () {
        clearIdentity();
    });

    var messageKeyEpoch = null;
    window.addEventListener("complaint-key-coherence", function (event) {
        var detail = event.detail || {};
        if (!$("message-list")) return;
        var epoch = Number(detail.epoch || 0);
        var moved = messageKeyEpoch !== null && messageKeyEpoch !== epoch;
        messageKeyEpoch = epoch;
        if (detail.clear_plaintext || (moved && detail.status !== "unlocked")) {
            clearView(true);
            setError("");
            setStatus(detail.recovery_guidance || "Messages were cleared until this case key is available again.");
            return;
        }
        if (detail.status === "unlocked" && (detail.reload === true || moved) && caseId()) {
            var value = capture();
            enqueue(function () { return loadThreads(value); }).catch(function (error) { failed(value, error); });
        }
    });

    setComposer("idle", "Ready");
})();
