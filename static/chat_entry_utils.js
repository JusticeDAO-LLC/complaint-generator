window.ChatEntryUtils = (function() {
    function normalizeChatEntry(entry) {
        if (typeof entry === 'string') {
            return {
                message: entry,
                question: entry,
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

    function normalizeSender(sender, hashedUsername) {
        if (sender == hashedUsername) {
            return 'You';
        }
        return sender || 'Bot:';
    }

    return {
        normalizeChatEntry,
        normalizeSender,
    };
})();
