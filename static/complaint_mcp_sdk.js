(function (globalScope) {
const SYNC_EVENT_NAME = 'complaint-mcp-sync';
const DEFAULT_SYNC_EVENT_STORAGE_KEY = 'complaintGenerator.sdkSyncEvent';

const SYNC_PUBLIC_FIELDS = [
    'event_type',
    'tool_name',
    'status',
    'user_id',
    'manifest_path',
    'source',
    'emitted_at',
    'revision',
    'session_revision',
    'expected_question_revision',
    'interview_action',
    'pending_inquiry_id',
    'question_id',
    'conflict',
    'graph_version',
    'action',
];
const PRIVATE_STORAGE_KEY = /(synopsis|handoff|narrative|evidence|summary|token|secret|password|passphrase|api[_-]?key|private[_-]?key|raw[_-]?key|uiReadiness|sdkSyncEvent|sdkLastToolCall|sdkToolLedger|gmail-user|authorization|credential|bearer)/i;
const PUBLIC_ERROR_CODES = /^(authorization_denied|authentication_failed|session_required|workspace_operation_failed|stale_question|stale_target|revision_conflict|mcp_tool_error|JSON-RPC request failed|pin refused|http_\d{3})$/;

const PUBLIC_TOOL_NAMES = new Set(["complaint.analyze_complaint_output", "complaint.build_mediator_prompt", "complaint.build_mike_handoff", "complaint.execute_packaged_docket_proof_revalidation_queue", "complaint.export_complaint_docx", "complaint.export_complaint_markdown", "complaint.export_complaint_packet", "complaint.export_complaint_pdf", "complaint.generate_complaint", "complaint.get_client_release_gate", "complaint.get_complaint_readiness", "complaint.get_docket_dataset_graph", "complaint.get_docket_dataset_metadata", "complaint.get_draft_proof_report", "complaint.get_filing_provenance", "complaint.get_formal_diagnostics", "complaint.get_mike_integration_status", "complaint.get_packaged_docket_operator_dashboard", "complaint.get_proof_history", "complaint.get_provider_diagnostics", "complaint.get_tooling_contract", "complaint.get_ui_readiness", "complaint.get_workflow_capabilities", "complaint.get_workspace_data_schema", "complaint.import_gmail_evidence", "complaint.import_local_evidence", "complaint.improve_draft", "complaint.list_claim_elements", "complaint.list_intake_questions", "complaint.load_packaged_docket_operator_dashboard_report", "complaint.migrate_legacy_workspace_data", "complaint.optimize_ui", "complaint.persist_packaged_docket_proof_revalidation_queue", "complaint.pin_draft_proof_report", "complaint.render_draft_proof_report", "complaint.reset_session", "complaint.review_case", "complaint.review_generated_exports", "complaint.review_ui", "complaint.run_browser_audit", "complaint.run_gmail_duckdb_pipeline", "complaint.run_intake_chat_turn", "complaint.save_evidence", "complaint.score_draft_quality", "complaint.search_docket_dataset", "complaint.search_email_duckdb_corpus", "complaint.search_workspace_dataset", "complaint.start_session", "complaint.submit_intake", "complaint.sync_mike_final_draft", "complaint.update_case_synopsis", "complaint.update_claim_type", "complaint.update_draft", "complaint.view_docket_dataset", "complaint.view_workspace_dataset"]);
const PUBLIC_EVENT_TYPES = new Set(['workspace.updated', 'workspace.reset', 'docket.updated', 'docket.persisted']);
const PUBLIC_ACTIONS = new Set(['start', 'answer', 'status', 'resume', 'defer', 'revise', 'continue', 'correct']);
function publicRevision(value) { return Number.isSafeInteger(value) && value >= 0 ? value : null; }
function publicAction(value) { return PUBLIC_ACTIONS.has(value) ? value : ''; }
function publicTimestamp(value) {
    return typeof value === 'string' && /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,3})?Z$/.test(value) ? value : '';
}
function publicToolName(value) { return PUBLIC_TOOL_NAMES.has(value) ? value : 'mcp_tool'; }
function stateChangedError() { const e = new Error('workspace_state_changed'); e.isError = true; return e; }

function publicErrorMessage(value) {
    const text = typeof value === 'string' ? value : '';
    return PUBLIC_ERROR_CODES.test(text) || text === 'workspace_state_changed' || text === 'csrf_required' ? text : 'mcp_tool_error';
}

function authorizationDeniedText(value) {
    return /authorization_denied|authentication_failed|session_required|bearer token required/i.test(String(value || ''));
}

function publicToolErrorCode(result) {
    if (result && typeof result.error === 'string' && PUBLIC_ERROR_CODES.test(result.error)) return result.error;
    const content = result && Array.isArray(result.content) ? result.content[0] : null;
    const text = content && content.text ? String(content.text) : '';
    if (text === 'authorization_denied' || text === 'workspace_operation_failed' || text === 'stale_question') {
        return text;
    }
    if (result && typeof result.conflict === 'string' && result.conflict) {
        return publicErrorMessage(result.conflict);
    }
    const structured = result && result.structuredContent;
    if (structured && typeof structured === 'object') {
        if (structured.conflict) {
            return publicErrorMessage(structured.conflict);
        }
        if (structured.error === 'authorization_denied' || structured.error === 'workspace_operation_failed') {
            return String(structured.error);
        }
    }
    if (authorizationDeniedText(text)) {
        return 'authorization_denied';
    }
    return 'mcp_tool_error';
}

function containsPrivateText(value) {
    return /narrative|evidence|summary|synopsis|token|secret|password|passphrase|api[_-]?key|private[_-]?key|raw[_-]?key|bearer\s+/i.test(String(value || ''));
}

function projectSyncDetail(detail) {
    const source = detail && typeof detail === 'object' ? detail : {};
    const projected = { emitted_at: new Date().toISOString() };
    if (PUBLIC_EVENT_TYPES.has(source.event_type)) projected.event_type = source.event_type;
    if (PUBLIC_TOOL_NAMES.has(source.tool_name)) projected.tool_name = source.tool_name;
    if (['success', 'error', 'started', 'denied', 'conflict'].includes(source.status)) projected.status = source.status;
    for (const field of ['revision', 'session_revision', 'expected_question_revision', 'graph_version']) {
        const value = publicRevision(source[field]);
        if (value !== null) projected[field] = value;
    }
    for (const field of ['interview_action', 'action']) {
        if (publicAction(source[field])) projected[field] = source[field];
    }
    if (typeof source.user_id === 'string' && /^(?:[a-f0-9]{32}|did:key:(?:[A-Za-z0-9]+|fallback-[a-f0-9]{32}))$/.test(source.user_id)) projected.user_id = source.user_id;
    for (const field of ['pending_inquiry_id', 'question_id']) {
        if (typeof source[field] === 'string' && (/^inq-[a-z0-9-]{1,128}$/.test(source[field]) || source[field] === 'original_complaint')) projected[field] = source[field];
    }
    if (['stale_question', 'revision_conflict', 'inquiry_mismatch'].includes(source.conflict)) projected.conflict = source.conflict;
    return projected;
}

function publicDiagnosticSummary(summary) {
    if (!summary || typeof summary !== 'object') return undefined;
    return { warning_count: Array.isArray(summary.warnings) ? summary.warnings.length : 0,
        warnings: [], primary_warning: null, summary_text: '' };
}

function publicToolActivity(detail) {
    const source = detail && typeof detail === 'object' ? detail : {};
    return { tool_name: publicToolName(source.tool_name),
        status: ['success', 'error', 'started'].includes(source.status) ? source.status : 'error',
        started_at: publicTimestamp(source.started_at), finished_at: publicTimestamp(source.finished_at),
        error_message: source.error_message ? publicErrorMessage(source.error_message) : '',
        authorization_denied: source.authorization_denied === true, is_error: source.is_error === true,
        expected_question_revision: publicRevision(source.expected_question_revision),
        interview_action: publicAction(source.interview_action), revision: publicRevision(source.revision),
        diagnostic_summary: publicDiagnosticSummary(source.diagnostic_summary) };
}

function storageBuckets() {
    const buckets = [];
    if (typeof localStorage !== 'undefined') {
        buckets.push(localStorage);
    }
    if (typeof sessionStorage !== 'undefined') {
        buckets.push(sessionStorage);
    }
    return buckets;
}

function storageKeys(bucket) {
    if (!bucket || typeof bucket.key !== 'function' || typeof bucket.length !== 'number') {
        return [];
    }
    const keys = [];
    for (let index = 0; index < bucket.length; index += 1) {
        const key = bucket.key(index);
        if (key) {
            keys.push(key);
        }
    }
    return keys;
}

function clearPrivateBrowserStorage(extraKeys) {
    const explicit = new Set(extraKeys || []);
    storageBuckets().forEach((bucket) => {
        storageKeys(bucket).forEach((key) => {
            if (explicit.has(key) || PRIVATE_STORAGE_KEY.test(key)) {
                try {
                    bucket.removeItem(key);
                } catch (error) {
                    // Keep clearing the remaining private keys.
                }
            }
        });
    });
    return { cleared: true };
}

function dispatchSharedSyncEvent(detail, storageKey) {
    const normalizedDetail = projectSyncDetail(detail);
    if (typeof localStorage !== 'undefined') {
        try {
            localStorage.setItem(storageKey || DEFAULT_SYNC_EVENT_STORAGE_KEY, JSON.stringify(normalizedDetail));
        } catch (error) {
            // Ignore localStorage write failures and still dispatch the in-page event.
        }
    }
    if (typeof window !== 'undefined' && typeof window.dispatchEvent === 'function' && typeof CustomEvent === 'function') {
        window.dispatchEvent(new CustomEvent(SYNC_EVENT_NAME, { detail: normalizedDetail }));
    }
    return normalizedDetail;
}

const MAX_BOUNDED_INFERENCE_RETRIES = 2;
const INTERFACE_REQUEST_BUDGET = Object.freeze({maxInFlight: 4, maxQueued: 8, deadlineMs: 8000});
function interfaceLifecycleError(lifecycle) {
    const error = new Error(lifecycle);
    error.code = lifecycle;
    error.lifecycle = lifecycle;
    error.isError = true;
    error.terminal = lifecycle !== 'pending';
    error.published = false;
    return error;
}
const BOUNDED_INFERENCE_RETRYABLE = new Set(['unavailable', 'rate_limited', 'timeout']);
const BOUNDED_INFERENCE_STAGE = new Set(['recorded', 'denied', 'not_reached', 'malformed', 'cancelled', 'timeout', 'unavailable', 'dispatching', 'held', 'admitted', 'refused', 'partial', 'rate_limited', 'unobserved', 'checking_consent']);

function boundedInferenceRevision(payload) {
    if (!payload || typeof payload !== 'object') return null;
    if (Number.isSafeInteger(payload.bound_session_revision)) return payload.bound_session_revision;
    if (Number.isSafeInteger(payload.session_revision)) return payload.session_revision;
    return null;
}

function boundedInferenceKey(body, revision) {
    const purpose = body && typeof body.purpose === 'string' ? body.purpose : '';
    let inputs = '';
    try { inputs = JSON.stringify(body && body.inputs && typeof body.inputs === 'object' ? body.inputs : {}); }
    catch (error) { inputs = ''; }
    return purpose + '\n' + inputs + '\n' + (revision == null ? '' : String(revision));
}

function boundedInferenceStages(payload, seeded) {
    const stages = Array.isArray(seeded) ? seeded.filter((item) => item && BOUNDED_INFERENCE_STAGE.has(item.status)).map((item) => ({kind: String(item.kind || 'request'), status: item.status})) : [];
    const receipts = payload && Array.isArray(payload.receipts) ? payload.receipts : [];
    receipts.forEach((item) => {
        if (!item || typeof item !== 'object' || !BOUNDED_INFERENCE_STAGE.has(item.status)) return;
        stages.push({kind: String(item.kind || 'outcome'), status: item.status});
    });
    return stages.slice(0, 8);
}

function projectBoundedInferenceReceipt(payload, context) {
    const source = payload && typeof payload === 'object' ? payload : {};
    const extra = context && typeof context === 'object' ? context : {};
    const error = extra.error;
    const codeFromError = error ? String(error.code || error.message || 'unobserved') : '';
    const status = typeof source.status === 'string' ? source.status : '';
    const code = error ? codeFromError : (typeof source.code === 'string' ? source.code : '');
    const partial = source.partial === true || status === 'partial' || code === 'partial_response';
    let lifecycle = 'unobserved';
    if (extra.lifecycle) lifecycle = String(extra.lifecycle);
    else if (code === 'cancelled' || status === 'cancelled' || (error && error.name === 'AbortError')) lifecycle = 'cancelled';
    else if (code === 'retry_exhausted') lifecycle = 'retry_exhausted';
    else if (code === 'retry_not_applicable') lifecycle = extra.previousLifecycle || 'unobserved';
    else if (status === 'timeout' || code === 'timeout' || code === 'deadline_expired' || (error && (error.status === 408 || error.status === 504))) lifecycle = 'timeout';
    else if (status === 'rate_limited' || code === 'rate_limited' || status === 'quota' || code === 'quota' || (error && error.status === 429)) lifecycle = 'rate_limited';
    else if (status === 'unavailable' || code === 'model_transport_unavailable' || code === 'provider_unavailable' || code === 'inference_unavailable') lifecycle = 'unavailable';
    else if (partial) lifecycle = 'partial';
    else if (status === 'held' || code === 'awaiting_late_admission') lifecycle = 'held';
    else if (source.accepted === true && status === 'admitted') lifecycle = 'admitted';
    else if (status === 'refused' || code) lifecycle = 'refused';
    let revision = boundedInferenceRevision(source);
    if (revision == null && Number.isSafeInteger(extra.preserveRevision)) revision = extra.preserveRevision;
    if (Object.prototype.hasOwnProperty.call(extra, 'revision')) revision = Number.isSafeInteger(extra.revision) ? extra.revision : null;
    let remote = extra.remoteRevoked === true ? 'revoked' : 'unchanged';
    if (code === 'consent_revoked' || source.remote_processing_revoked === true || source.revoked === true) remote = 'revoked';
    if (partial && (source.remote_processing_enabled === true || source.reenable_remote_processing === true)) remote = remote === 'revoked' ? 'revoked' : 'not_reenabled';
    const terminal = extra.terminal !== false && lifecycle !== 'dispatching' && lifecycle !== 'checking_consent';
    const retryable = BOUNDED_INFERENCE_RETRYABLE.has(lifecycle) && terminal;
    const texts = {
        idle: 'No inference request has started.',
        checking_consent: 'Persisted case-purpose consent is being read. No model call has been observed.',
        dispatching: 'The inference request was sent. Completion has not been observed.',
        held: 'The provider response is held for late admission. Legal requirements are not marked supported.',
        admitted: 'Late admission accepted the held result. Model text does not mark legal requirements supported.',
        cancelled: 'The inference request was cancelled.',
        unavailable: 'Inference is unavailable.',
        rate_limited: 'The provider rate limit was observed.',
        timeout: 'The inference request timed out.',
        refused: 'The inference request was refused (' + (code || 'refused') + ').',
        partial: 'A partial response was observed. It does not support legal requirements or restore remote processing.',
        unobserved: 'No inference outcome was observed.',
        retry_exhausted: 'The retry limit was reached. The request was not sent again.',
    };
    return {
        schema: 'bounded-inference-progress-v1',
        lifecycle: lifecycle,
        code: code || lifecycle,
        revision: revision,
        percent: null,
        fabricated_progress: false,
        requirements_supported: false,
        model_dispatched: source.model_dispatched === true,
        remote_processing: remote,
        retry_count: Number.isSafeInteger(extra.retryCount) ? extra.retryCount : 0,
        attempt_count: Number.isSafeInteger(extra.attemptCount) ? extra.attemptCount : 0,
        retry_limit: MAX_BOUNDED_INFERENCE_RETRIES,
        terminal: terminal,
        retryable: retryable,
        stages: boundedInferenceStages(source, extra.stages),
        lifecycle_text: texts[lifecycle] || texts.unobserved,
        status_text: (texts[lifecycle] || texts.unobserved) + (revision == null ? ' Current revision: unobserved.' : ' Current revision: ' + revision + '.'),
        streaming: false,
        limitations: ['progress_percent_is_not_estimated', 'partial_output_is_not_legal_support', 'revoked_remote_processing_stays_revoked', 'ws_sse_streaming_not_used'],
    };
}

class ComplaintMcpClient {
    constructor(options = {}) {
        this.baseUrl = options.baseUrl || '/api/complaint-workspace';
        this.mcpBaseUrl = options.mcpBaseUrl || `${this.baseUrl}/mcp`;
        this.origin = options.origin || (typeof window !== 'undefined' && window.location ? window.location.origin : 'http://localhost');
        this.fetchImpl = options.fetchImpl || (typeof fetch === 'function' ? fetch.bind(globalThis) : null);
        this._requestId = 1;
        this.didStorageKey = options.didStorageKey || 'complaintGenerator.did';
        this.lastToolCallStorageKey = options.lastToolCallStorageKey || 'complaintGenerator.sdkLastToolCall';
        this.toolCallLedgerStorageKey = options.toolCallLedgerStorageKey || 'complaintGenerator.sdkToolLedger';
        this.syncEventStorageKey = options.syncEventStorageKey || DEFAULT_SYNC_EVENT_STORAGE_KEY;
        this.maxToolLedgerEntries = Number(options.maxToolLedgerEntries || 8);
        this.csrfToken = typeof options.csrfToken === 'string' ? options.csrfToken : '';
        this.activePrincipalId = '';
        this.caseContext = null;
        this._interfaceBudget = INTERFACE_REQUEST_BUDGET;
        this._interfaceInFlight = 0;
        this._interfaceQueue = [];
        this._interfaceRecords = [];
        this._bindingGeneration = 0;
        this._bindingKey = '';
        if (options.caseContext) this.setCaseContext(options.caseContext);
        this._privacyEpoch = 0;
        this._privacyActive = true;
        this._pendingRequests = new Set();
        this._boundedInference = {key: '', attempts: 0, retries: 0, view: projectBoundedInferenceReceipt(null, {lifecycle: 'idle', terminal: true, revision: null}), inflight: null, controller: null, remoteRevoked: false};
        clearPrivateBrowserStorage([this.lastToolCallStorageKey, this.toolCallLedgerStorageKey, this.syncEventStorageKey]);
        // A legacy cache accepted arbitrary text; retain only opaque IDs.
        try { this.getCachedDid(); } catch (error) { /* Storage may be unavailable. */ }
    }

    setCaseContext(context) {
        if (!context || !['tenant_id', 'case_id', 'resource_id'].every(field => typeof context[field] === 'string' && context[field])) throw new Error('mcp_tool_error');
        if (this._pendingRequests) this.clearPrivateBrowserState();
        this.caseContext = {tenant_id: context.tenant_id, case_id: context.case_id, resource_id: context.resource_id};
        const revision = context.expected_revision === undefined ? context.revision : context.expected_revision;
        if (Number.isSafeInteger(revision) && revision >= 1) this.caseContext.expected_revision = revision;
        if (Number.isSafeInteger(context.expected_membership_revision) && context.expected_membership_revision >= 1) this.caseContext.expected_membership_revision = context.expected_membership_revision;
        this._privacyActive = true;
        this.noteInterfaceBinding({
            actorId: this.activePrincipalId,
            caseId: context.case_id,
            keyRevision: context.key_revision !== undefined ? context.key_revision : context.keyRevision,
            consentRevision: context.consent_revision !== undefined ? context.consent_revision : context.consentRevision,
        });
        return {configured: true};
    }

    _recordInterface(lifecycle, extra) {
        const row = Object.assign({lifecycle, terminal: lifecycle !== 'pending', published: false, completed: false}, extra || {});
        this._interfaceRecords.push(row);
        if (this._interfaceRecords.length > 32) this._interfaceRecords.shift();
        return row;
    }

    interfaceRequestView() {
        const budget = this._interfaceBudget;
        return {
            budget: {maxInFlight: budget.maxInFlight, maxQueued: budget.maxQueued, deadlineMs: budget.deadlineMs},
            inFlight: this._interfaceInFlight,
            queued: this._interfaceQueue.length,
            bindingGeneration: this._bindingGeneration,
            records: this._interfaceRecords.map((row) => Object.assign({}, row)),
        };
    }

    noteInterfaceBinding(binding) {
        const source = binding && typeof binding === 'object' ? binding : {};
        const key = [
            source.actorId || source.principal_id || this.activePrincipalId || '',
            source.caseId || source.case_id || (this.caseContext && this.caseContext.case_id) || '',
            source.keyRevision == null ? '' : String(source.keyRevision),
            source.consentRevision == null ? '' : String(source.consentRevision),
        ].join('\u001f');
        let changed = false;
        if (this._bindingKey && this._bindingKey !== key) {
            this._retireInterfaceRequests('binding');
            changed = true;
        }
        this._bindingKey = key;
        return {generation: this._bindingGeneration, changed};
    }

    _retireInterfaceRequests(reason) {
        this._bindingGeneration += 1;
        const generation = this._bindingGeneration;
        const queued = this._interfaceQueue.splice(0, this._interfaceQueue.length);
        queued.forEach((entry) => {
            this._recordInterface('cancelled', {reason: reason || 'retired', queued: true, generation, published: false, late: false});
            entry.reject(interfaceLifecycleError('cancelled'));
        });
        if (this._pendingRequests) this._pendingRequests.forEach((controller) => controller.abort());
        return generation;
    }

    _acquireInterfacePermit(generation) {
        const budget = this._interfaceBudget;
        if (this._interfaceInFlight < budget.maxInFlight) {
            this._interfaceInFlight += 1;
            this._recordInterface('pending', {queued: false, generation, published: false});
            return Promise.resolve(generation);
        }
        if (this._interfaceQueue.length >= budget.maxQueued) {
            this._recordInterface('unavailable', {reason: 'request_budget', generation, published: false, terminal: true});
            return Promise.reject(interfaceLifecycleError('unavailable'));
        }
        this._recordInterface('pending', {queued: true, generation, published: false});
        return new Promise((resolve, reject) => {
            this._interfaceQueue.push({generation, resolve, reject});
        });
    }

    _releaseInterfacePermit() {
        this._interfaceInFlight = Math.max(0, this._interfaceInFlight - 1);
        while (this._interfaceQueue.length && this._interfaceInFlight < this._interfaceBudget.maxInFlight) {
            const entry = this._interfaceQueue.shift();
            if (entry.generation !== this._bindingGeneration) {
                this._recordInterface('cancelled', {queued: true, late: true, generation: entry.generation, published: false});
                entry.reject(interfaceLifecycleError('cancelled'));
                continue;
            }
            this._interfaceInFlight += 1;
            entry.resolve(entry.generation);
            return;
        }
    }

    async selectCanonicalCase(caseId) {
        if (typeof caseId !== 'string' || !caseId || !this.activePrincipalId) throw stateChangedError();
        const principalId = this.activePrincipalId;
        this.clearPrivateBrowserState();
        this.caseContext = null;
        const epoch = this._privacyEpoch;
        const current = () => epoch === this._privacyEpoch && principalId === this.activePrincipalId;
        // Lifecycle requests still use the real cookie, CSRF check and server
        // catalog authorization while old private requests remain retired.
        const actor = await this._request(`${this.baseUrl}/auth/session`, {method: 'GET'}, true);
        if (!current() || actor.authenticated !== true || actor.principal_id !== principalId) throw stateChangedError();
        this.csrfToken = typeof actor.csrf_token === 'string' ? actor.csrf_token : '';
        const record = await this._request('/api/cases/' + encodeURIComponent(caseId) + '/select',
            {method: 'POST', body: JSON.stringify({})}, true);
        if (!current() || record.case_id !== caseId || record.actor_principal_id !== principalId
                || record.plaintext_available === false) throw stateChangedError();
        this.setBrowserSession(actor);
        this.setCaseContext(Object.assign({}, record, {expected_revision: record.directory_revision}));
        return record;
    }

    _caseArguments(argumentsPayload) {
        const args = Object.assign({}, argumentsPayload || {});
        // Canonical storage owner is not an actor claim. Other explicit
        // claims stay visible to the server's ordinary mismatch denial.
        if (this.caseContext && args.user_id === this.caseContext.tenant_id) delete args.user_id;
        return args;
    }

    initialize() {
        return this.callJsonRpc('initialize', {
            clientInfo: {
                name: 'complaint-generator-browser-sdk',
                version: '0.1.0',
            },
        });
    }

    async _request(path, options = {}, lifecycle = false) {
        if (typeof this.fetchImpl !== 'function') throw new Error('mcp_tool_error');
        if (!lifecycle && !this._privacyActive) throw stateChangedError();
        const epoch = this._privacyEpoch;
        const generation = this._bindingGeneration;
        let permitHeld = false;
        let controller = null;
        let deadlineTimer = null;
        await this._acquireInterfacePermit(generation);
        permitHeld = true;
        controller = new AbortController();
        this._pendingRequests.add(controller);
        try {
        if (generation !== this._bindingGeneration || (!lifecycle && !this._privacyActive)) throw interfaceLifecycleError('cancelled');
        const target = new URL(path, this.origin);
        const sameOrigin = target.origin === new URL(this.origin).origin;
        const caseRequest = this.caseContext && sameOrigin && !target.pathname.includes('/auth/');
        let requestTarget = path;
        if (caseRequest && target.searchParams.get('user_id') === this.caseContext.tenant_id) {
            target.searchParams.delete('user_id');
            requestTarget = target.toString();
        }
        if (options.signal) {
            if (options.signal.aborted) controller.abort();
            else options.signal.addEventListener('abort', () => controller.abort(), {once: true});
        }
        const headers = new Headers(options.headers || {});
        if (!headers.has('Content-Type')) headers.set('Content-Type', 'application/json');
        if (caseRequest) {
            headers.set('x-tenant-id', this.caseContext.tenant_id);
            headers.set('x-case-id', this.caseContext.case_id);
            headers.set('x-resource-id', this.caseContext.resource_id);
            if (this.caseContext.expected_revision) headers.set('x-expected-revision', String(this.caseContext.expected_revision));
            if (this.caseContext.expected_membership_revision) headers.set('x-expected-membership-revision', String(this.caseContext.expected_membership_revision));
        }
        if (this.csrfToken && new URL(path, this.origin).origin === new URL(this.origin).origin) headers.set('x-csrf-token', this.csrfToken);
            const response = await Promise.race([
                this.fetchImpl(requestTarget, Object.assign({}, options, {headers, credentials: 'same-origin', signal: controller.signal})),
                new Promise((_, reject) => {
                    deadlineTimer = setTimeout(() => {
                        controller.abort();
                        reject(interfaceLifecycleError('timeout'));
                    }, this._interfaceBudget.deadlineMs);
                }),
            ]);
            if (!lifecycle && (epoch !== this._privacyEpoch || generation !== this._bindingGeneration)) throw stateChangedError();
            if (!response.ok) {
                const denied = response.status === 401 || response.status === 403;
                let code = denied ? 'authorization_denied' : `http_${response.status}`;
                if (response.status === 429) code = 'rate_limited';
                if (response.status === 408 || response.status === 504) code = 'timeout';
                let contract;
                let readable = null;
                if (response.status === 409) {
                    try {
                        const conflictBody = await response.json();
                        readable = conflictBody && conflictBody.result ? conflictBody.result : conflictBody;
                        const body = readable;
                        const publicCode = publicToolErrorCode(body);
                        if (['stale_question', 'revision_conflict', 'inquiry_mismatch', 'stale_target'].includes(publicCode)) code = publicCode;
                        const structured = body && body.structuredContent ? body.structuredContent : body;
                        const interview = structured && structured.interview ? structured.interview : {};
                        contract = projectSyncDetail(Object.assign({}, structured, {session_revision: interview.session_revision}));
                        if (structured && structured !== readable) readable = structured;
                    } catch (readError) { /* The fixed HTTP code remains truthful. */ }
                }
                if (!lifecycle && (epoch !== this._privacyEpoch || generation !== this._bindingGeneration)) throw stateChangedError();
                const error = new Error(code);
                error.code = code;
                error.status = response.status; error.authorizationDenied = denied; error.isError = true;
                if (contract) error.contract = contract;
                if (readable && typeof readable === 'object') error.readable = readable;
                throw error;
            }
            const payload = await response.json();
            if (!lifecycle && (epoch !== this._privacyEpoch || generation !== this._bindingGeneration)) throw stateChangedError();
            if (payload && payload.isError === true && !payload.jsonrpc) {
                const code = publicToolErrorCode(payload);
                const error = new Error(code); error.code = code; error.status = response.status; error.authorizationDenied = code === 'authorization_denied'; error.isError = true;
                throw error;
            }
            this._recordInterface('completed', {generation, published: true, completed: true, terminal: true});
            return payload;
        } catch (error) {
            const late = generation !== this._bindingGeneration;
            if (error && (error.name === 'AbortError' || error.lifecycle === 'cancelled' || error.lifecycle === 'timeout' || (error.message === 'workspace_state_changed' && late))) {
                const lifecycle = error.lifecycle === 'timeout' ? 'timeout' : 'cancelled';
                this._recordInterface(lifecycle, {generation, published: false, late, completed: false, terminal: true});
                if (error.lifecycle === 'timeout') throw error;
                const cancelled = interfaceLifecycleError('cancelled');
                cancelled.late = late;
                throw cancelled;
            }
            throw error;
        } finally {
            if (deadlineTimer) clearTimeout(deadlineTimer);
            if (controller) this._pendingRequests.delete(controller);
            if (permitHeld) this._releaseInterfacePermit();
        }
    }

    setBrowserSession(issued) {
        this.clearPrivateBrowserState();
        this.csrfToken = issued && typeof issued.csrf_token === 'string' ? issued.csrf_token : '';
        this.activePrincipalId = issued && typeof issued.principal_id === 'string' ? issued.principal_id : '';
        this.caseContext = null;
        this._privacyActive = true;
        this.noteInterfaceBinding({actorId: this.activePrincipalId, caseId: '', keyRevision: '', consentRevision: ''});
        return {principal_id: this.activePrincipalId, configured: Boolean(this.csrfToken)};
    }

    async _rpc(method, params) {
        const payload = await this._request(`${this.mcpBaseUrl}/rpc`, {
            method: 'POST',
            body: JSON.stringify({
                jsonrpc: '2.0',
                id: this._requestId++,
                method,
                params: method === 'tools/call' && params ? Object.assign({}, params, {arguments: this._caseArguments(params.arguments)}) : (params || {}),
            }),
        });
        if (!payload || typeof payload !== 'object') throw new Error('mcp_tool_error');
        if (payload.error) {
            const error = new Error(publicErrorMessage(payload.error.message || 'JSON-RPC request failed'));
            error.isError = true;
            error.authorizationDenied = authorizationDeniedText(payload.error.message || '');
            throw error;
        }
        if (payload.result && payload.result.isError === true) {
            const code = publicToolErrorCode(payload.result);
            const error = new Error(code); error.isError = true; error.authorizationDenied = code === 'authorization_denied';
            error.readable = payload.result.structuredContent && typeof payload.result.structuredContent === 'object'
                ? payload.result.structuredContent
                : payload.result;
            throw error;
        }
        if (!Object.prototype.hasOwnProperty.call(payload, 'result')) throw new Error('mcp_tool_error');
        return payload.result;
    }

    callJsonRpc(method, params) {
        return this._rpc(method, params);
    }

    _cacheLastToolCall(detail) {
        const published = publicToolActivity(detail);
        if (typeof localStorage === 'undefined') {
            return published;
        }
        try {
            localStorage.setItem(this.lastToolCallStorageKey, JSON.stringify(published));
            const existing = this.getToolCallLedger();
            const ledger = [published].concat(existing).slice(0, this.maxToolLedgerEntries);
            localStorage.setItem(this.toolCallLedgerStorageKey, JSON.stringify(ledger));
        } catch (error) {
            return published;
        }
        return published;
    }

    _publishLastToolCall(detail) {
        const published = this._cacheLastToolCall(detail);
        if (typeof window !== 'undefined' && typeof window.dispatchEvent === 'function' && typeof CustomEvent === 'function') {
            window.dispatchEvent(new CustomEvent('complaint-mcp-sdk-call', { detail: published }));
        }
        return published;
    }

    _publishSyncEvent(detail) {
        return dispatchSharedSyncEvent(detail, this.syncEventStorageKey);
    }

    _publishDerivedSyncEvents(toolName, argumentsPayload, structuredContent, status) {
        if (String(status || '').toLowerCase() !== 'success') {
            return [];
        }
        const normalizedToolName = String(toolName || '').trim();
        const args = argumentsPayload && typeof argumentsPayload === 'object' ? argumentsPayload : {};
        const payload = structuredContent && typeof structuredContent === 'object' ? structuredContent : {};
        const userId = String(
            (payload.session && payload.session.user_id)
            || payload.user_id
            || args.user_id
            || ''
        ).trim();
        const manifestPath = String(
            payload.manifest_path
            || payload.manifest_json_path
            || args.manifest_path
            || ''
        ).trim();
        const events = [];
        const workspaceMutationTools = new Set([
            'complaint.start_session',
            'complaint.submit_intake',
            'complaint.run_intake_chat_turn',
            'complaint.save_evidence',
            'complaint.import_gmail_evidence',
            'complaint.import_local_evidence',
            'complaint.review_case',
            'complaint.generate_complaint',
            'complaint.update_draft',
            'complaint.build_mike_handoff',
            'complaint.sync_mike_final_draft',
            'complaint.update_claim_type',
            'complaint.update_case_synopsis',
            'complaint.reset_session',
        ]);
        const docketTools = new Set([
            'complaint.get_packaged_docket_operator_dashboard',
            'complaint.load_packaged_docket_operator_dashboard_report',
            'complaint.execute_packaged_docket_proof_revalidation_queue',
            'complaint.persist_packaged_docket_proof_revalidation_queue',
            'complaint.view_docket_dataset',
            'complaint.search_docket_dataset',
            'complaint.get_docket_dataset_metadata',
            'complaint.get_docket_dataset_graph',
        ]);

        const interview = payload.interview && typeof payload.interview === 'object' ? payload.interview : {};
        const graph = interview.graph && typeof interview.graph === 'object' ? interview.graph : {};
        const revision = interview.session_revision !== undefined ? interview.session_revision : (payload.session_revision !== undefined ? payload.session_revision : null);
        const contract = {
            tool_name: normalizedToolName,
            status: 'success',
            user_id: userId,
            revision: revision,
            session_revision: revision,
            expected_question_revision: args.expected_question_revision !== undefined ? args.expected_question_revision : (payload.expected_question_revision !== undefined ? payload.expected_question_revision : interview.expected_question_revision),
            interview_action: args.interview_action || payload.interview_action || interview.action || '',
            pending_inquiry_id: payload.pending_inquiry_id || '',
            question_id: args.question_id || '',
            conflict: payload.conflict || '',
            graph_version: graph.graph_version !== undefined ? graph.graph_version : '',
        };
        if (workspaceMutationTools.has(normalizedToolName)) {
            events.push(this._publishSyncEvent(Object.assign({
                event_type: normalizedToolName === 'complaint.reset_session' ? 'workspace.reset' : 'workspace.updated',
            }, contract)));
        }
        if (docketTools.has(normalizedToolName)) {
            events.push(this._publishSyncEvent(Object.assign({
                event_type: normalizedToolName === 'complaint.persist_packaged_docket_proof_revalidation_queue' ? 'docket.persisted' : 'docket.updated',
                manifest_path: manifestPath,
            }, contract)));
        }
        return events;
    }

    getLastToolCall() {
        if (typeof localStorage === 'undefined') {
            return null;
        }
        try {
            const raw = localStorage.getItem(this.lastToolCallStorageKey);
            return raw ? publicToolActivity(JSON.parse(raw)) : null;
        } catch (error) {
            return null;
        }
    }

    getToolCallLedger() {
        if (typeof localStorage === 'undefined') {
            return [];
        }
        try {
            const raw = localStorage.getItem(this.toolCallLedgerStorageKey);
            const parsed = raw ? JSON.parse(raw) : [];
            return Array.isArray(parsed) ? parsed.map(publicToolActivity) : [];
        } catch (error) {
            return [];
        }
    }

    getToolImpactSummary() {
        const ledger = this.getToolCallLedger();
        const latest = ledger[0] || null;
        const successCount = ledger.filter((item) => String((item && item.status) || '').toLowerCase() === 'success').length;
        const errorCount = ledger.filter((item) => String((item && item.status) || '').toLowerCase() === 'error').length;
        return {
            total_calls: ledger.length,
            success_count: successCount,
            error_count: errorCount,
            latest_tool_name: latest ? String(latest.tool_name || '').trim() : '',
            latest_status: latest ? String(latest.status || '').trim() : '',
            latest_finished_at: latest ? String(latest.finished_at || '').trim() : '',
        };
    }

    async getWorkflowOperationSnapshot(userId) {
        const [releaseGate, workflowCapabilities, toolingContract, mikeIntegrationStatus] = await Promise.all([
            this.getCanonicalReleaseGate(userId),
            this.getWorkflowCapabilities(userId),
            this.getToolingContract(userId),
            this.getMikeIntegrationStatus(userId),
        ]);
        return {
            tool_impact_summary: this.getToolImpactSummary(),
            canonical_release_gate: releaseGate,
            workflow_capabilities: workflowCapabilities,
            tooling_contract: toolingContract,
            mike_integration_status: mikeIntegrationStatus,
        };
    }

    ping() {
        return this.callJsonRpc('ping', {});
    }

    async listTools() {
        const result = await this._rpc('tools/list', {});
        return result.tools || [];
    }

    _extractToolDiagnostics(payload) {
        const structured = payload && typeof payload === 'object' ? payload : {};
        const diagnostics = [];
        const directSearchDiagnostics = structured.search_diagnostics && typeof structured.search_diagnostics === 'object'
            ? structured.search_diagnostics
            : null;
        const authorityDiagnostics = structured.authorities_diagnostics && typeof structured.authorities_diagnostics === 'object'
            ? structured.authorities_diagnostics
            : null;

        const appendDiagnosticEntries = (scope, container) => {
            if (!container || typeof container !== 'object') {
                return;
            }
            Object.entries(container).forEach(([key, value]) => {
                if (!value || typeof value !== 'object' || !value.warning_code) {
                    return;
                }
                diagnostics.push({
                    scope: scope,
                    family: key,
                    warning_code: String(value.warning_code || '').trim(),
                    warning_message: String(value.warning_message || '').trim(),
                    state_code: String(value.state_code || '').trim(),
                    hf_dataset_id: String(value.hf_dataset_id || '').trim(),
                });
            });
        };

        appendDiagnosticEntries('search', directSearchDiagnostics);
        if (authorityDiagnostics) {
            Object.entries(authorityDiagnostics).forEach(([claimType, value]) => {
                if (!value || typeof value !== 'object') {
                    return;
                }
                const claimScope = 'claim:' + String(claimType || '').trim();
                appendDiagnosticEntries(claimScope, value);
            });
        }

        return diagnostics;
    }

    _buildToolDiagnosticSummary(payload) {
        const diagnostics = this._extractToolDiagnostics(payload);
        const warningCount = diagnostics.length;
        const primary = diagnostics[0] || null;
        return {
            warning_count: warningCount,
            warnings: diagnostics,
            primary_warning: primary,
            summary_text: primary && primary.warning_message
                ? primary.warning_message
                : '',
        };
    }

    async callTool(toolName, argumentsPayload) {
        const startedAt = new Date().toISOString();
        const epoch = this._privacyEpoch;
        const generation = this._bindingGeneration;
        try {
            const result = await this._rpc('tools/call', {
                name: toolName,
                arguments: argumentsPayload || {},
            });
            if (result && result.isError === true) {
                const code = publicToolErrorCode(result);
                const failure = new Error(code);
                failure.isError = true;
                failure.authorizationDenied = code === 'authorization_denied';
                    throw failure;
            }
            if (epoch !== this._privacyEpoch || generation !== this._bindingGeneration || !this._privacyActive) throw stateChangedError();
            const structuredContent = result && result.structuredContent ? result.structuredContent : result;
            const diagnosticSummary = this._buildToolDiagnosticSummary(structuredContent);
            const args = argumentsPayload && typeof argumentsPayload === 'object' ? argumentsPayload : {};
            this._publishLastToolCall({
                tool_name: toolName,
                status: 'success',
                started_at: startedAt,
                finished_at: new Date().toISOString(),
                diagnostic_summary: diagnosticSummary,
                expected_question_revision: args.expected_question_revision,
                interview_action: args.interview_action,
                revision: structuredContent && structuredContent.interview ? structuredContent.interview.session_revision : null,
            });
            this._publishDerivedSyncEvents(toolName, argumentsPayload, structuredContent, 'success');
            if (result && result.structuredContent) {
                return result.structuredContent;
            }
            return result;
        } catch (error) {
            if (epoch !== this._privacyEpoch || generation !== this._bindingGeneration || !this._privacyActive) throw stateChangedError();
            if (error && (error.lifecycle === 'cancelled' || error.lifecycle === 'unavailable' || error.lifecycle === 'timeout' || error.late === true)) throw error;
            const args = argumentsPayload && typeof argumentsPayload === 'object' ? argumentsPayload : {};
            this._publishLastToolCall({
                tool_name: toolName,
                status: 'error',
                started_at: startedAt,
                finished_at: new Date().toISOString(),
                error_message: error && error.message ? error.message : String(error),
                authorization_denied: Boolean(error && error.authorizationDenied),
                is_error: true,
                expected_question_revision: args.expected_question_revision,
                interview_action: args.interview_action,
            });
            throw error;
        }
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
        const value = localStorage.getItem(this.didStorageKey);
        if (typeof value === 'string' && /^(?:[a-f0-9]{32}|did:key:(?:[A-Za-z0-9]+|fallback-[a-f0-9]{32}))$/.test(value)) return value;
        localStorage.removeItem(this.didStorageKey);
        return null;
    }

    cacheDid(did) {
        if (typeof did !== 'string' || !/^(?:[a-f0-9]{32}|did:key:(?:[A-Za-z0-9]+|fallback-[a-f0-9]{32}))$/.test(did)) throw new Error('mcp_tool_error');
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
        this._privacyActive = true;
        if (this.caseContext) {
            const current = await this._request(`${this.baseUrl}/auth/session`, {method: 'GET'});
            if (!current || current.authenticated !== true || typeof current.principal_id !== 'string') throw new Error('session_required');
            this.activePrincipalId = current.principal_id;
        }
        const did = this.caseContext ? this.activePrincipalId : (userId || await this.getOrCreateDid());
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

    runIntakeChatTurn(userId, message, questionId, options = {}) {
        const extra = options && typeof options === 'object' ? options : {};
        const args = {
            user_id: userId,
            message: message || undefined,
            question_id: questionId || extra.question_id || undefined,
        };
        if (extra.expected_question_revision !== undefined && extra.expected_question_revision !== null && extra.expected_question_revision !== '') {
            args.expected_question_revision = extra.expected_question_revision;
        }
        if (extra.interview_action) {
            args.interview_action = extra.interview_action;
        }
        if (extra.expected_graph_revision !== undefined && extra.expected_graph_revision !== null && extra.expected_graph_revision !== '') {
            args.expected_graph_revision = extra.expected_graph_revision;
        }
        if (extra.expected_session_revision !== undefined && extra.expected_session_revision !== null && extra.expected_session_revision !== '') {
            args.expected_session_revision = extra.expected_session_revision;
        }
        return this.callTool('complaint.run_intake_chat_turn', args);
    }

    async _readableGraphResult(error) {
        const body = error && error.readable && typeof error.readable === 'object' ? error.readable : null;
        if (!body) throw error;
        return {accepted: false, conflict: String(error.code || body.conflict || ''), payload: body};
    }

    async submitCanonicalGraphAnswer(userId, message, options = {}) {
        const extra = options && typeof options === 'object' ? options : {};
        const questionId = String(extra.question_id || '').trim();
        const revision = Number(extra.expected_question_revision);
        if (!questionId.startsWith('inq-') || !Number.isSafeInteger(revision)) {
            const error = new Error('question_revision_required');
            error.code = 'question_revision_required';
            throw error;
        }
        try {
            const payload = await this.runIntakeChatTurn(userId, message, questionId, {
                expected_question_revision: revision,
                interview_action: extra.interview_action || 'answer',
            });
            const conflict = payload && (payload.conflict || (payload.interview && payload.interview.status === 'refused' ? (payload.interview.error && payload.interview.error.code) : ''));
            return {accepted: !conflict, conflict: conflict || '', payload: payload};
        } catch (error) {
            return this._readableGraphResult(error);
        }
    }

    async submitCanonicalGraphCorrection(userId, replacement, options = {}) {
        const extra = options && typeof options === 'object' ? options : {};
        const graphRevision = String(extra.expected_graph_revision || '').trim();
        const sessionRevision = Number(extra.expected_session_revision);
        if (!graphRevision || !Number.isSafeInteger(sessionRevision)) {
            const error = new Error('question_revision_required');
            error.code = 'question_revision_required';
            throw error;
        }
        const message = JSON.stringify({
            schema: 'gui-factual-correction-v1',
            replacement: String(replacement || ''),
            expected_graph_revision: graphRevision,
            expected_session_revision: sessionRevision,
            target_stable_id: String(extra.target_stable_id || ''),
            actor_principal_id: String(extra.actor_principal_id || ''),
        });
        try {
            const payload = await this.runIntakeChatTurn(userId, message, extra.question_id || extra.target_stable_id || '', {
                interview_action: 'correct',
                expected_graph_revision: graphRevision,
                expected_session_revision: sessionRevision,
            });
            const receipt = payload && payload.factual_correction ? payload.factual_correction : {};
            const conflict = receipt.status && receipt.status !== 'applied' ? String((receipt.error && receipt.error.code) || receipt.status) : (payload && payload.conflict) || '';
            return {accepted: receipt.status === 'applied', conflict: conflict, payload: payload};
        } catch (error) {
            return this._readableGraphResult(error);
        }
    }

    clearPrivateBrowserState() {
        this._privacyEpoch += 1;
        this._privacyActive = false;
        if (this._interfaceQueue) this._retireInterfaceRequests('privacy');
        else if (this._pendingRequests) {
            this._pendingRequests.forEach((controller) => controller.abort());
            this._pendingRequests.clear();
        }
        try { this.getCachedDid(); } catch (error) { /* Storage may be unavailable. */ }
        return clearPrivateBrowserStorage([
            this.lastToolCallStorageKey,
            this.toolCallLedgerStorageKey,
            this.syncEventStorageKey,
        ]);
    }

    switchWorkspaceUser(nextUserId) {
        this.clearPrivateBrowserState();
        storageBuckets().forEach((bucket) => {
            try {
                bucket.removeItem(this.didStorageKey);
            } catch (error) {
                // Identity removal is best-effort during a user switch.
            }
        });
        this.activeUserId = nextUserId ? String(nextUserId) : '';
        this.caseContext = null;
        this.noteInterfaceBinding({actorId: this.activeUserId, caseId: '', keyRevision: '', consentRevision: ''});
        return { user_id: this.activeUserId, switched: true, cleared: true };
    }

    async logout() {
        this.switchWorkspaceUser('');
        let loggedOut = false;
        try {
            if (this.csrfToken) {
                await this._request(`${this.baseUrl}/auth/logout`, {method: 'POST', body: '{}'}, true);
                loggedOut = true;
            } else {
                try { await this._request(`${this.baseUrl}/auth/session`, {method: 'GET'}, true); }
                catch (error) { if (error.status === 401) loggedOut = true; else throw error; }
                if (!loggedOut) throw new Error('csrf_required');
            }
            return {logged_out: true, cleared: true};
        } finally {
            this.csrfToken = '';
            this.activePrincipalId = '';
        }
    }

    saveEvidence(userId, payload) {
        return this.callTool('complaint.save_evidence', Object.assign({
            user_id: userId,
        }, payload || {}));
    }

    importGmailEvidence(payload) {
        return this.callTool('complaint.import_gmail_evidence', payload || {});
    }

    importLocalEvidence(payload) {
        return this.callTool('complaint.import_local_evidence', payload || {});
    }

    runGmailDuckdbPipeline(payload) {
        return this.callTool('complaint.run_gmail_duckdb_pipeline', payload || {});
    }

    searchEmailDuckdb(payload) {
        return this.callTool('complaint.search_email_duckdb_corpus', payload || {});
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

    getClientReleaseGate(userId) {
        return this.callTool('complaint.get_client_release_gate', {
            user_id: userId,
        });
    }

    toCanonicalReleaseGate(payload) {
        const source = (payload && typeof payload === 'object') ? payload : {};
        const gate = source.complaint_output_release_gate || source.release_gate || source;
        const verdict = String((gate && (gate.verdict || gate.status)) || 'unknown').trim().toLowerCase() || 'unknown';
        const blockers = Array.isArray(gate && gate.blockers)
            ? gate.blockers
            : Array.isArray(gate && gate.blocking_reasons)
                ? gate.blocking_reasons
                : String((gate && gate.reason) || '').trim()
                    ? [String(gate.reason).trim()]
                    : [];
        const updatedAt = String((gate && gate.updated_at) || (source && source.updated_at) || '').trim() || new Date().toISOString();
        const gateSource = String((gate && gate.source) || (source && source.source) || 'complaint.get_client_release_gate').trim();
        const version = String((gate && (gate.version || gate.state_version)) || (source && (source.version || source.state_version)) || 'workspace-gate-v1').trim();
        const reason = String((gate && gate.reason) || '').trim() || (blockers[0] || '');
        const unblockAction = String((gate && (gate.next_best_action || gate.unblock_action)) || '').trim();
        const status = String((gate && gate.status) || verdict || 'unknown').trim().toUpperCase();
        return {
            verdict,
            status,
            blockers,
            blocking_reasons: blockers,
            updated_at: updatedAt,
            source: gateSource,
            version,
            state_version: version,
            next_best_action: unblockAction,
            canonical_gate: {
                verdict,
                status,
                reason,
                unblock_action: unblockAction,
                next_best_action: unblockAction,
                source: gateSource,
                timestamp: updatedAt,
                version,
                state_version: version,
                blocking_reasons: blockers,
            },
            reason,
            unblock_action: unblockAction,
            claim_type_label: String((gate && gate.claim_type_label) || '').trim() || 'Unknown',
            draft_strategy: String((gate && gate.draft_strategy) || '').trim() || 'template',
            filing_shape_score: Number((gate && gate.filing_shape_score) || 0),
            claim_type_alignment_score: Number((gate && gate.claim_type_alignment_score) || 0),
        };
    }

    async getCanonicalReleaseGate(userId) {
        const payload = await this.getClientReleaseGate(userId);
        return this.toCanonicalReleaseGate(payload);
    }

    getWorkflowCapabilities(userId) {
        return this.callTool('complaint.get_workflow_capabilities', {
            user_id: userId,
        });
    }

    getToolingContract(userId) {
        return this.callTool('complaint.get_tooling_contract', {
            user_id: userId,
        });
    }

    getWorkspaceDataSchema(userId, options = {}) {
        return this.callTool('complaint.get_workspace_data_schema', Object.assign({
            user_id: userId,
        }, options || {}));
    }

    migrateLegacyWorkspaceData(userId, outputDir, options = {}) {
        return this.callTool('complaint.migrate_legacy_workspace_data', Object.assign({
            user_id: userId,
            output_dir: outputDir,
        }, options || {}));
    }

    searchWorkspaceDataset(inputPath, query, options = {}) {
        return this.callTool('complaint.search_workspace_dataset', Object.assign({
            input_path: inputPath,
            query: query,
        }, options || {}));
    }

    viewWorkspaceDataset(inputPath, options = {}) {
        return this.callTool('complaint.view_workspace_dataset', Object.assign({
            input_path: inputPath,
        }, options || {}));
    }

    viewDocketDataset(inputPath, options = {}) {
        return this.callTool('complaint.view_docket_dataset', Object.assign({
            input_path: inputPath,
        }, options || {}));
    }

    searchDocketDataset(inputPath, query, options = {}) {
        return this.callTool('complaint.search_docket_dataset', Object.assign({
            input_path: inputPath,
            query: query,
        }, options || {}));
    }

    getDocketDatasetMetadata(inputPath, options = {}) {
        return this.callTool('complaint.get_docket_dataset_metadata', Object.assign({
            input_path: inputPath,
        }, options || {}));
    }

    getDocketDatasetGraph(inputPath, options = {}) {
        return this.callTool('complaint.get_docket_dataset_graph', Object.assign({
            input_path: inputPath,
        }, options || {}));
    }

    getPackagedDocketOperatorDashboard(manifestPath) {
        return this.callTool('complaint.get_packaged_docket_operator_dashboard', {
            manifest_path: manifestPath,
        });
    }

    loadPackagedDocketOperatorDashboardReport(manifestPath, reportFormat = 'parsed') {
        return this.callTool('complaint.load_packaged_docket_operator_dashboard_report', {
            manifest_path: manifestPath,
            report_format: reportFormat || 'parsed',
        });
    }

    executePackagedDocketProofRevalidationQueue(manifestPath, options = {}) {
        return this.callTool('complaint.execute_packaged_docket_proof_revalidation_queue', Object.assign({
            manifest_path: manifestPath,
        }, options || {}));
    }

    persistPackagedDocketProofRevalidationQueue(manifestPath, outputDir, options = {}) {
        return this.callTool('complaint.persist_packaged_docket_proof_revalidation_queue', Object.assign({
            manifest_path: manifestPath,
            output_dir: outputDir,
        }, options || {}));
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

    buildMikeHandoff(payload) {
        return this.callTool('complaint.build_mike_handoff', payload || {});
    }

    getMikeIntegrationStatus(userId) {
        return this.callTool('complaint.get_mike_integration_status', {
            user_id: userId,
        });
    }

    syncMikeFinalDraft(payload) {
        return this.callTool('complaint.sync_mike_final_draft', payload || {});
    }

    getDraftProofReport(userId, options = {}) {
        return this.callTool('complaint.get_draft_proof_report', Object.assign({
            user_id: userId,
            allow_live_scrape_fallback: false,
        }, options || {}));
    }

    renderDraftProofReport(userId, options = {}) {
        return this.callTool('complaint.render_draft_proof_report', Object.assign({
            user_id: userId,
        }, options || {}));
    }

    pinDraftProofReport(userId, options = {}) {
        return this.callTool('complaint.pin_draft_proof_report', Object.assign({
            user_id: userId,
        }, options || {}));
    }

    scoreDraftQuality(userId, options = {}) {
        return this.callTool('complaint.score_draft_quality', Object.assign({
            user_id: userId,
        }, options || {}));
    }

    improveDraft(userId, options = {}) {
        return this.callTool('complaint.improve_draft', Object.assign({
            user_id: userId,
        }, options || {}));
    }

    getProofHistory(userId) {
        return this.callTool('complaint.get_proof_history', {
            user_id: userId,
        });
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

    exportComplaintDocx(userId) {
        return this.callTool('complaint.export_complaint_docx', {
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

    getFormalDiagnostics(userId) {
        return this.callTool('complaint.get_formal_diagnostics', {
            user_id: userId,
        });
    }

    getFilingProvenance(userId) {
        return this.callTool('complaint.get_filing_provenance', {
            user_id: userId,
        });
    }

    getProviderDiagnostics(userId) {
        return this.callTool('complaint.get_provider_diagnostics', {
            user_id: userId,
        });
    }

    reviewGeneratedExports(payload) {
        return this.callTool('complaint.review_generated_exports', payload || {});
    }

    updateClaimType(userId, claimType) {
        return this.callTool('complaint.update_claim_type', {
            user_id: userId,
            claim_type: claimType,
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

    _boundedInferenceContext(extra) {
        const state = this._boundedInference;
        return Object.assign({
            attemptCount: state.attempts,
            retryCount: state.retries,
            remoteRevoked: state.remoteRevoked,
            preserveRevision: state.view && Number.isSafeInteger(state.view.revision) ? state.view.revision : null,
        }, extra || {});
    }

    _settleBoundedInference(view) {
        const state = this._boundedInference;
        if (view.remote_processing === 'revoked') state.remoteRevoked = true;
        if (view.remote_processing !== 'revoked' && state.remoteRevoked) view = Object.assign({}, view, {remote_processing: 'revoked', requirements_supported: false});
        if (view.lifecycle === 'partial') view = Object.assign({}, view, {requirements_supported: false, remote_processing: state.remoteRevoked ? 'revoked' : 'not_reenabled'});
        view.requirements_supported = false;
        state.view = view;
        return view;
    }

    async dispatchBoundedGuiInference(body, options) {
        const extra = options && typeof options === 'object' ? options : {};
        const retry = extra.retry === true;
        const state = this._boundedInference;
        const revision = this.caseContext && Number.isSafeInteger(this.caseContext.expected_revision) ? this.caseContext.expected_revision : null;
        const key = boundedInferenceKey(body, revision);
        if (state.inflight) return state.inflight;
        if (!retry && state.key === key && state.view && state.view.terminal && state.view.lifecycle !== 'cancelled') return state.view;
        if (retry) {
            if (state.key !== key || !state.view || state.view.retryable !== true) {
                return this._settleBoundedInference(projectBoundedInferenceReceipt(state.view, this._boundedInferenceContext({
                    lifecycle: state.view ? state.view.lifecycle : 'unobserved',
                    error: {code: 'retry_not_applicable'},
                    previousLifecycle: state.view ? state.view.lifecycle : 'idle',
                    terminal: true,
                    stages: state.view ? state.view.stages : [],
                })));
            }
            if (state.retries >= MAX_BOUNDED_INFERENCE_RETRIES) {
                return this._settleBoundedInference(projectBoundedInferenceReceipt(null, this._boundedInferenceContext({
                    lifecycle: 'retry_exhausted',
                    error: {code: 'retry_exhausted'},
                    terminal: true,
                    stages: state.view.stages,
                })));
            }
            state.retries += 1;
        } else {
            state.key = key;
            state.attempts = 0;
            state.retries = 0;
        }
        state.attempts += 1;
        const controller = new AbortController();
        state.controller = controller;
        const pending = projectBoundedInferenceReceipt(null, this._boundedInferenceContext({
            lifecycle: 'dispatching', terminal: false, stages: [{kind: 'request', status: 'dispatching'}],
        }));
        state.view = pending;
        if (typeof extra.onView === 'function') extra.onView(pending);
        const run = (async () => {
            try {
                const payload = await this._request('/api/complaint-workspace/inference/dispatch', {
                    method: 'POST', body: JSON.stringify(body || {}), signal: controller.signal,
                });
                const view = this._settleBoundedInference(projectBoundedInferenceReceipt(payload, this._boundedInferenceContext({
                    terminal: true, stages: [{kind: 'request', status: 'dispatching'}],
                })));
                if (typeof extra.onView === 'function') extra.onView(view);
                return view;
            } catch (error) {
                const view = this._settleBoundedInference(projectBoundedInferenceReceipt(null, this._boundedInferenceContext({
                    error: error, terminal: true, stages: [{kind: 'request', status: 'dispatching'}],
                })));
                if (typeof extra.onView === 'function') extra.onView(view);
                return view;
            } finally {
                state.inflight = null;
                state.controller = null;
            }
        })();
        state.inflight = run;
        return run;
    }

    observeBoundedGuiInference(payload, context) {
        const state = this._boundedInference;
        if (state.inflight) return state.inflight;
        const view = this._settleBoundedInference(projectBoundedInferenceReceipt(payload, this._boundedInferenceContext(Object.assign({terminal: true}, context || {}))));
        state.key = '';
        state.controller = null;
        return view;
    }

    cancelBoundedGuiInference() {
        const state = this._boundedInference;
        if (state.controller) state.controller.abort();
        if (state.inflight) return state.inflight;
        return state.view;
    }

    projectCanonicalContinuity(payload) {
        const source = payload && typeof payload === 'object' ? payload : {};
        const session = source.session && typeof source.session === 'object' ? source.session : {};
        const shared = session.shared_interview && typeof session.shared_interview === 'object' ? session.shared_interview : {};
        const pending = shared.pending_inquiry && typeof shared.pending_inquiry === 'object' ? shared.pending_inquiry : {};
        const review = source.review && typeof source.review === 'object' ? source.review : {};
        const evidence = []
            .concat(Array.isArray(review.testimony) ? review.testimony : [])
            .concat(Array.isArray(review.documents) ? review.documents : []);
        const draft = session.draft && typeof session.draft === 'object'
            ? session.draft
            : (source.draft && typeof source.draft === 'object' ? source.draft : {});
        const inquiryRevision = Number.isSafeInteger(pending.revision) ? pending.revision : null;
        return {
            transport: 'complaint-workspace-session',
            user_id: typeof session.user_id === 'string' ? session.user_id : '',
            case_id: typeof session.case_id === 'string' ? session.case_id : '',
            private_revision: session.private_revision === undefined || session.private_revision === null ? null : session.private_revision,
            session_revision: shared.session_revision === undefined || shared.session_revision === null ? null : shared.session_revision,
            inquiry_id: typeof pending.inquiry_id === 'string' ? pending.inquiry_id : '',
            inquiry_revision: inquiryRevision,
            evidence_ids: evidence.map((item) => item && item.id ? String(item.id) : '').filter(Boolean).sort(),
            draft_title: typeof draft.title === 'string' ? draft.title : '',
            draft_body: typeof draft.body === 'string' ? draft.body : '',
            draft_updated_at: typeof draft.updated_at === 'string' ? draft.updated_at : '',
        };
    }

    async readCanonicalSession(binding) {
        const url = new URL(`${this.baseUrl}/session`, this.origin);
        const headers = {accept: 'application/json'};
        const caseId = binding && typeof binding.case_id === 'string' ? binding.case_id : '';
        if (caseId) {
            url.searchParams.set('case_id', caseId);
            headers['x-case-id'] = caseId;
            if (typeof binding.tenant_id === 'string' && binding.tenant_id) headers['x-tenant-id'] = binding.tenant_id;
            if (typeof binding.resource_id === 'string' && binding.resource_id) headers['x-resource-id'] = binding.resource_id;
            if (Number.isSafeInteger(binding.directory_revision) && binding.directory_revision >= 1) {
                headers['x-expected-revision'] = String(binding.directory_revision);
            }
        }
        const payload = await this._request(url.toString(), {method: 'GET', headers});
        return {continuity: this.projectCanonicalContinuity(payload)};
    }
}


const ComplaintMcpSdk = {
    ComplaintMcpClient,
    default: ComplaintMcpClient,
    SYNC_EVENT_NAME,
    DEFAULT_SYNC_EVENT_STORAGE_KEY,
    publishSyncEvent: dispatchSharedSyncEvent,
    projectSyncDetail: projectSyncDetail,
    projectBoundedInferenceReceipt: projectBoundedInferenceReceipt,
    MAX_BOUNDED_INFERENCE_RETRIES: MAX_BOUNDED_INFERENCE_RETRIES,
    INTERFACE_REQUEST_BUDGET: INTERFACE_REQUEST_BUDGET,
    clearPrivateBrowserStorage: clearPrivateBrowserStorage,
};

  if (globalScope) {
    globalScope.ComplaintMcpSdk = Object.assign({}, globalScope.ComplaintMcpSdk || {}, ComplaintMcpSdk);
  }

  if (typeof module !== 'undefined' && module.exports) {
    module.exports = ComplaintMcpSdk;
  }
})(typeof globalThis !== 'undefined' ? globalThis : (typeof window !== 'undefined' ? window : this));
