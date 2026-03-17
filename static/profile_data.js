window.ProfileDataPage = (function() {
    const chatEntryUtils = window.ChatEntryUtils || {};

    function escapeHtml(text) {
        return $("<div>").text(text || "").html();
    }

    function showError(message) {
        const formField = "<span>" + escapeHtml(message) + "</span>";
        $("#Err").html(formField);
        $("#Err").show();
    }

    function loadProfile(hashedUsername, hashedPassword, isAsync, onSuccess) {
        $.ajax({
            type: "POST",
            contentType: "application/json",
            url: "/load_profile",
            data: JSON.stringify({
                request: {
                    hashed_username: hashedUsername,
                    hashed_password: hashedPassword,
                }
            }),
            dataType: "json",
            async: isAsync,
            success: function(data) {
                if (typeof onSuccess === "function") {
                    onSuccess(data);
                }
            }
        });
    }

    function normalizeProfileData(data) {
        if (typeof data === "string") {
            return JSON.parse(data);
        }
        return data || {};
    }

    function normalizeChatEntry(entry) {
        if (typeof chatEntryUtils.normalizeChatEntry === "function") {
            return chatEntryUtils.normalizeChatEntry(entry);
        }
        if (typeof entry === "string") {
            return {
                message: entry,
                question: entry,
            };
        }
        const normalized = Object.assign({}, entry || {});
        if (!normalized.message) {
            normalized.message = normalized.question || ((normalized.inquiry || {}).question) || "";
        }
        if (!normalized.question) {
            normalized.question = ((normalized.inquiry || {}).question) || normalized.message || "";
        }
        return normalized;
    }

    function renderChatHistory(chatHistory, targetSelector) {
        const parent = $(targetSelector);
        parent.empty();
        const entries = chatHistory || {};

        Object.keys(entries).sort().forEach(function(timestamp) {
            const entry = normalizeChatEntry(entries[timestamp]);
            const sender = escapeHtml(entry.sender || "Bot:");
            const message = escapeHtml(entry.message || "");
            const explanation = escapeHtml(((entry.explanation || {}).summary) || "");
            let html = '<div class="chat-history-entry">';
            html += '<div><strong>' + escapeHtml(timestamp) + '</strong> — <strong>' + sender + '</strong>: ' + message + '</div>';
            if (explanation) {
                html += '<div class="chat-history-explanation">Why this question: ' + explanation + '</div>';
            }
            html += '</div>';
            parent.append(html);
        });
    }

    function renderProfileData(profileData, jsonSelector, historySelector) {
        const normalized = normalizeProfileData(profileData);
        $(jsonSelector).text(JSON.stringify(normalized, null, 2));
        renderChatHistory(normalized.chat_history || {}, historySelector);
    }

    function initialize(options) {
        const settings = Object.assign({
            jsonSelector: "#profile_data",
            historySelector: "#chat_history",
            refreshMs: null,
        }, options || {});

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

        const parsedCookies = JSON.parse(cookies || "{}");
        const hashedUsername = parsedCookies.hashed_username;
        const hashedPassword = parsedCookies.hashed_password;

        const refresh = function(isAsync) {
            loadProfile(hashedUsername, hashedPassword, isAsync, function(data) {
                if (data && data.Err) {
                    showError(data.Err);
                    return;
                }
                renderProfileData(data.data, settings.jsonSelector, settings.historySelector);
            });
        };

        refresh(false);
        if (settings.refreshMs) {
            setInterval(function() { refresh(true); }, settings.refreshMs);
        }
    }

    return {
        initialize,
        renderProfileData,
        renderChatHistory,
        normalizeChatEntry,
        normalizeProfileData,
    };
})();
