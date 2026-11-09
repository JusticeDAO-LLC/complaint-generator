/* Projects the canonical workspace session into a mediator conversation.
   It does not start an interview, store the complaint, or adopt model text. */
(function () {
    var MAX_RETRIES = 3;
    var BLOCKED = { "missing-key": true, denied: true, unavailable: true, locked: true, revoked: true };
    var root = null;
    var generation = 0;
    var renderedHead = null;
    var renderedCaseId = "";
    var submitting = false;
    var submissionEpoch = 0;
    var retryCount = 0;
    var lifecycle = "idle";
    var controller = null;
    var lastPayload = null;
    var lateGate = {
        displayAllowed: false,
        purpose: "",
        generation: "",
        resultId: "",
        code: "local_private",
        suppressed: false,
        cancelledIds: {}
    };

    function $(id) { return document.getElementById(id); }

    function text(value) {
        if (value === undefined || value === null) return "";
        return String(value).replace(/\s+/g, " ").trim();
    }

    function escapeHtml(value) {
        return text(value).replace(/[&<>"']/g, function (ch) {
            return ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[ch];
        });
    }

    function shellState() {
        var shell = $("complaint-case-shell");
        var entry = $("complaint-entry");
        return {
            shell: shell ? (shell.dataset.state || "") : "",
            entry: entry ? (entry.dataset.entry || "") : "",
            caseLabel: text(($("complaint-case-shell-case") || {}).textContent),
            caseId: shell ? (($("complaint-case-shell-case") || {}).dataset || {}).caseId || "" : ""
        };
    }

    function blocked() {
        var state = shellState();
        return BLOCKED[state.shell] || BLOCKED[state.entry] || state.entry === "missing-key";
    }

    function sessionOf(payload) {
        if (!payload || typeof payload !== "object") return {};
        if (payload.session && typeof payload.session === "object") return payload.session;
        return {};
    }

    function documentsOf(session, payload) {
        var evidence = session.evidence && typeof session.evidence === "object" ? session.evidence : {};
        var review = payload && payload.review && typeof payload.review === "object" ? payload.review : {};
        var documents = [].concat(Array.isArray(evidence.documents) ? evidence.documents : [], Array.isArray(review.documents) ? review.documents : []);
        var testimony = [].concat(Array.isArray(evidence.testimony) ? evidence.testimony : [], Array.isArray(review.testimony) ? review.testimony : []);
        var seen = {};
        return documents.concat(testimony).filter(function (item) {
            if (!item || typeof item !== "object") return false;
            var key = text(item.id) || text(item.title);
            if (!key || seen[key]) return false;
            seen[key] = true;
            return true;
        });
    }

    function selectedEvidenceTitle(items) {
        var list = $("evidence-list");
        var selected = list ? text(list.dataset.selectedId) : "";
        var match = null;
        items.forEach(function (item) {
            if (!item || typeof item !== "object") return;
            if (selected && text(item.id) === selected) match = item;
        });
        var chosen = match || items[0];
        if (!chosen) return "";
        return text(chosen.title || chosen.label || chosen.name);
    }

    function suggestionRecord(source) {
        if (!source || typeof source !== "object") return null;
        var wording = text(source.wording || source.name || source.text || (source.attributes && source.attributes.wording));
        if (!wording || (source.record_type && source.record_type !== "model_suggestion")) return null;
        return {
            wording: wording,
            late: source.late_result === true,
            purpose: text(source.purpose),
            generation: source.consent_generation === undefined || source.consent_generation === null ? "" : String(source.consent_generation),
            resultId: text(source.result_id),
            implied: source.key_unlocked === true || source.key_unlock === true || source.unlocked === true
                || !!source.staff_role || source.development_provider_authorization === true
                || source.development_provider_authorized === true
        };
    }

    function lateAdmitted(item) {
        if (!item || !item.late) return true;
        if (item.implied || lateGate.suppressed || lateGate.cancelledIds[item.resultId]) return false;
        return lateGate.displayAllowed === true
            && item.purpose === lateGate.purpose
            && item.generation === String(lateGate.generation)
            && item.resultId === lateGate.resultId
            && item.resultId !== "";
    }

    function suggestionsOf(session) {
        var found = [];
        var interview = session.shared_interview && typeof session.shared_interview === "object" ? session.shared_interview : {};
        var pending = interview.pending_inquiry && typeof interview.pending_inquiry === "object" ? interview.pending_inquiry : {};
        var proposal = pending.model_proposal && typeof pending.model_proposal === "object" ? pending.model_proposal : null;
        var direct = suggestionRecord(proposal);
        if (direct) found.push(direct);
        var graph = interview.knowledge_graph && typeof interview.knowledge_graph === "object" ? interview.knowledge_graph : {};
        var rows = [].concat(Array.isArray(graph.entities) ? graph.entities : [], Array.isArray(graph.nodes) ? graph.nodes : []);
        rows.forEach(function (row) {
            var item = suggestionRecord(row);
            if (item) found.push(item);
        });
        return found;
    }

    function messagesFrom(payload) {
        var session = sessionOf(payload);
        var interview = session.shared_interview && typeof session.shared_interview === "object" ? session.shared_interview : {};
        var pending = interview.pending_inquiry && typeof interview.pending_inquiry === "object" ? interview.pending_inquiry : null;
        var complaint = session.original_complaint && typeof session.original_complaint === "object" ? session.original_complaint : {};
        var narrative = text(complaint.text);
        var messages = [];
        if (narrative) {
            messages.push({
                type: "user-statement",
                kind: "Your statement",
                body: narrative,
                why: "You entered this for the current case. It is not a legal conclusion."
            });
        }
        var history = Array.isArray(session.intake_history) ? session.intake_history : [];
        history.forEach(function (item) {
            if (!item || typeof item !== "object") return;
            var answer = text(item.answer);
            if (!answer || answer === narrative) return;
            messages.push({
                type: "user-statement",
                kind: "Your statement",
                body: answer,
                why: "This is a recorded answer on the case. It stays separate from evidence and from model text."
            });
        });
        if (pending && text(pending.question)) {
            var explanation = pending.inquiry_explanation && typeof pending.inquiry_explanation === "object" ? pending.inquiry_explanation : {};
            messages.push({
                type: "ai-question",
                kind: "Mediator question",
                body: text(pending.question),
                why: text(explanation.why_asked) || "This is the current question from the shared mediator."
            });
        }
        var suggestions = suggestionsOf(session);
        if (!suggestions.length) {
            messages.push({
                type: "model-suggestion",
                kind: "Model suggestion",
                body: "No model suggestion is available for this case.",
                why: "A missing suggestion is not a fact, evidence, or legal requirement.",
                availability: "unavailable"
            });
        } else {
            suggestions.forEach(function (item) {
                if (item.late && !lateAdmitted(item)) {
                    messages.push({
                        type: "model-suggestion",
                        kind: "Model suggestion",
                        body: "A remote Grok result is withheld. Current case consent does not allow it to be shown.",
                        why: "Revocation, cancellation, unlock, a staff role, development authorization, or a missing consent flag cannot admit a late result.",
                        availability: "withheld"
                    });
                    return;
                }
                messages.push({
                    type: "model-suggestion",
                    kind: "Model suggestion",
                    body: item.wording,
                    why: "This is a model suggestion. It is not adopted as a fact, as evidence, or as law.",
                    availability: item.late ? "admitted" : "available"
                });
            });
        }
        messages.push({
            type: "system-outcome",
            kind: "System outcome",
            body: stoppingCopy(classifyStopping(payload)).summary,
            why: "System text reports the interview state. It does not adopt an answer and it is not legal sufficiency."
        });
        return messages;
    }

    function reasonBlob(payload, outcome, policy) {
        var reasons = [].concat(
            Array.isArray(outcome.unresolved_reasons) ? outcome.unresolved_reasons : [],
            Array.isArray(policy.remaining_issues) ? policy.remaining_issues : []
        );
        var parts = [text(policy.dependency_lane), text(policy.stopping_distinction), text(outcome.state)];
        reasons.forEach(function (item) {
            if (!item || typeof item !== "object") {
                parts.push(text(item));
                return;
            }
            parts.push(text(item.code), text(item.reason), text(item.detail), text(item.dependency_lane), text(item.lane), text(item.target_kind));
        });
        return parts.join(" ").toLowerCase();
    }

    function classifyStopping(payload) {
        var source = payload && typeof payload === "object" ? payload : {};
        var outcome = source.finite_interview_outcome && typeof source.finite_interview_outcome === "object" ? source.finite_interview_outcome : {};
        var policy = source.stopping_policy && typeof source.stopping_policy === "object" ? source.stopping_policy : {};
        var session = sessionOf(source);
        var interview = session.shared_interview && typeof session.shared_interview === "object" ? session.shared_interview : {};
        var pending = interview.pending_inquiry && typeof interview.pending_inquiry === "object" ? interview.pending_inquiry : null;
        var hasQuestion = !!(pending && text(pending.question));
        var stop = text(outcome.stop || policy.outcome).toLowerCase();
        var blob = reasonBlob(source, outcome, policy);
        var legalGap = /legal|source_research|authority|governing/.test(blob);
        var evidentiaryGap = /evidence|proof|document|evidentiary/.test(blob);
        var answers = session.intake_answers && typeof session.intake_answers === "object" ? session.intake_answers : {};
        var filledForm = Object.keys(answers).some(function (key) { return text(answers[key]); });
        var conversation = source.conversation_state && typeof source.conversation_state === "object" ? source.conversation_state : {};
        var noMoreQuestions = !hasQuestion && (conversation.is_complete === true || /no further/.test(text(source.message).toLowerCase()) || stop === "saturated");
        var completedTask = source.stored_as_answer === true || conversation.is_complete === true;
        var distinction = "awaiting_answer";
        if (stop === "paused" || stop === "user_pause") distinction = "user_pause";
        else if (stop === "cancelled" || stop === "cancellation") distinction = "cancellation";
        else if (stop === "capped" || stop === "cap" || stop === "limit_reached" || stop === "no_progress") distinction = "cap";
        else if (stop === "unavailable" || stop === "blocked_provider" || stop === "provider_unavailable") distinction = "unavailable_source";
        else if (stop === "saturated" || stop === "saturation" || stop === "complete") distinction = "saturation";
        else if (!hasQuestion) distinction = "no_actionable_question";
        var head = source.encrypted_head && typeof source.encrypted_head === "object" ? source.encrypted_head : {};
        return {
            distinction: distinction,
            legalGap: legalGap,
            evidentiaryGap: evidentiaryGap,
            legalSufficiency: false,
            noMoreQuestions: noMoreQuestions,
            filledForm: filledForm,
            completedTask: completedTask,
            inquiryId: hasQuestion ? text(pending.inquiry_id) : "",
            question: hasQuestion ? text(pending.question) : "",
            revision: hasQuestion && pending.revision !== undefined && pending.revision !== null ? String(pending.revision) : "",
            privateRevision: head.private_revision === undefined || head.private_revision === null ? "" : String(head.private_revision)
        };
    }

    function stoppingCopy(view) {
        var next = {
            awaiting_answer: "Answer, mark unknown, or defer the current question. The saved question stays until you do.",
            no_actionable_question: "There is no further actionable question. Review the open factual, evidence, and legal gaps. An empty question list is not legal sufficiency.",
            user_pause: "You paused. Resume returns the same saved question. This wait is not a stalled worker and is not legal sufficiency.",
            cancellation: "The interview was cancelled. Unresolved issues stay open. Cancellation is not legal sufficiency.",
            cap: "A question, iteration, or budget cap stopped new questions. Review what is still unresolved. A cap is not legal sufficiency.",
            saturation: "The interview is saturated. Open gaps remain. Saturation is not legal sufficiency or court readiness.",
            unavailable_source: "A required source or provider is unavailable. Retry when it is available. Unavailability is not legal sufficiency."
        };
        var summary = {
            awaiting_answer: "The mediator is waiting for your answer. Answer the current question to continue.",
            no_actionable_question: "No actionable question is waiting. That is an interview outcome, not legal sufficiency.",
            user_pause: "You paused the interview. The saved question is unchanged.",
            cancellation: "The interview was cancelled. Unresolved reasons stay visible.",
            cap: "A cap stopped the interview. Unresolved reasons stay visible.",
            saturation: "The interview is saturated. Unresolved reasons stay visible.",
            unavailable_source: "A source or provider is unavailable. Unresolved reasons stay visible."
        };
        var extra = "";
        if (view.legalGap) extra += " A legal or source gap is still open. Acquire or admit the source before treating that point as supported.";
        if (view.evidentiaryGap) extra += " An evidence gap is still open. A filled form is not source-bound evidence.";
        if (view.filledForm) extra += " Filled intake fields are not legal sufficiency.";
        if (view.completedTask || view.noMoreQuestions) extra += " A completed software task and a finished question list are not legal sufficiency.";
        return {
            summary: summary[view.distinction] || summary.no_actionable_question,
            next: (next[view.distinction] || next.no_actionable_question) + extra
        };
    }

    function paintStopping(payload) {
        if (!payload) {
            ["conversation-stopping", "finite-interview-outcome"].forEach(function (id) {
                var panel = $(id);
                if (!panel) return;
                panel.dataset.distinction = "";
                panel.dataset.legalSufficiency = "false";
                panel.dataset.inquiryId = "";
                panel.dataset.revision = "";
            });
            var idleSummary = $("conversation-stopping-summary");
            if (idleSummary) idleSummary.textContent = "Stopping has not been read. No further questions, a filled form, and a completed software task are not legal sufficiency.";
            var idleNext = $("conversation-stopping-next");
            if (idleNext) idleNext.textContent = "";
            return null;
        }
        var view = classifyStopping(payload);
        var copy = stoppingCopy(view);
        var nodes = [
            { panel: "conversation-stopping", summary: "conversation-stopping-summary", next: "conversation-stopping-next" },
            { panel: "finite-interview-outcome", summary: "finite-interview-summary", next: "finite-interview-next" }
        ];
        nodes.forEach(function (ids) {
            var panel = $(ids.panel);
            if (!panel) return;
            var serverStop = text((payload && payload.finite_interview_outcome && payload.finite_interview_outcome.stop) || "");
            panel.dataset.distinction = view.distinction;
            if (serverStop) panel.dataset.stop = serverStop;
            else if (!panel.dataset.stop) panel.dataset.stop = view.distinction;
            panel.dataset.legalSufficiency = "false";
            panel.dataset.legalGap = view.legalGap ? "true" : "false";
            panel.dataset.evidentiaryGap = view.evidentiaryGap ? "true" : "false";
            panel.dataset.noMoreQuestions = view.noMoreQuestions ? "true" : "false";
            panel.dataset.filledForm = view.filledForm ? "true" : "false";
            panel.dataset.completedTask = view.completedTask ? "true" : "false";
            panel.dataset.inquiryId = view.inquiryId;
            panel.dataset.revision = view.revision;
            panel.dataset.privateRevision = view.privateRevision;
            var summary = $(ids.summary);
            var next = $(ids.next);
            if (summary) summary.textContent = copy.summary;
            if (next) next.textContent = copy.next;
        });
        var sufficiency = $("finite-interview-sufficiency");
        if (sufficiency) {
            sufficiency.textContent = "No further questions, a filled intake form, and a completed software task are not legal sufficiency. Support requires source-bound factual or legal evidence.";
        }
        var gaps = $("finite-interview-gaps");
        if (gaps) {
            var gapText = [];
            if (view.legalGap) gapText.push("Legal or source gap: still unresolved.");
            if (view.evidentiaryGap) gapText.push("Evidence gap: still unresolved.");
            if (!gapText.length) gapText.push("No separate legal or evidence gap is marked on this stop.");
            gaps.textContent = gapText.join(" ");
        }
        return view;
    }

    function paintControls() {
        if (!root) return;
        root.dataset.lifecycle = lifecycle;
        root.dataset.retryCount = String(retryCount);
        root.setAttribute("aria-busy", lifecycle === "pending" ? "true" : "false");
        var refresh = $("mediator-conversation-refresh");
        var cancel = $("mediator-conversation-cancel");
        var retry = $("mediator-conversation-retry");
        if (refresh) refresh.disabled = lifecycle === "pending" || lifecycle === "retry-exhausted" || blocked();
        if (cancel) cancel.disabled = lifecycle !== "pending";
        if (retry) retry.disabled = !((lifecycle === "error" || lifecycle === "cancelled") && retryCount < MAX_RETRIES);
        var status = $("mediator-conversation-status");
        if (!status) return;
        var copy = {
            idle: "The conversation has not been loaded.",
            settled: "The conversation matches the latest confirmed case session.",
            pending: "Reading the case session. You can cancel this refresh.",
            cancelled: "Refresh cancelled. The conversation still shows the last confirmed case.",
            error: "The case session could not be read. Retry is available until the limit.",
            "retry-exhausted": "The retry limit was reached. The conversation was not read again.",
            blocked: "This case cannot be shown. No conversation text is available."
        };
        status.textContent = copy[lifecycle] || copy.idle;
        paintLate();
    }

    function paintLate() {
        var node = $("conversation-late-result");
        var privacy = $("conversation-privacy");
        if (privacy) {
            privacy.dataset.defaultProcessing = "local_private";
            privacy.dataset.egressAuthorized = lateGate.displayAllowed ? "true" : "false";
        }
        if (!node) return;
        node.dataset.displayAllowed = lateGate.displayAllowed ? "true" : "false";
        node.dataset.admission = lateGate.displayAllowed ? "admitted" : "withheld";
        node.dataset.code = lateGate.code || "local_private";
        node.textContent = lateGate.displayAllowed
            ? "The late Grok 4.7 result matches the current persisted case and purpose consent."
            : "No remote Grok result is admitted. Processing stays on this machine until persisted case and purpose consent is current.";
    }

    function render(payload) {
        placeInquiryWorkbench();
        root = $("mediator-conversation");
        if (!root) return;
        var log = $("mediator-conversation-log");
        var context = $("mediator-conversation-context");
        var actions = $("mediator-conversation-actions");
        if (!log || !context || !actions) return;
        if (blocked()) {
            log.replaceChildren();
            context.textContent = "Case access does not allow this conversation to be shown.";
            actions.replaceChildren();
            lifecycle = "blocked";
            paintControls();
            renderInquiryCard(payload);
            return;
        }
        var session = sessionOf(payload);
        var items = documentsOf(session, payload);
        var evidenceTitle = selectedEvidenceTitle(items);
        var label = shellState().caseLabel;
        if (!label || label === "No case selected") label = "the open case";
        context.textContent = "Case: " + label + ". Evidence: " + (evidenceTitle || "none attached yet") + ".";
        var messages = messagesFrom(payload || {});
        log.innerHTML = messages.map(function (message, index) {
            var id = "mediator-conversation-kind-" + index;
            return '<li class="mediator-conversation__message" data-message-type="' + message.type + '" data-availability="' + escapeHtml(message.availability || "shown") + '" role="article">'
                + '<p class="mediator-conversation__kind" id="' + id + '">' + escapeHtml(message.kind) + "</p>"
                + '<p class="mediator-conversation__body">' + escapeHtml(message.body) + "</p>"
                + '<p class="mediator-conversation__why">Why this is here: ' + escapeHtml(message.why) + "</p>"
                + "</li>";
        }).join("");
        var buttons = [];
        var pending = session.shared_interview && session.shared_interview.pending_inquiry;
        if (pending && text(pending.question)) {
            buttons.push('<button type="button" data-conversation-action="answer">Answer the current question</button>');
        } else if (!text((session.original_complaint || {}).text)) {
            buttons.push('<button type="button" data-conversation-action="narrative">Enter what happened</button>');
        }
        if (items.length) buttons.push('<button type="button" data-conversation-action="evidence">Review the case evidence</button>');
        actions.innerHTML = buttons.join("");
        if (lifecycle !== "pending" && lifecycle !== "error" && lifecycle !== "cancelled" && lifecycle !== "retry-exhausted") {
            lifecycle = messages.length ? "settled" : "idle";
        }
        paintControls();
        renderInquiryCard(payload);
        paintStopping(payload);
    }

    function placeInquiryWorkbench() {
        var panel = document.querySelector("#complaint-case-shell [data-case-panel='mediator']");
        var card = $("inquiry-card");
        var editor = $("inquiry-response-editor");
        if (!panel || !card || !editor) return;
        // Keep the original controls and their privacy/revision handlers.
        // Shell summary refreshes replace the body, so retain these siblings.
        [card, editor].forEach(function (node) {
            if (node.parentNode !== panel) panel.appendChild(node);
        });
    }

    function inquiryRecord(payload) {
        var session = sessionOf(payload);
        var interview = session.shared_interview && typeof session.shared_interview === "object" ? session.shared_interview : {};
        var pending = interview.pending_inquiry && typeof interview.pending_inquiry === "object" ? interview.pending_inquiry : null;
        var adaptive = payload && payload.adaptive_inquiry && typeof payload.adaptive_inquiry === "object" ? payload.adaptive_inquiry : null;
        return { session: session, interview: interview, pending: pending, adaptive: adaptive };
    }

    function allowedInquiryActions(record) {
        var pending = record.pending;
        var adaptive = record.adaptive;
        var issued = pending && text(pending.question) && text(pending.inquiry_id).indexOf("inq-") === 0;
        if (!issued || (adaptive && adaptive.from_fixed_intake_fields === true)) return [];
        var declared = pending.allowed_actions || (adaptive && adaptive.allowed_actions);
        var known = { answer: true, unknown: true, defer: true, deferred: true };
        if (Array.isArray(declared) && declared.length) {
            return declared.map(function (item) { return text(item).toLowerCase(); }).filter(function (item) {
                return known[item] === true;
            }).map(function (item) { return item === "deferred" ? "defer" : item; });
        }
        return ["answer", "unknown", "defer"];
    }

    function renderInquiryCard(payload) {
        var card = $("inquiry-card");
        if (!card) return;
        var questionNode = $("inquiry-card-question");
        var revisionNode = $("inquiry-card-revision");
        var whyNode = $("inquiry-card-explanation");
        var gapsNode = $("inquiry-card-gaps");
        var requirementsNode = $("inquiry-card-requirements");
        var actionsNode = $("inquiry-card-actions");
        var note = $("inquiry-card-note");
        if (!questionNode || !revisionNode || !whyNode || !gapsNode || !requirementsNode || !actionsNode) return;
        var editor = $("inquiry-response-editor");
        if (blocked()) {
            if (editor) editor.hidden = true;
            card.dataset.pending = "false";
            card.dataset.inquiryId = "";
            card.dataset.revision = "";
            card.dataset.fromFixedIntake = "false";
            card.dataset.storesAnswer = "false";
            questionNode.textContent = "This case cannot be shown. No question is available.";
            revisionNode.textContent = "";
            whyNode.textContent = "";
            gapsNode.replaceChildren();
            requirementsNode.replaceChildren();
            actionsNode.replaceChildren();
            if (note && note.dataset.action !== "why" && note.dataset.action !== "status") {
                note.textContent = "Why and status read the interview. They do not save an answer.";
            }
            return;
        }
        var record = inquiryRecord(payload || {});
        var pending = record.pending;
        var explanation = pending && pending.inquiry_explanation && pending.inquiry_explanation.schema === "inquiry-explanation-v1"
            ? pending.inquiry_explanation : null;
        var issued = pending && text(pending.question) && text(pending.inquiry_id).indexOf("inq-") === 0
            && !(record.adaptive && record.adaptive.from_fixed_intake_fields === true);
        var revision = issued && pending.revision !== undefined && pending.revision !== null ? String(pending.revision) : "";
        var previous = card.dataset.inquiryId || "";
        card.dataset.source = "shared_mediator";
        card.dataset.fromFixedIntake = "false";
        card.dataset.storesAnswer = "false";
        card.dataset.pending = issued ? "true" : "false";
        if (editor) editor.hidden = !issued;
        card.dataset.inquiryId = issued ? text(pending.inquiry_id) : "";
        card.dataset.revision = revision;
        if (!issued) {
            questionNode.textContent = "No server question is loaded. The fixed intake form is not the interview.";
            revisionNode.textContent = "";
            whyNode.textContent = "Why this matters is unavailable until the shared mediator asks a question.";
            gapsNode.innerHTML = "<li data-gap-kind=\"none\">No factual gap is linked.</li>";
            requirementsNode.innerHTML = "<li data-requirement-id=\"\">No legal requirement is linked.</li>";
            actionsNode.replaceChildren();
            if (note && previous !== "") {
                note.dataset.action = "";
                note.dataset.storedAsAnswer = "false";
                note.textContent = "Why and status read the interview. They do not save an answer.";
            }
            return;
        }
        var factual = explanation && explanation.factual_target && typeof explanation.factual_target === "object" ? explanation.factual_target : {};
        var law = explanation && explanation.sourced_legal_requirement && typeof explanation.sourced_legal_requirement === "object" ? explanation.sourced_legal_requirement : {};
        var why = text(explanation && explanation.why_asked) || text(pending.why_it_matters) || "Why this matters has not been recorded for this question.";
        questionNode.textContent = text(pending.question);
        revisionNode.textContent = "Revision " + revision;
        whyNode.textContent = why;
        var gaps = [];
        var preserved = record.interview.preserved_gaps;
        if (!Array.isArray(preserved) && record.adaptive && Array.isArray(record.adaptive.preserved_gaps)) preserved = record.adaptive.preserved_gaps;
        if (text(factual.target_id) || text(factual.label)) {
            gaps.push({
                kind: "factual",
                label: text(factual.label) || "unknown",
                targetId: text(factual.target_id) || "unknown"
            });
        }
        (Array.isArray(preserved) ? preserved : []).forEach(function (item) {
            if (!item || typeof item !== "object") return;
            gaps.push({
                kind: text(item.disposition) || "open",
                label: text(item.target_id) || "Open gap",
                targetId: text(item.target_id) || "unknown"
            });
        });
        if (!gaps.length) gaps.push({ kind: "unresolved", label: "The linked factual gap is unresolved.", targetId: "unknown" });
        gapsNode.innerHTML = gaps.map(function (item) {
            return '<li data-gap-kind="' + escapeHtml(item.kind) + '" data-target-id="' + escapeHtml(item.targetId) + '">'
                + escapeHtml(item.label) + "</li>";
        }).join("");
        var requirementId = text(law.requirement_id) || "unknown";
        var requirementLabel = text(law.label) || "unknown";
        requirementsNode.innerHTML = '<li data-requirement-id="' + escapeHtml(requirementId) + '" data-law-derived="'
            + (law.law_derived === true ? "true" : "false") + '">' + escapeHtml(requirementLabel) + "</li>";
        var labels = { answer: "Answer", unknown: "I don't know", defer: "Defer" };
        var buttons = allowedInquiryActions(record).map(function (action) {
            var id = action === "answer" ? "inquiry-card-answer" : (action === "unknown" ? "inquiry-card-unknown" : "inquiry-card-defer");
            return '<button type="button" id="' + id + '" data-inquiry-action="' + action + '">' + labels[action] + "</button>";
        });
        buttons.push('<button type="button" id="inquiry-card-why" data-inquiry-action="why">Why</button>');
        buttons.push('<button type="button" id="inquiry-card-status" data-inquiry-action="status">Interview status</button>');
        actionsNode.innerHTML = buttons.join("");
        if (note && previous !== card.dataset.inquiryId) {
            note.dataset.action = "";
            note.dataset.storedAsAnswer = "false";
            note.dataset.inquiryUnchanged = "";
            note.textContent = "Why and status read the interview. They do not save an answer.";
        }
    }

    function focusAction(action) {
        if (action === "answer") {
            var answer = $("adaptive-answer");
            if (answer) answer.focus();
            return;
        }
        if (action === "narrative") {
            var narrative = $("adaptive-narrative");
            if (narrative) narrative.focus();
            return;
        }
        if (action === "evidence") {
            var tab = document.querySelector('.tab-button[data-tab-target="evidence"]');
            if (tab) tab.click();
            var list = $("evidence-list");
            var button = list && list.querySelector("button");
            if (button) button.focus();
            else if (list) list.focus();
        }
    }

    function clear() {
        generation += 1;
        submissionEpoch += 1;
        submitting = false;
        renderedHead = null;
        renderedCaseId = "";
        if (controller) controller.abort();
        controller = null;
        lastPayload = null;
        ["factual-correction-graph-revision", "factual-correction-session-revision", "factual-correction-target",
            "factual-correction-actor", "factual-correction-replacement"].forEach(function (id) {
            var node = $(id);
            if (node) node.value = "";
        });
        var change = $("inquiry-graph-change");
        if (change) change.remove();
        retryCount = 0;
        lifecycle = "idle";
        root = $("mediator-conversation");
        if (!root) return;
        var log = $("mediator-conversation-log");
        var context = $("mediator-conversation-context");
        var actions = $("mediator-conversation-actions");
        if (log) log.replaceChildren();
        if (context) context.textContent = "";
        if (actions) actions.replaceChildren();
        paintControls();
        var status = $("mediator-conversation-status");
        if (status) status.textContent = "Conversation text was cleared because this case is no longer open.";
        renderInquiryCard(null);
        paintStopping(null);
    }

    function headOf(payload) {
        var head = payload && payload.encrypted_head;
        var session = sessionOf(payload || {});
        var revision = head && head.private_revision !== undefined ? Number(head.private_revision) : null;
        return {
            caseId: text((head && head.case_id) || session.case_id),
            revision: Number.isFinite(revision) ? revision : null
        };
    }

    function replyConflict(payload) {
        if (!payload || typeof payload !== "object") return "";
        if (payload.conflict) return text(payload.conflict);
        var interview = payload.interview;
        if (interview && interview.status === "refused") {
            var error = interview.error && typeof interview.error === "object" ? interview.error : {};
            return text(error.code || interview.status);
        }
        var correction = payload.factual_correction;
        if (correction && correction.status && correction.status !== "applied") {
            var correctionError = correction.error && typeof correction.error === "object" ? correction.error : {};
            return text(correctionError.code || correction.status);
        }
        return "";
    }

    function currentCaseId() {
        var binding = window.complaintCaseShell && window.complaintCaseShell.binding ? window.complaintCaseShell.binding() : null;
        return binding && binding.case_id ? text(binding.case_id) : "";
    }

    function acceptPayload(payload) {
        if (!payload || blocked()) return false;
        var head = headOf(payload);
        var openCase = currentCaseId();
        if (openCase && renderedCaseId && openCase !== renderedCaseId) {
            renderedCaseId = "";
            renderedHead = null;
        }
        if (openCase && head.caseId && head.caseId !== openCase) return false;
        if (renderedCaseId && head.caseId && head.caseId !== renderedCaseId) return false;
        if (renderedHead !== null && head.revision !== null && head.revision < renderedHead) return false;
        if (replyConflict(payload)) return false;
        return true;
    }

    function rememberHead(payload) {
        var head = headOf(payload);
        if (head.caseId) renderedCaseId = head.caseId;
        if (head.revision !== null) renderedHead = head.revision;
    }

    function graphChangeNode() {
        var node = $("inquiry-graph-change");
        if (node) return node;
        node = document.createElement("section");
        node.id = "inquiry-graph-change";
        node.dataset.applied = "false";
        node.dataset.changesLaw = "false";
        node.dataset.conflict = "";
        node.dataset.count = "0";
        node.innerHTML = '<p id="inquiry-graph-change-text"></p><button type="button" id="inquiry-graph-recover">Reload the current question</button>';
        var card = $("inquiry-card");
        if (card && card.parentNode) card.parentNode.insertBefore(node, card.nextSibling);
        else if ($("mediator-conversation")) $("mediator-conversation").appendChild(node);
        return node;
    }

    function showGraphChange(payload, conflict) {
        var node = graphChangeNode();
        if (!node) return;
        var rows = payload && Array.isArray(payload.affected_support_projection) ? payload.affected_support_projection : [];
        var latest = rows.length ? rows[rows.length - 1] : null;
        var applied = !conflict && payload && payload.support_projection_updated === true;
        node.dataset.applied = applied ? "true" : "false";
        node.dataset.changesLaw = "false";
        node.dataset.conflict = conflict || "";
        node.dataset.count = String(rows.length);
        node.dataset.effectId = latest ? text(latest.effect_id) : "";
        node.dataset.inquiryId = latest ? text(latest.inquiry_id) : "";
        var head = headOf(payload || {});
        node.dataset.caseId = head.caseId;
        node.dataset.privateRevision = head.revision === null ? "" : String(head.revision);
        var textNode = $("inquiry-graph-change-text");
        if (!textNode) return;
        if (conflict) {
            textNode.textContent = "This reply is stale. The current question and encrypted case were kept. Reload the current question.";
            return;
        }
        if (applied) {
            var affected = latest && Array.isArray(latest.affected) ? latest.affected.length : 0;
            textNode.textContent = "The factual graph was updated once. Support links affected: " + affected + ". Admitted legal requirements were not rewritten.";
            return;
        }
        textNode.textContent = "No new factual graph update was stored.";
    }

    function project(payload) {
        if (generation < 0) return;
        if (blocked()) {
            clear();
            lifecycle = "blocked";
            paintControls();
            return;
        }
        if (!acceptPayload(payload)) {
            if (replyConflict(payload) || (payload && headOf(payload).caseId && headOf(payload).caseId !== currentCaseId())) {
                showGraphChange(payload, replyConflict(payload) || "newer_case");
            }
            return;
        }
        rememberHead(payload);
        lastPayload = payload;
        projectCorrectionOffer(payload);
        if (lifecycle === "pending") return;
        render(payload);
    }

    async function refresh() {
        root = $("mediator-conversation");
        if (!root || lifecycle === "pending" || lifecycle === "retry-exhausted" || blocked()) return;
        var client = window.workspaceClient;
        var binding = window.complaintCaseShell && window.complaintCaseShell.binding ? window.complaintCaseShell.binding() : null;
        if (!client || typeof client._request !== "function" || !binding || !binding.case_id) {
            lifecycle = "error";
            paintControls();
            return;
        }
        var token = ++generation;
        var caseId = binding.case_id;
        lifecycle = "pending";
        paintControls();
        controller = new AbortController();
        var url = "/api/complaint-workspace/session?case_id=" + encodeURIComponent(caseId);
        try {
            var payload = await client._request(url, { method: "GET", signal: controller.signal });
            if (token !== generation) return;
            var current = window.complaintCaseShell.binding();
            if (!current || current.case_id !== caseId || blocked()) {
                clear();
                return;
            }
            if (!acceptPayload(payload)) {
                lifecycle = "settled";
                showGraphChange(payload, replyConflict(payload) || "newer_case");
                paintControls();
                return;
            }
            rememberHead(payload);
            lastPayload = payload;
            projectCorrectionOffer(payload);
            retryCount = 0;
            lifecycle = "settled";
            lateGate.suppressed = false;
            render(payload);
        } catch (error) {
            if (token !== generation) return;
            lifecycle = error && error.code === "cancelled" ? "cancelled" : "error";
            if (lastPayload) render(lastPayload);
            else paintControls();
            if (lifecycle === "cancelled" || lifecycle === "error") paintControls();
        } finally {
            if (token === generation) controller = null;
        }
    }

    function cancel() {
        if (lifecycle !== "pending") return;
        generation += 1;
        if (controller) controller.abort();
        controller = null;
        lifecycle = "cancelled";
        lateGate.displayAllowed = false;
        lateGate.suppressed = true;
        lateGate.code = "consent_cancelled";
        if (lateGate.resultId) lateGate.cancelledIds[lateGate.resultId] = true;
        if (lastPayload && !blocked()) render(lastPayload);
        paintControls();
    }

    async function considerLateResult(proposal) {
        var client = window.workspaceClient;
        var binding = window.complaintCaseShell && window.complaintCaseShell.binding ? window.complaintCaseShell.binding() : null;
        var source = proposal && typeof proposal === "object" ? proposal : {};
        var resultId = text(source.result_id);
        lateGate.displayAllowed = false;
        lateGate.purpose = text(source.purpose);
        lateGate.generation = source.consent_generation === undefined || source.consent_generation === null ? "" : String(source.consent_generation);
        lateGate.resultId = resultId;
        if (!client || typeof client._request !== "function" || !binding || !binding.case_id || source.late_result !== true) {
            lateGate.code = "local_private";
            if (lastPayload) render(lastPayload);
            else paintLate();
            return { displayAllowed: false, code: lateGate.code };
        }
        if (source.key_unlocked === true || source.key_unlock === true || source.unlocked === true || source.staff_role
                || source.development_provider_authorization === true || source.consent_generation === undefined
                || source.consent_generation === null || !text(source.purpose) || !resultId) {
            lateGate.code = "consent_not_implied";
            if (resultId) lateGate.cancelledIds[resultId] = false;
            if (lastPayload) render(lastPayload);
            else paintLate();
            return { displayAllowed: false, code: lateGate.code };
        }
        if (lateGate.suppressed || lateGate.cancelledIds[resultId]) {
            lateGate.code = "consent_cancelled";
            lateGate.cancelledIds[resultId] = true;
            try {
                var current = await client._request("/api/cases/" + encodeURIComponent(binding.case_id) + "/processing-consent", { method: "GET" });
                await client._request("/api/cases/" + encodeURIComponent(binding.case_id) + "/processing-consent/late-result/cancel", {
                    method: "POST",
                    body: JSON.stringify({
                        purpose: text(source.purpose),
                        result_id: resultId,
                        expected_generation: current.generation
                    })
                });
            } catch (error) {
                lateGate.code = "consent_cancelled";
            }
            if (lastPayload) render(lastPayload);
            else paintLate();
            return { displayAllowed: false, code: "consent_cancelled" };
        }
        try {
            var live = await client._request("/api/cases/" + encodeURIComponent(binding.case_id) + "/processing-consent", { method: "GET" });
            var decision = await client._request("/api/cases/" + encodeURIComponent(binding.case_id) + "/processing-consent/late-result", {
                method: "POST",
                body: JSON.stringify({
                    purpose: text(source.purpose),
                    consent_generation: source.consent_generation,
                    result_id: resultId,
                    expected_generation: live.generation
                })
            });
            var allowed = decision && decision.display_allowed === true && decision.admitted === true && decision.code === "current_consent";
            lateGate.displayAllowed = allowed;
            lateGate.code = decision && decision.code ? text(decision.code) : "local_private";
            if (!allowed) lateGate.displayAllowed = false;
        } catch (error) {
            lateGate.displayAllowed = false;
            lateGate.code = "consent_not_implied";
        }
        if (lastPayload) render(lastPayload);
        else paintLate();
        return { displayAllowed: lateGate.displayAllowed, code: lateGate.code };
    }

    function retry() {
        if (lifecycle !== "error" && lifecycle !== "cancelled") return;
        if (retryCount >= MAX_RETRIES) {
            lifecycle = "retry-exhausted";
            paintControls();
            return;
        }
        retryCount += 1;
        lifecycle = "idle";
        refresh();
    }

    function bind() {
        placeInquiryWorkbench();
        root = $("mediator-conversation");
        if (!root || root.dataset.bound === "true") return;
        root.dataset.bound = "true";
        root.addEventListener("click", function (event) {
            var button = event.target.closest("button");
            if (!button || !root.contains(button)) return;
            if (button.id === "mediator-conversation-refresh") refresh();
            else if (button.id === "mediator-conversation-cancel") cancel();
            else if (button.id === "mediator-conversation-retry") retry();
            else if (button.dataset.conversationAction) focusAction(button.dataset.conversationAction);
        });
        if (window.MutationObserver) {
            var shell = $("complaint-case-shell");
            if (shell) {
                var observer = new MutationObserver(function () {
                    if (blocked()) clear();
                    else if (lastPayload && lifecycle !== "pending") render(lastPayload);
                });
                observer.observe(shell, { attributes: true, attributeFilter: ["data-state"] });
            }
            var caseNode = $("complaint-case-shell-case");
            if (caseNode) {
                var caseObserver = new MutationObserver(function () {
                    if (blocked()) clear();
                    else if (lastPayload && lifecycle !== "pending") render(lastPayload);
                });
                caseObserver.observe(caseNode, { childList: true, characterData: true, subtree: true });
            }
        }
        paintControls();
        if (typeof window.complaintCasesSelect !== "function") {
            window.complaintCasesSelect = async function (caseId) {
                clear();
                var client = window.workspaceClient;
                if (!client || typeof client.selectCanonicalCase !== "function") return;
                try {
                    await client.selectCanonicalCase(caseId);
                    if (window.complaintCaseShell) await window.complaintCaseShell.refresh();
                } catch (error) {
                    // Failed selection leaves retired private content closed.
                    if (window.complaintCaseShell) await window.complaintCaseShell.refresh();
                }
            };
        }
        document.addEventListener("click", function (event) {
            var button = event.target && event.target.closest ? event.target.closest("button") : null;
            if (!button) return;
            if (button.id === "inquiry-graph-recover") {
                event.preventDefault();
                refresh();
                return;
            }
            if (button.id !== "adaptive-submit-answer" && button.id !== "factual-correction-submit") return;
            event.preventDefault();
            event.stopImmediatePropagation();
            if (button.id === "adaptive-submit-answer") submitAnswer();
            else submitCorrection();
        }, true);
        var card = $("inquiry-card");
        if (card && card.dataset.bound !== "true") {
            card.dataset.bound = "true";
            card.addEventListener("click", function (event) {
                var button = event.target.closest("button");
                if (!button || !card.contains(button)) return;
                var action = button.dataset.inquiryAction || "";
                if (action === "answer") focusAction("answer");
                else if (action === "unknown" && typeof window.answerAdaptiveInquiry === "function") window.answerAdaptiveInquiry("unknown");
                else if (action === "defer" && typeof window.answerAdaptiveInquiry === "function") window.answerAdaptiveInquiry("deferred");
                else if (action === "why" && typeof window.explainOrReviewInquiry === "function") window.explainOrReviewInquiry("why");
                else if (action === "status" && typeof window.readInquiryStatus === "function") window.readInquiryStatus();
            });
        }
    }

    function projectCorrectionOffer(payload) {
        var offer = payload && payload.adaptive_inquiry && payload.adaptive_inquiry.factual_correction;
        if (!offer || offer.schema !== "gui-factual-correction-v1") return;
        var fields = {
            "factual-correction-graph-revision": offer.expected_graph_revision,
            "factual-correction-session-revision": offer.expected_session_revision,
            "factual-correction-target": offer.target_stable_id,
            "factual-correction-actor": offer.actor_principal_id
        };
        Object.keys(fields).forEach(function (id) {
            var node = $(id);
            if (node) node.value = fields[id] === undefined || fields[id] === null ? "" : String(fields[id]);
        });
        // Only adopting a confirmed canonical payload refreshes these editable
        // revisions. A deliberately stale submitted revision stays visible to
        // the server's ordinary refusal; replacement text is left intact.
        var panel = $("factual-correction");
        if (panel) {
            panel.dataset.graphRevision = text(offer.expected_graph_revision);
            panel.dataset.sessionRevision = text(offer.expected_session_revision);
            panel.dataset.targetStableId = text(offer.target_stable_id);
            panel.dataset.actor = text(offer.actor_principal_id);
            panel.dataset.canonicalOwner = text(offer.canonical_owner_principal_id);
            panel.dataset.priorAnswer = text(offer.prior_answer);
        }
    }

    function offeredCorrection() {
        var adaptive = lastPayload && lastPayload.adaptive_inquiry;
        var offer = adaptive && adaptive.factual_correction;
        return offer && typeof offer === "object" ? offer : {};
    }

    function fieldValue(id) {
        var node = $(id);
        return node ? text(node.value) : "";
    }

    async function submitAnswer() {
        if (submitting || blocked()) return;
        var card = $("inquiry-card");
        var questionId = card ? text(card.dataset.inquiryId) : "";
        var revision = card && card.dataset.revision !== "" ? Number(card.dataset.revision) : NaN;
        var message = fieldValue("adaptive-answer");
        var client = window.workspaceClient;
        if (!client || typeof client.submitCanonicalGraphAnswer !== "function") return;
        if (!questionId || !Number.isSafeInteger(revision) || !message) return;
        var caseId = currentCaseId();
        var epoch = submissionEpoch;
        var userId = (client.caseContext && client.caseContext.tenant_id) || client.activePrincipalId || "";
        submitting = true;
        try {
            var result = await client.submitCanonicalGraphAnswer(userId, message, {
                question_id: questionId,
                expected_question_revision: revision
            });
            if (submissionEpoch !== epoch || currentCaseId() !== caseId) return;
            var payload = result && result.payload;
            var conflict = result && result.conflict ? result.conflict : replyConflict(payload);
            if (!result || result.accepted !== true || conflict) {
                showGraphChange(payload, conflict || "stale_question");
                return;
            }
            project(payload);
            showGraphChange(payload, "");
        } catch (error) {
            if (submissionEpoch === epoch && currentCaseId() === caseId) showGraphChange(null, "unavailable");
        } finally {
            if (submissionEpoch === epoch) submitting = false;
        }
    }

    async function submitCorrection() {
        if (submitting || blocked()) return;
        var offer = offeredCorrection();
        var graphRevision = fieldValue("factual-correction-graph-revision") || text(offer.expected_graph_revision);
        var sessionText = fieldValue("factual-correction-session-revision");
        var sessionRevision = sessionText === "" ? Number(offer.expected_session_revision) : Number(sessionText);
        var targetId = fieldValue("factual-correction-target") || text(offer.target_stable_id);
        var actor = fieldValue("factual-correction-actor") || text(offer.actor_principal_id);
        var replacement = fieldValue("factual-correction-replacement");
        var client = window.workspaceClient;
        if (!client || typeof client.submitCanonicalGraphCorrection !== "function" || !replacement) return;
        var caseId = currentCaseId();
        var epoch = submissionEpoch;
        var userId = (client.caseContext && client.caseContext.tenant_id) || client.activePrincipalId || "";
        submitting = true;
        try {
            var result = await client.submitCanonicalGraphCorrection(userId, replacement, {
                question_id: targetId,
                target_stable_id: targetId,
                actor_principal_id: actor,
                expected_graph_revision: graphRevision,
                expected_session_revision: sessionRevision
            });
            if (submissionEpoch !== epoch || currentCaseId() !== caseId) return;
            var payload = result && result.payload;
            var conflict = result && result.accepted === true ? "" : ((result && result.conflict) || replyConflict(payload) || "stale_target");
            if (conflict) {
                showGraphChange(payload, conflict);
                return;
            }
            project(payload);
            showGraphChange(payload, "");
        } catch (error) {
            if (submissionEpoch === epoch && currentCaseId() === caseId) showGraphChange(null, "unavailable");
        } finally {
            if (submissionEpoch === epoch) submitting = false;
        }
    }

    window.complaintConversation = {
        project: project,
        clear: clear,
        refresh: refresh,
        cancel: cancel,
        retry: retry,
        submitAnswer: submitAnswer,
        submitCorrection: submitCorrection,
        classifyStopping: classifyStopping,
        paintStopping: paintStopping,
        considerLateResult: considerLateResult
    };

    if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", bind);
    else bind();
})();
