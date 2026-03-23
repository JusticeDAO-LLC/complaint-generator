window.ChatPage = (function() {
    const hostname = "localhost:19000";
    const chatEntryUtils = window.ChatEntryUtils || {};

    function loadProfile(username, password) {
        $.ajaxSetup({ async: false });
        let returnData = null;
        $.ajax({
            type: "POST",
            contentType: 'application/json',
            url: "/load_profile",
            data: '{"request": {"hashed_username" : "' + username + '", "hashed_password": "' + password + '"}}',
            dataType: 'json',
            async: false,
            success: function(data) {
                returnData = data;
            }
        });
        $.ajaxSetup({ async: true });

        if (returnData && "Err" in returnData) {
            showError(returnData["Err"]);
            return returnData;
        }
        return returnData;
    }

    function showError(message) {
        let formField = $("#Err").html();
        formField = "<span>" + message + "</span>";
        $("#Err").html(formField);
        $("#Err").show();
    }

    function escapeHtml(text) {
        return $("<div>").text(text || "").html();
    }

    function normalizeSender(sender, hashedUsername) {
        if (typeof chatEntryUtils.normalizeSender === 'function') {
            return chatEntryUtils.normalizeSender(sender, hashedUsername);
        }
        if (sender == hashedUsername) {
            return "You";
        }
        return sender || "Bot:";
    }

    function normalizeChatEntry(entry) {
        if (typeof chatEntryUtils.normalizeChatEntry === 'function') {
            return chatEntryUtils.normalizeChatEntry(entry);
        }
        if (typeof entry === 'string') {
            return {
                message: entry,
                question: entry
            };
        }

        const normalized = Object.assign({}, entry || {});
        if (!normalized.message) {
            normalized.message = normalized.question || ((normalized.inquiry || {}).question) || '';
        }
        if (!normalized.question) {
            normalized.question = ((normalized.inquiry || {}).question) || normalized.message || '';
        }

        return normalized;
    }

    function renderMessage(parent, data, hashedUsername) {
        if (!data) {
            return;
        }

        data = normalizeChatEntry(data);

        const sender = normalizeSender(data['sender'], hashedUsername);
        const message = escapeHtml(data['message'] || '');
        const explanation = ((data['explanation'] || {})['summary']) || '';
        let content = '<div class="chat-message">' +
            '<p><strong>' + escapeHtml(sender) + ' </strong><span> ' + message + '</span></p>';

        if (explanation) {
            content += '<div class="chat-explanation">Why this question: ' + escapeHtml(explanation) + '</div>';
        }

        content += '</div>';
        parent.append(content);
    }

    function readWorkspaceHandoff() {
        if (typeof window === 'undefined' || !window.location) {
            return null;
        }
        const params = new URLSearchParams(window.location.search || '');
        const source = String(params.get('source') || '').trim();
        const userId = String(params.get('user_id') || '').trim();
        const caseSynopsis = String(params.get('case_synopsis') || '').trim();
        const prefillMessage = String(params.get('prefill_message') || '').trim();
        const returnTo = String(params.get('return_to') || '').trim();
        if (!(source || userId || caseSynopsis || prefillMessage || returnTo)) {
            return null;
        }
        return {
            source,
            userId,
            caseSynopsis,
            prefillMessage,
            returnTo,
        };
    }

    function getActiveComplaintUserId(handoff) {
        if (handoff && handoff.userId) {
            return String(handoff.userId).trim();
        }
        try {
            const cachedDid = window.localStorage.getItem('complaintGenerator.did');
            return String(cachedDid || '').trim();
        } catch (error) {
            return '';
        }
    }

    function setHrefForIds(linkIds, href) {
        linkIds.forEach((id) => {
            const node = document.getElementById(id);
            if (node) {
                node.href = href;
            }
        });
    }

    function updateChatNextStepLinks(handoff) {
        const activeUserId = getActiveComplaintUserId(handoff);
        const caseSynopsis = String((handoff && handoff.caseSynopsis) || '').trim();
        const hasActiveContext = Boolean(activeUserId || caseSynopsis);
        const profileLink = document.getElementById('chat-open-profile');
        const resultsLink = document.getElementById('chat-open-results');
        const builderLink = document.getElementById('chat-open-builder');
        if (!profileLink || !resultsLink || !builderLink) {
            return;
        }

        const workspaceParams = new URLSearchParams();
        if (activeUserId) {
            workspaceParams.set('user_id', activeUserId);
        }
        workspaceParams.set('target_tab', 'review');
        workspaceParams.set('status_message', 'Opened Workspace from the chat narrative surface.');
        const workspaceHref = `/workspace?${workspaceParams.toString()}`;
        setHrefForIds(['chat-meta-workspace', 'chat-hero-workspace', 'chat-open-workspace'], workspaceHref);

        const profileParams = new URLSearchParams();
        if (hasActiveContext) {
            if (activeUserId) {
                profileParams.set('user_id', activeUserId);
            }
            if (caseSynopsis) {
                profileParams.set('case_synopsis', caseSynopsis);
            }
            profileParams.set('source', 'chat');
        }
        const profileHref = profileParams.toString() ? `/profile?${profileParams.toString()}` : '/profile';
        setHrefForIds(['chat-nav-profile', 'chat-open-profile'], profileHref);

        const resultsParams = new URLSearchParams(profileParams.toString());
        const resultsHref = resultsParams.toString() ? `/results?${resultsParams.toString()}` : '/results';
        setHrefForIds(['chat-nav-results', 'chat-open-results'], resultsHref);

        const chatHref = hasActiveContext
            ? buildCurrentChatUrl(activeUserId, caseSynopsis, handoff)
            : '/chat';
        setHrefForIds(['chat-nav-chat'], chatHref);

        const reviewParams = new URLSearchParams();
        if (activeUserId) {
            reviewParams.set('user_id', activeUserId);
            reviewParams.set('workspace_user_id', activeUserId);
        }
        const reviewHref = reviewParams.toString() ? `/claim-support-review?${reviewParams.toString()}` : '/claim-support-review';
        setHrefForIds(['chat-meta-review', 'chat-hero-review', 'chat-nav-review', 'chat-open-review'], reviewHref);

        const builderParams = new URLSearchParams();
        if (activeUserId) {
            builderParams.set('user_id', activeUserId);
        }
        if (caseSynopsis) {
            builderParams.set('case_synopsis', caseSynopsis);
        }
        const builderHref = builderParams.toString() ? `/document?${builderParams.toString()}` : '/document';
        setHrefForIds(['chat-meta-builder', 'chat-nav-builder', 'chat-open-builder'], builderHref);

        const traceParams = new URLSearchParams();
        if (activeUserId) {
            traceParams.set('user_id', activeUserId);
        }
        if (hasActiveContext) {
            traceParams.set('source', 'chat');
        }
        const traceHref = traceParams.toString() ? `/document/optimization-trace?${traceParams.toString()}` : '/document/optimization-trace';
        setHrefForIds(['chat-nav-trace'], traceHref);
    }

    function buildCurrentChatUrl(activeUserId, caseSynopsis, handoff) {
        const chatParams = new URLSearchParams();
        if (activeUserId) {
            chatParams.set('user_id', activeUserId);
        }
        if (caseSynopsis) {
            chatParams.set('case_synopsis', caseSynopsis);
        }
        if (handoff && handoff.source) {
            chatParams.set('source', handoff.source);
        }
        if (handoff && handoff.prefillMessage) {
            chatParams.set('prefill_message', handoff.prefillMessage);
        }
        if (handoff && handoff.returnTo) {
            chatParams.set('return_to', handoff.returnTo);
        }
        return chatParams.toString() ? `/chat?${chatParams.toString()}` : '/chat';
    }

    function applyWorkspaceHandoff() {
        const handoff = readWorkspaceHandoff();
        updateChatNextStepLinks(handoff);
        if (!handoff) {
            return;
        }

        const contextCard = document.getElementById('chat-context-card');
        const contextSummary = document.getElementById('chat-context-summary');
        const contextPrefill = document.getElementById('chat-context-prefill');
        const returnLink = document.getElementById('chat-context-return-link');
        const input = document.querySelector('#chat-form input');
        if (!contextCard || !contextSummary || !contextPrefill || !returnLink || !input) {
            return;
        }

        const summaryParts = [];
        if (handoff.userId) {
            summaryParts.push(`Shared complaint session: ${handoff.userId}.`);
        }
        if (handoff.caseSynopsis) {
            summaryParts.push(handoff.caseSynopsis);
        }
        contextSummary.textContent = summaryParts.join(' ') || 'Chat was opened from the workspace with the shared complaint context.';
        contextPrefill.textContent = handoff.prefillMessage
            ? `Prepared mediator prompt: ${handoff.prefillMessage}`
            : 'Use this chat to turn the current case framing into cleaner testimony and follow-up questions.';
        returnLink.href = handoff.returnTo || '/workspace';
        if (handoff.prefillMessage && !input.value.trim()) {
            input.value = handoff.prefillMessage;
        }
        contextCard.hidden = false;
    }

    function initialize() {
        let cookies = "";
        $("body").css("background-color", "transparent");
        $.ajax({
            url: "/cookies",
            type: "get",
            async: false,
            data: {},
            success: function(data) {
                cookies = data;
            }
        });

        const hashedUsername = JSON.parse(cookies)["hashed_username"];
        const hashedPassword = JSON.parse(cookies)["hashed_password"];
        const profile = loadProfile(hashedUsername, hashedPassword);
        let testdata = profile["data"];
        const parent = $("#messages");

        if (typeof testdata === 'string') {
            testdata = JSON.parse(testdata);
        }

        const chatHistory = testdata["chat_history"] || {};

        for (const timestamp in chatHistory) {
            renderMessage(parent, chatHistory[timestamp], hashedUsername);
        }

        let socket = null;
        let socketReady = false;

        async function sendViaFallback(message) {
            const response = await fetch("/api/chat/fallback", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                },
                credentials: "same-origin",
                body: JSON.stringify({
                    sender: hashedUsername,
                    message: message,
                }),
            });
            if (!response.ok) {
                throw new Error("Fallback chat request failed.");
            }
            const payload = await response.json();
            const messages = Array.isArray(payload && payload.messages) ? payload.messages : [];
            if (!messages.length) {
                renderMessage(parent, {"sender": hashedUsername, "message": message}, hashedUsername);
                return;
            }
            messages.forEach((entry) => {
                renderMessage(parent, entry, hashedUsername);
            });
        }

        try {
            socket = new WebSocket("ws://" + hostname + "/api/chat");
            socket.onopen = function() {
                socketReady = true;
            };
            socket.onerror = function() {
                socketReady = false;
            };
            socket.onclose = function() {
                socketReady = false;
            };
            socket.onmessage = function(event) {
                const data = JSON.parse(event.data);
                renderMessage(parent, data, hashedUsername);
            };
        } catch (error) {
            socketReady = false;
        }

        $("#chat-form").on("submit", async function(e) {
            e.preventDefault();
            const message = $("input").val().trim();
            if (message) {
                try {
                    if (socket && socketReady && socket.readyState === WebSocket.OPEN) {
                        const data = {
                            "sender": hashedUsername,
                            "message": message
                        };
                        socket.send(JSON.stringify(data));
                    } else {
                        await sendViaFallback(message);
                    }
                    $("input").val("");
                } catch (error) {
                    showError(error && error.message ? error.message : "Unable to submit the chat message.");
                }
            }
        });

        applyWorkspaceHandoff();
    }

    return {
        initialize,
        renderMessage,
        normalizeChatEntry,
        normalizeSender,
        escapeHtml,
        showError,
        loadProfile,
    };
})();

$(document).ready(function() {
    window.ChatPage.initialize();
});
