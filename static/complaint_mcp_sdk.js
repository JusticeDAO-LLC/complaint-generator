(function (globalFactory) {
    if (typeof module === 'object' && module.exports) {
        module.exports = globalFactory();
    } else {
        window.ComplaintMcpSdk = globalFactory();
    }
})(function () {
    class ComplaintMcpClient {
        constructor(options) {
            const config = options || {};
            this.baseUrl = config.baseUrl || '/api/complaint-workspace';
            this.mcpBaseUrl = config.mcpBaseUrl || (this.baseUrl + '/mcp');
        }

        async _request(path, options) {
            const response = await fetch(path, Object.assign({
                headers: {
                    'Content-Type': 'application/json',
                },
                credentials: 'same-origin',
            }, options || {}));
            if (!response.ok) {
                const text = await response.text();
                throw new Error(text || ('Request failed with status ' + response.status));
            }
            return response.json();
        }

        listTools() {
            return this._request(this.mcpBaseUrl + '/tools');
        }

        callTool(toolName, argumentsPayload) {
            return this._request(this.mcpBaseUrl + '/call', {
                method: 'POST',
                body: JSON.stringify({
                    tool_name: toolName,
                    arguments: argumentsPayload || {},
                }),
            });
        }

        getSession(userId) {
            const url = new URL(this.baseUrl + '/session', window.location.origin);
            if (userId) {
                url.searchParams.set('user_id', userId);
            }
            return this._request(url.toString());
        }

        submitIntake(userId, answers) {
            return this.callTool('complaint.submit_intake', {
                user_id: userId,
                answers: answers || {},
            });
        }

        saveEvidence(userId, payload) {
            return this.callTool('complaint.save_evidence', Object.assign({
                user_id: userId,
            }, payload || {}));
        }

        reviewCase(userId) {
            return this.callTool('complaint.review_case', {
                user_id: userId,
            });
        }

        generateComplaint(userId, payload) {
            return this.callTool('complaint.generate_complaint', Object.assign({
                user_id: userId,
            }, payload || {}));
        }

        updateDraft(userId, payload) {
            return this.callTool('complaint.update_draft', Object.assign({
                user_id: userId,
            }, payload || {}));
        }

        resetSession(userId) {
            return this.callTool('complaint.reset_session', {
                user_id: userId,
            });
        }
    }

    return {
        ComplaintMcpClient,
    };
});
