class ComplaintMcpClient {
    constructor(options = {}) {
        this.baseUrl = options.baseUrl || '/api/complaint-workspace';
        this.mcpBaseUrl = options.mcpBaseUrl || `${this.baseUrl}/mcp`;
        this.origin = options.origin || (typeof window !== 'undefined' && window.location ? window.location.origin : 'http://localhost');
        this.fetchImpl = options.fetchImpl || (typeof fetch === 'function' ? fetch.bind(globalThis) : null);
        this._requestId = 1;
        this.didStorageKey = options.didStorageKey || 'complaintGenerator.did';
    }

    initialize() {
        return this.callJsonRpc('initialize', {
            clientInfo: {
                name: 'complaint-generator-browser-sdk',
                version: '0.1.0',
            },
        });
    }

    async _request(path, options = {}) {
        if (typeof this.fetchImpl !== 'function') {
            throw new Error('ComplaintMcpClient requires a fetch implementation.');
        }
        const response = await this.fetchImpl(path, Object.assign({
            headers: {
                'Content-Type': 'application/json',
            },
            credentials: 'same-origin',
        }, options));
        if (!response.ok) {
            const text = await response.text();
            throw new Error(text || (`Request failed with status ${response.status}`));
        }
        return response.json();
    }

    async _rpc(method, params) {
        const payload = await this._request(`${this.mcpBaseUrl}/rpc`, {
            method: 'POST',
            body: JSON.stringify({
                jsonrpc: '2.0',
                id: this._requestId++,
                method,
                params: params || {},
            }),
        });
        if (payload.error) {
            throw new Error(payload.error.message || 'JSON-RPC request failed');
        }
        return payload.result;
    }

    callJsonRpc(method, params) {
        return this._rpc(method, params);
    }

    ping() {
        return this.callJsonRpc('ping', {});
    }

    async listTools() {
        const result = await this._rpc('tools/list', {});
        return result.tools || [];
    }

    async callTool(toolName, argumentsPayload) {
        const result = await this._rpc('tools/call', {
            name: toolName,
            arguments: argumentsPayload || {},
        });
        if (result && result.structuredContent) {
            return result.structuredContent;
        }
        return result;
    }

    startSession(userId) {
        return this.callTool('complaint.start_session', {
            user_id: userId,
        });
    }

    createIdentity() {
        return this._request(`${this.baseUrl}/identity`, {
            method: 'POST',
            body: JSON.stringify({}),
        });
    }

    listIntakeQuestions() {
        return this.callTool('complaint.list_intake_questions', {});
    }

    listClaimElements() {
        return this.callTool('complaint.list_claim_elements', {});
    }

    getCachedDid() {
        if (typeof localStorage === 'undefined') {
            return null;
        }
        return localStorage.getItem(this.didStorageKey);
    }

    cacheDid(did) {
        if (typeof localStorage !== 'undefined') {
            localStorage.setItem(this.didStorageKey, did);
        }
        return did;
    }

    async getOrCreateDid() {
        const cachedDid = this.getCachedDid();
        if (cachedDid) {
            return cachedDid;
        }
        const identity = await this.createIdentity();
        if (!identity || !identity.did) {
            throw new Error('Identity endpoint did not return a DID.');
        }
        return this.cacheDid(identity.did);
    }

    async bootstrapWorkspace(userId) {
        const did = userId || await this.getOrCreateDid();
        const [initialization, tools, session] = await Promise.all([
            this.initialize(),
            this.listTools(),
            this.startSession(did),
        ]);
        return {
            did,
            initialization,
            tools,
            session,
        };
    }

    getSession(userId) {
        const url = new URL(`${this.baseUrl}/session`, this.origin);
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

    buildMediatorPrompt(userId) {
        return this.callTool('complaint.build_mediator_prompt', {
            user_id: userId,
        });
    }

    getComplaintReadiness(userId) {
        return this.callTool('complaint.get_complaint_readiness', {
            user_id: userId,
        });
    }

    getUiReadiness(userId) {
        return this.callTool('complaint.get_ui_readiness', {
            user_id: userId,
        });
    }

    getWorkflowCapabilities(userId) {
        return this.callTool('complaint.get_workflow_capabilities', {
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

    exportComplaintPacket(userId) {
        return this.callTool('complaint.export_complaint_packet', {
            user_id: userId,
        });
    }

    exportComplaintMarkdown(userId) {
        return this.callTool('complaint.export_complaint_markdown', {
            user_id: userId,
        });
    }

    exportComplaintPdf(userId) {
        return this.callTool('complaint.export_complaint_pdf', {
            user_id: userId,
        });
    }

    analyzeComplaintOutput(userId) {
        return this.callTool('complaint.analyze_complaint_output', {
            user_id: userId,
        });
    }

    downloadComplaintPacketUrl(userId, outputFormat) {
        const url = new URL(`${this.baseUrl}/export/download`, this.origin);
        if (userId) {
            url.searchParams.set('user_id', userId);
        }
        if (outputFormat) {
            url.searchParams.set('output_format', outputFormat);
        }
        return url.toString();
    }

    updateCaseSynopsis(userId, synopsis) {
        return this.callTool('complaint.update_case_synopsis', {
            user_id: userId,
            synopsis: synopsis || '',
        });
    }

    resetSession(userId) {
        return this.callTool('complaint.reset_session', {
            user_id: userId,
        });
    }

    reviewUiArtifacts(payload) {
        return this.callTool('complaint.review_ui', payload || {});
    }

    optimizeUiArtifacts(payload) {
        return this.callTool('complaint.optimize_ui', payload || {});
    }

    runUiUxWorkflow(payload) {
        return this.reviewUiArtifacts(payload);
    }

    runClosedLoopUiUxWorkflow(payload) {
        return this.optimizeUiArtifacts(payload);
    }

    runBrowserAudit(payload) {
        return this.callTool('complaint.run_browser_audit', payload || {});
    }
}

export { ComplaintMcpClient };
export default ComplaintMcpClient;
