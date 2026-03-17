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

        const socket = new WebSocket("ws://" + hostname + "/api/chat");
        socket.onmessage = function(event) {
            const data = JSON.parse(event.data);
            renderMessage(parent, data, hashedUsername);
        };

        $("#chat-form").on("submit", function(e) {
            e.preventDefault();
            const message = $("input").val();
            if (message) {
                const data = {
                    "sender": hashedUsername,
                    "message": message
                };
                socket.send(JSON.stringify(data));
                $("input").val("");
            }
        });
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
