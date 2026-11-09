(function () {
    const readinessStorageKey = 'complaintGenerator.uiReadiness';
    const lastToolCallStorageKey = 'complaintGenerator.sdkLastToolCall';
    const shellModeStorageKey = 'complaintGenerator.shellMode';
    const shellModeValues = new Set(['client', 'operator']);
    const primaryNavItems = [
        ['Landing', '/'],
        ['Secure Intake', '/home'],
        ['Workspace', '/workspace'],
        ['Review', '/claim-support-review'],
        ['Builder', '/document'],
        ['Chat', '/chat'],
    ];
    const advancedNavItems = [
        ['Profile', '/profile'],
        ['Results', '/results'],
        ['Editor', '/mlwysiwyg'],
        ['Trace', '/document/optimization-trace'],
        ['SDK', '/ipfs-datasets/sdk-playground'],
        ['Dashboards', '/dashboards'],
    ];

    function safeText(value, fallback) {
        if (value === null || value === undefined || value === '') {
            return fallback;
        }
        return String(value);
    }

    function normalizeShellMode(value) {
        const normalized = String(value || '').trim().toLowerCase();
        return shellModeValues.has(normalized) ? normalized : '';
    }

    function readStoredShellMode() {
        if (typeof localStorage === 'undefined') {
            return '';
        }
        try {
            return normalizeShellMode(localStorage.getItem(shellModeStorageKey));
        } catch (error) {
            return '';
        }
    }

    function writeStoredShellMode(mode) {
        if (typeof localStorage === 'undefined') {
            return;
        }
        try {
            localStorage.setItem(shellModeStorageKey, mode);
        } catch (error) {
            // Ignore storage failures.
        }
    }

    function resolveShellMode() {
        const params = new URLSearchParams(window.location.search || '');
        const queryMode = normalizeShellMode(params.get('shell_mode') || params.get('app_shell_mode'));
        if (queryMode) {
            writeStoredShellMode(queryMode);
            return queryMode;
        }
        const storedMode = readStoredShellMode();
        if (storedMode) {
            return storedMode;
        }
        const bodyMode = normalizeShellMode(document.body && document.body.dataset ? document.body.dataset.complaintShellMode : '');
        return bodyMode || 'client';
    }

    function buildShellModeHref(targetMode) {
        const mode = normalizeShellMode(targetMode) || 'client';
        const next = new URL(window.location.href);
        next.searchParams.set('shell_mode', mode);
        return `${next.pathname}${next.search}${next.hash}`;
    }

    function countAnsweredQuestions(payload) {
        if (payload && Array.isArray(payload.questions)) {
            return payload.questions.filter((question) => {
                if (!question) {
                    return false;
                }
                if (typeof question.is_answered === 'boolean') {
                    return question.is_answered;
                }
                return Boolean(question.answer);
            }).length;
        }
        const answers = payload && payload.session && payload.session.intake_answers;
        return answers ? Object.keys(answers).length : 0;
    }

    function buildSummary(payload, complaintReadiness) {
        const review = payload && payload.review ? payload.review : {};
        const overview = review.overview || {};
        const session = payload && payload.session ? payload.session : {};
        const nextQuestion = payload && payload.next_question ? payload.next_question.prompt : 'Intake complete.';
        const draftState = resolveShellDraftState(payload, complaintReadiness);
        const draft = draftState.draft;
        const draftSummary = draft && draft.title
            ? draft.title
            : (draftState.hasDraft ? 'Draft in progress.' : 'No draft generated yet.');
        return {
            answeredQuestions: countAnsweredQuestions(payload),
            supportedElements: overview.supported_elements || 0,
            missingElements: overview.missing_elements || 0,
            evidenceCount: (overview.testimony_items || 0) + (overview.document_items || 0),
            nextQuestion: nextQuestion,
            draftSummary: draftSummary,
        };
    }

    function resolveShellDraftState(payload, complaintReadiness) {
        const session = payload && payload.session ? payload.session : {};
        const directDraft = payload && payload.draft ? payload.draft : null;
        const sessionDraft = session.draft || null;
        const draft = directDraft || sessionDraft || null;
        const readinessHasDraft = Boolean(complaintReadiness && complaintReadiness.has_draft);
        return {
            draft: draft,
            hasDraft: Boolean(draft) || readinessHasDraft,
        };
    }

    function deriveWorkflowState(payload, complaintReadiness) {
        const review = payload && payload.review ? payload.review : {};
        const overview = review.overview || {};
        const session = payload && payload.session ? payload.session : {};
        const summary = buildSummary(payload || {}, complaintReadiness || null);
        const draftState = resolveShellDraftState(payload, complaintReadiness);
        const draft = draftState.draft;
        const answeredQuestions = Number(summary.answeredQuestions || 0);
        const totalQuestions = Array.isArray(payload && payload.questions) ? payload.questions.length : 0;
        const evidenceCount = Number(summary.evidenceCount || 0);
        const missingElements = Number(summary.missingElements || 0);
        const caseSynopsis = String((payload && payload.case_synopsis) || session.case_synopsis || '').trim();
        const intakeComplete = totalQuestions > 0 ? answeredQuestions >= totalQuestions : answeredQuestions > 0;
        const reviewReady = intakeComplete || answeredQuestions >= Math.max(2, Math.ceil(totalQuestions * 0.6)) || evidenceCount > 0;
        const builderReady = draftState.hasDraft || (intakeComplete && missingElements === 0 && evidenceCount > 0);
        const mediatorReady = Boolean(caseSynopsis) || answeredQuestions > 0;
        const phaseLabel = draftState.hasDraft
            ? 'draft refinement'
            : !reviewReady
                ? 'intake first'
                : missingElements > 0 || evidenceCount === 0
                    ? 'support building'
                    : 'ready for drafting';
        return {
            summary,
            reviewReady,
            builderReady,
            mediatorReady,
            phaseLabel,
            reviewGateReason: reviewReady
                ? `Support review is available with ${answeredQuestions} answered intake prompt${answeredQuestions === 1 ? '' : 's'} and ${evidenceCount} evidence item${evidenceCount === 1 ? '' : 's'}.`
                : 'Finish more intake in the workspace before opening review from the shared shell.',
            builderGateReason: builderReady
                ? (draft
                    ? 'A complaint draft already exists for this shared session.'
                    : 'The record is coherent enough to justify formal drafting.')
                : (!intakeComplete
                    ? 'Finish intake before opening the formal builder from the shared shell.'
                    : evidenceCount === 0
                        ? 'Add evidence before opening the formal builder from the shared shell.'
                        : 'Close the remaining support gaps before opening the formal builder from the shared shell.'),
            mediatorGateReason: mediatorReady
                ? 'The shared case framing is ready for mediator coaching.'
                : 'Capture at least one intake answer or synopsis detail before opening the mediator.',
        };
    }

    function buildGatedLink(className, label, href, enabled, reason) {
        const disabledClass = enabled ? '' : ' is-disabled';
        const disabledAttr = enabled ? 'false' : 'true';
        return '<a class="' + className + disabledClass + '" href="' + href + '" aria-disabled="' + disabledAttr + '" data-disabled-reason="' + safeText(reason, '') + '">' + label + '</a>';
    }

    function findPageTitle() {
        const heading = document.querySelector('h1');
        if (heading && heading.textContent.trim()) {
            return heading.textContent.trim();
        }
        return document.title || 'Complaint Generator';
    }

    function findPageDescription() {
        const metaDescription = document.querySelector('meta[name="description"]');
        if (metaDescription && metaDescription.content) {
            return metaDescription.content;
        }
        const workspaceParagraph = document.querySelector('main p, .hero p, .card p, .lead');
        if (workspaceParagraph && workspaceParagraph.textContent.trim()) {
            return workspaceParagraph.textContent.trim();
        }
        return 'Shared complaint workflow shell powered by the same browser MCP SDK and workspace service.';
    }

    function loadCachedReadiness() {
        if (typeof localStorage === 'undefined') {
            return null;
        }
        try {
            const raw = localStorage.getItem(readinessStorageKey);
            if (!raw) {
                return null;
            }
            const parsed = JSON.parse(raw);
            return parsed && typeof parsed === 'object' ? parsed : null;
        } catch (error) {
            return null;
        }
    }

    function loadCachedLastToolCall() {
        if (typeof localStorage === 'undefined') {
            return null;
        }
        try {
            const raw = localStorage.getItem(lastToolCallStorageKey);
            if (!raw) {
                return null;
            }
            const parsed = JSON.parse(raw);
            return parsed && typeof parsed === 'object' ? parsed : null;
        } catch (error) {
            return null;
        }
    }

    function latestToolDiagnosticSummary(lastToolCall) {
        const summary = lastToolCall && lastToolCall.diagnostic_summary && typeof lastToolCall.diagnostic_summary === 'object'
            ? lastToolCall.diagnostic_summary
            : null;
        return summary || null;
    }

    function formatToolDiagnosticMeta(primaryWarning) {
        if (!primaryWarning || typeof primaryWarning !== 'object') {
            return '';
        }
        const fragments = [];
        const family = String(primaryWarning.family || '').trim();
        const warningCode = String(primaryWarning.warning_code || '').trim();
        const stateCode = String(primaryWarning.state_code || '').trim();
        const datasetId = String(primaryWarning.hf_dataset_id || '').trim();
        if (family) {
            fragments.push('Family: ' + family);
        }
        if (warningCode) {
            fragments.push('Code: ' + warningCode);
        }
        if (stateCode) {
            fragments.push('State: ' + stateCode);
        }
        if (datasetId) {
            fragments.push('Dataset: ' + datasetId);
        }
        return fragments.join(' | ');
    }

    function readShellContext(state) {
        const params = new URLSearchParams(window.location.search);
        const sessionPayload = state && state.sessionPayload ? state.sessionPayload : {};
        const session = sessionPayload && sessionPayload.session ? sessionPayload.session : {};
        return {
            userId: String(params.get('user_id') || state.did || '').trim(),
            caseSynopsis: String(params.get('case_synopsis') || sessionPayload.case_synopsis || session.case_synopsis || '').trim(),
            claimType: String(params.get('claim_type') || sessionPayload.claim_type || session.claim_type || '').trim(),
            returnTo: window.location.pathname + window.location.search,
        };
    }

    function buildShellSurfaceUrl(path, context, extraParams) {
        const params = new URLSearchParams();
        if (context && context.userId) {
            params.set('user_id', context.userId);
        }
        if (context && context.caseSynopsis) {
            params.set('case_synopsis', context.caseSynopsis);
        }
        if (context && context.claimType && path === '/claim-support-review') {
            params.set('claim_type', context.claimType);
        }
        if (context && context.returnTo && path === '/chat') {
            params.set('return_to', context.returnTo);
        }
        if (extraParams && typeof extraParams === 'object') {
            Object.entries(extraParams).forEach(([key, value]) => {
                if (value === null || value === undefined || value === '') {
                    return;
                }
                params.set(key, String(value));
            });
        }
        const query = params.toString();
        return query ? path + '?' + query : path;
    }

    function renderShell(state) {
        const existing = document.getElementById('cg-app-shell');
        if (existing) {
            existing.remove();
        }
        if (document.body) {
            document.body.classList.remove('cg-app-shell-active');
        }

        const summary = buildSummary(state.sessionPayload, state.complaintReadiness || null);
        const workflowState = deriveWorkflowState(state.sessionPayload || {}, state.complaintReadiness || null);
        const shellMode = resolveShellMode();
        const isOperatorMode = shellMode === 'operator';
        const shell = document.createElement('aside');
        shell.id = 'cg-app-shell';
        shell.className = 'cg-app-shell';
        shell.setAttribute('aria-label', 'Complaint Generator Application Sidebar');

        const context = readShellContext(state);

        const renderNavLink = ([label, href]) => {
            const targetUrl = buildShellSurfaceUrl(href, context);
            const active = window.location.pathname === href ? ' is-active' : '';
            const gatedReview = href === '/claim-support-review';
            const gatedBuilder = href === '/document';
            const enabled = gatedReview ? workflowState.reviewReady : (gatedBuilder ? workflowState.builderReady : true);
            const reason = gatedReview ? workflowState.reviewGateReason : (gatedBuilder ? workflowState.builderGateReason : '');
            return '<a class="cg-app-shell__nav-link' + active + (enabled ? '' : ' is-disabled') + '" href="' + targetUrl + '" aria-disabled="' + (enabled ? 'false' : 'true') + '" data-disabled-reason="' + safeText(reason, '') + '">' + label + '</a>';
        };
        const navHtml = primaryNavItems.map(renderNavLink).join('');
        const advancedNavHtml = advancedNavItems.map(renderNavLink).join('');
        const modeToggleHref = buildShellModeHref(isOperatorMode ? 'client' : 'operator');
        const modeToggleLabel = isOperatorMode ? 'Use client mode' : 'Use operator mode';
        const modeChipLabel = isOperatorMode ? 'Operator mode' : 'Client mode';
        const readiness = state.uiReadiness || loadCachedReadiness();
        const lastToolCall = loadCachedLastToolCall();
        const readinessVerdict = readiness && readiness.verdict ? readiness.verdict : 'No UI verdict cached';
        const readinessScore = readiness && Number.isFinite(Number(readiness.score)) ? String(readiness.score) + '/100' : 'pending';
        const readinessUpdated = readiness && readiness.updated_at ? readiness.updated_at : '';
        const readinessStages = readiness && Array.isArray(readiness.tested_stages) ? readiness.tested_stages : [];
        const readinessBlockers = readiness && Array.isArray(readiness.release_blockers) ? readiness.release_blockers : [];
        const readinessTools = readiness && Array.isArray(readiness.exposed_tools) ? readiness.exposed_tools : [];
        const toolDiagnosticSummary = latestToolDiagnosticSummary(lastToolCall);
        const toolDiagnosticPrimary = toolDiagnosticSummary && toolDiagnosticSummary.primary_warning
            ? toolDiagnosticSummary.primary_warning
            : null;
        const toolDiagnosticMeta = formatToolDiagnosticMeta(toolDiagnosticPrimary);
        const readinessTone = readiness && String(readiness.verdict || '').toLowerCase() === 'client-safe'
            ? ' is-good'
            : readiness
                ? ' is-warn'
                : '';
        const complaintReadiness = state.complaintReadiness || {
            verdict: 'Not ready to draft',
            score: 'pending',
            detail: 'Load the complaint session to estimate readiness.',
        };
        const complaintReadinessTone = String(complaintReadiness.verdict || '').toLowerCase() === 'ready for first draft'
            || String(complaintReadiness.verdict || '').toLowerCase() === 'draft in progress'
            ? ' is-good'
            : ' is-warn';
        const canonicalReleaseGate = state.canonicalReleaseGate || {};
        const releaseGateVerdict = String(canonicalReleaseGate.verdict || 'unknown').trim().toLowerCase();
        const releaseGateSafe = releaseGateVerdict === 'client_safe' || releaseGateVerdict === 'pass' || releaseGateVerdict === 'ready';
        const releaseGateBlockers = Array.isArray(canonicalReleaseGate.blockers) ? canonicalReleaseGate.blockers : [];
        const releaseGateReason = String(canonicalReleaseGate.reason || '').trim() || releaseGateBlockers[0] || 'Refresh the release gate before treating complaint output as safe to download.';
        const releaseGateVersion = String(canonicalReleaseGate.version || '').trim() || 'workspace-gate-v1';
        const releaseGateTone = releaseGateSafe ? ' is-good' : ' is-warn';
        const releaseGateNextStep = String(canonicalReleaseGate.unblock_action || '').trim() || (releaseGateSafe
            ? 'Keep packet export and next-step guidance visible while downloading.'
            : 'Use Review or Evidence to close blockers, then refresh packet export and gate checks.');
        const shellDraftState = resolveShellDraftState(state.sessionPayload || {}, state.complaintReadiness || null);
        const primaryActionKey = !workflowState.reviewReady
            ? 'workspace'
            : (!workflowState.builderReady
                ? 'review'
                : (!shellDraftState.hasDraft
                    ? 'builder'
                    : (!releaseGateSafe ? 'export' : 'builder')));
        const primaryActionHref = primaryActionKey === 'workspace'
            ? buildShellSurfaceUrl('/workspace', context)
            : primaryActionKey === 'review'
                ? buildShellSurfaceUrl('/claim-support-review', context)
                : primaryActionKey === 'export'
                    ? buildShellSurfaceUrl('/workspace', context, { target_tab: 'draft' })
                    : buildShellSurfaceUrl('/document', context);
        const primaryActionLabel = primaryActionKey === 'workspace'
            ? 'Primary: Continue Intake'
            : primaryActionKey === 'review'
                ? 'Primary: Close Support Gaps'
                : primaryActionKey === 'export'
                    ? 'Primary: Export + Review Gate'
                    : 'Primary: Draft Complaint';
        const workflowNextStep = primaryActionKey === 'workspace'
            ? 'Primary action: continue intake in Workspace, then reopen Review once enough factual detail is saved.'
            : primaryActionKey === 'review'
                ? 'Primary action: resolve support gaps in Review before moving into formal drafting.'
                : primaryActionKey === 'export'
                    ? 'Primary action: keep generation, packet export, and release-gate next-step guidance visible together before any download.'
                    : 'Primary action: generate or refine the complaint draft in Builder, then use Workspace export + release-gate checks before download.';
        const draftFlowEnabled = workflowState.builderReady;
        const draftFlowReason = draftFlowEnabled
            ? 'Draft flow rail is available because this session is ready for drafting.'
            : workflowState.builderGateReason;
        const actionLinks = [
            buildGatedLink('cg-app-shell__action', 'Open Workspace', buildShellSurfaceUrl('/workspace', context), true, ''),
            buildGatedLink('cg-app-shell__action', 'Open Review', buildShellSurfaceUrl('/claim-support-review', context), workflowState.reviewReady, workflowState.reviewGateReason),
            buildGatedLink('cg-app-shell__action', 'Open Builder', buildShellSurfaceUrl('/document', context), workflowState.builderReady, workflowState.builderGateReason),
            buildGatedLink('cg-app-shell__action', 'Open Export Rail', buildShellSurfaceUrl('/workspace', context, { target_tab: 'draft' }), draftFlowEnabled, draftFlowReason),
            '<a class="cg-app-shell__action" href="' + buildShellSurfaceUrl('/mlwysiwyg', context) + '">Edit Draft</a>',
        ];
        const secondaryActionLinks = actionLinks.filter((link) => {
            if (primaryActionKey === 'workspace') {
                return link.indexOf('Open Workspace') === -1;
            }
            if (primaryActionKey === 'review') {
                return link.indexOf('Open Review') === -1;
            }
            if (primaryActionKey === 'export') {
                return link.indexOf('Open Export Rail') === -1;
            }
            return link.indexOf('Open Builder') === -1;
        });
        const advancedNavSection = isOperatorMode
            ? '<details class="cg-app-shell__drawer" id="cg-app-shell-advanced-nav" open><summary class="cg-app-shell__drawer-summary">Developer tools and linked surfaces</summary><div class="cg-app-shell__nav cg-app-shell__nav--secondary">' + advancedNavHtml + '</div></details>'
            : '<div class="cg-app-shell__phase-note">Developer dashboards and MCP internals are hidden in client mode.</div>';
        const sessionSyncSection = isOperatorMode
            ? [
                '<div class="cg-app-shell__section-title">Session Sync</div>',
                '<div class="cg-app-shell__readiness" id="cg-app-shell-session-sync">',
                '<div class="cg-app-shell__readiness-header"><strong>' + safeText(lastToolCall && (lastToolCall.status === 'error' || lastToolCall.is_error) ? 'Last shared call failed' : (state.did ? 'Shared session synced' : 'Session not loaded'), 'Session not loaded') + '</strong><span>' + safeText(workflowState.phaseLabel, 'unknown') + '</span></div>',
                '<div class="cg-app-shell__readiness-copy">' + safeText(lastToolCall && lastToolCall.tool_name ? ('Last MCP tool: ' + lastToolCall.tool_name) : 'No MCP tool calls have been cached for this browser session yet.') + '</div>',
                '<div class="cg-app-shell__phase-note">' + safeText(lastToolCall && lastToolCall.finished_at ? ('Updated: ' + lastToolCall.finished_at) : 'Updated: waiting for the next shared SDK action.') + '</div>',
                (lastToolCall && lastToolCall.status ? '<div class="cg-app-shell__phase-note">Status: ' + safeText(lastToolCall.status, 'unknown') + (lastToolCall.error_message ? ' (' + safeText(lastToolCall.error_message, '') + ')' : '') + '</div>' : ''),
                (toolDiagnosticPrimary ? '<div class="cg-app-shell__phase-note">Latest retrieval warning: ' + safeText(toolDiagnosticPrimary.warning_message, '') + '</div>' : ''),
                (toolDiagnosticMeta ? '<div class="cg-app-shell__phase-note">Retrieval warning details: ' + safeText(toolDiagnosticMeta, '') + '</div>' : ''),
                '</div>',
            ].join('')
            : '';
        const uiReadinessSection = isOperatorMode
            ? [
                '<div class="cg-app-shell__section-title">UI Readiness</div>',
                '<div class="cg-app-shell__readiness' + readinessTone + '" id="cg-app-shell-readiness">',
                '<div class="cg-app-shell__readiness-header"><strong>' + safeText(readinessVerdict, 'No UI verdict cached') + '</strong><span>' + safeText(readinessScore, 'pending') + '</span></div>',
                '<div class="cg-app-shell__readiness-copy">' + safeText(readinessBlockers[0], readiness ? 'The latest actor/critic review did not return a release blocker.' : 'Run UX Audit in the workspace to cache an actor/critic verdict for the rest of the site.') + '</div>',
                '<div class="cg-app-shell__readiness-meta">' + (readinessStages.length ? ('Stages: ' + readinessStages.join(', ')) : 'Stages: not reviewed yet') + '</div>',
                '<div class="cg-app-shell__readiness-meta">' + (readinessTools.length ? ('Shared tools: ' + readinessTools.slice(0, 3).join(', ')) : 'Shared tools: not cached yet') + '</div>',
                (readinessUpdated ? '<div class="cg-app-shell__readiness-meta">Updated: ' + safeText(readinessUpdated, '') + '</div>' : ''),
                '<a class="cg-app-shell__action" href="' + buildShellSurfaceUrl('/workspace', context, { target_tab: 'ux-review' }) + '">Open UX Audit</a>',
                '</div>',
            ].join('')
            : '';
        const draftFlowRailSection = isOperatorMode
            ? [
                '<div class="cg-app-shell__section-title">Draft Flow Rail</div>',
                '<div class="cg-app-shell__draft-rail' + (draftFlowEnabled && releaseGateSafe ? '' : ' is-warn') + '" id="cg-app-shell-draft-flow-rail">',
                '<div class="cg-app-shell__phase-note">Keep one visible sequence: generate or refine, export and review, then confirm the release-gate next step.</div>',
                '<div class="cg-app-shell__draft-flow-grid">',
                buildGatedLink('cg-app-shell__draft-step', '1. Generate / refine draft', buildShellSurfaceUrl('/document', context), draftFlowEnabled, draftFlowReason),
                buildGatedLink('cg-app-shell__draft-step', '2. Export + review packet', buildShellSurfaceUrl('/workspace', context, { target_tab: 'draft' }), draftFlowEnabled, draftFlowReason),
                buildGatedLink('cg-app-shell__draft-step', '3. Check next-step gate', buildShellSurfaceUrl('/workspace', context, { target_tab: 'draft' }), draftFlowEnabled, draftFlowReason),
                '</div>',
                '</div>',
            ].join('')
            : '';
        const releaseGateTitle = isOperatorMode ? 'Client gate' : 'Filing gate';
        const releaseGateVersionCopy = isOperatorMode ? safeText(releaseGateVersion, 'workspace-gate-v1') : 'client-safe check';
        const releaseGateNextCopy = isOperatorMode
            ? safeText(releaseGateNextStep, '')
            : (releaseGateSafe ? 'You can proceed to export review and attorney handoff.' : 'Stay in Review and Evidence until filing blockers are cleared.');

        shell.innerHTML = [
            '<div class="cg-app-shell__inner">',
            '<div class="cg-app-shell__mode-row">',
            '<span class="cg-app-shell__mode-chip">' + modeChipLabel + '</span>',
            '<a class="cg-app-shell__mode-toggle" href="' + modeToggleHref + '">' + modeToggleLabel + '</a>',
            '</div>',
            '<div class="cg-app-shell__eyebrow">Complaint Generator</div>',
            '<h2 class="cg-app-shell__title">' + safeText(findPageTitle(), 'Complaint Generator') + '</h2>',
            '<p class="cg-app-shell__copy">' + safeText(findPageDescription(), '') + '</p>',
            '<div class="cg-app-shell__status" id="cg-app-shell-status">' + safeText(state.status, 'Shell ready.') + '</div>',
            '<div class="cg-app-shell__section-title">Session</div>',
            '<div class="cg-app-shell__chip-row">',
            '<div class="cg-app-shell__chip"><span class="cg-app-shell__chip-label">DID</span><span class="cg-app-shell__chip-value" id="cg-app-shell-did">' + safeText(state.did, 'Unavailable') + '</span></div>',
            '<div class="cg-app-shell__chip"><span class="cg-app-shell__chip-label">' + (isOperatorMode ? 'Tools' : 'Operator') + '</span><span class="cg-app-shell__chip-value">' + (isOperatorMode ? safeText(state.toolCount, '0') + ' MCP tools' : 'Technical tools hidden in client mode') + '</span></div>',
            '</div>',
            '<div class="cg-app-shell__section-title">Navigate</div>',
            '<div class="cg-app-shell__nav">' + navHtml + '</div>',
            advancedNavSection,
            '<div class="cg-app-shell__section-title">Case Snapshot</div>',
            '<div class="cg-app-shell__stats">',
            '<div class="cg-app-shell__stat"><span class="cg-app-shell__stat-label">Intake</span><span class="cg-app-shell__stat-value" id="cg-app-shell-intake-count">' + summary.answeredQuestions + '</span><span class="cg-app-shell__stat-detail">' + safeText(summary.nextQuestion, 'Intake complete.') + '</span></div>',
            '<div class="cg-app-shell__stat"><span class="cg-app-shell__stat-label">Support Review</span><span class="cg-app-shell__stat-value" id="cg-app-shell-supported-count">' + summary.supportedElements + '</span><span class="cg-app-shell__stat-detail">' + summary.missingElements + ' claim elements still need support.</span></div>',
            '<div class="cg-app-shell__stat"><span class="cg-app-shell__stat-label">Evidence</span><span class="cg-app-shell__stat-value" id="cg-app-shell-evidence-count">' + summary.evidenceCount + '</span><span class="cg-app-shell__stat-detail">' + safeText(summary.draftSummary, 'No draft generated yet.') + '</span></div>',
            '</div>',
            '<div class="cg-app-shell__section-title">Complaint Readiness</div>',
            '<div class="cg-app-shell__readiness' + complaintReadinessTone + '" id="cg-app-shell-complaint-readiness">',
            '<div class="cg-app-shell__readiness-header"><strong>' + safeText(complaintReadiness.verdict, 'Not reviewed') + '</strong><span>' + safeText(String(complaintReadiness.score) + '/100', 'pending') + '</span></div>',
            '<div class="cg-app-shell__readiness-copy">' + safeText(complaintReadiness.detail, 'Load the complaint session to estimate readiness.') + '</div>',
            '<div class="cg-app-shell__readiness-meta">Answered intake: ' + safeText(complaintReadiness.answered_questions, summary.answeredQuestions) + '. Supported elements: ' + safeText(complaintReadiness.supported_elements, summary.supportedElements) + '. Evidence items: ' + safeText(complaintReadiness.evidence_count, summary.evidenceCount) + '.</div>',
            '<a class="cg-app-shell__action" href="' + buildShellSurfaceUrl('/workspace', context) + '">Continue complaint workflow</a>',
            '</div>',
            '<div class="cg-app-shell__section-title">Workflow Phase</div>',
            '<div class="cg-app-shell__readiness" id="cg-app-shell-workflow-phase">',
            '<div class="cg-app-shell__readiness-header"><strong>' + safeText(workflowState.phaseLabel, 'phase unavailable') + '</strong><span>' + safeText(state.did, 'no DID') + '</span></div>',
            '<div class="cg-app-shell__readiness-copy">The shared shell now gates review and builder links so every page respects the same complaint phase.</div>',
            '<div class="cg-app-shell__phase-note">' + safeText(workflowState.builderReady ? 'The session is coherent enough for cross-surface drafting.' : workflowState.builderGateReason, '') + '</div>',
            '</div>',
            sessionSyncSection,
            uiReadinessSection,
            '<div class="cg-app-shell__section-title">Complaint Output Gate</div>',
            '<div class="cg-app-shell__readiness' + releaseGateTone + '" id="cg-app-shell-release-gate">',
            '<div class="cg-app-shell__readiness-header"><strong>' + releaseGateTitle + ': ' + safeText(String(canonicalReleaseGate.verdict || 'unknown').toUpperCase(), 'UNKNOWN') + '</strong><span>' + releaseGateVersionCopy + '</span></div>',
            '<div class="cg-app-shell__readiness-copy">' + safeText(releaseGateReason, 'Refresh the release gate before treating complaint output as safe to download.') + '</div>',
            '<div class="cg-app-shell__readiness-meta">' + safeText(releaseGateBlockers.length ? ('Blockers: ' + releaseGateBlockers.join('; ')) : 'Blockers: none reported in the latest gate response.', '') + '</div>',
            '<div class="cg-app-shell__readiness-meta">Next step: ' + releaseGateNextCopy + '</div>',
            '<a class="cg-app-shell__action" href="' + buildShellSurfaceUrl('/workspace', context, { target_tab: 'draft' }) + '">Open Draft + Export Rail</a>',
            '</div>',
            '<div class="cg-app-shell__section-title">Next Actions</div>',
            '<div class="cg-app-shell__actions" id="cg-app-shell-actions">',
            buildGatedLink('cg-app-shell__action is-primary', primaryActionLabel, primaryActionHref, primaryActionKey === 'workspace' ? true : (primaryActionKey === 'review' ? workflowState.reviewReady : (primaryActionKey === 'export' ? draftFlowEnabled : workflowState.builderReady)), primaryActionKey === 'review' ? workflowState.reviewGateReason : (primaryActionKey === 'builder' ? workflowState.builderGateReason : (primaryActionKey === 'export' ? draftFlowReason : ''))).replace('class="cg-app-shell__action is-primary', 'id="cg-app-shell-primary-action" data-stage-primary="true" class="cg-app-shell__action is-primary'),
            secondaryActionLinks.join(''),
            '</div>',
            '<div class="cg-app-shell__workflow-rail' + (workflowState.builderReady && releaseGateSafe ? '' : ' is-warn') + '" id="cg-app-shell-workflow-rail">',
            '<div class="cg-app-shell__phase-note">' + safeText(workflowNextStep, '') + '</div>',
            '<div class="cg-app-shell__phase-note">Keep draft generation, packet export, and release-gate next-step guidance visible together before downloading complaint files.</div>',
            (!releaseGateSafe ? '<div class="cg-app-shell__phase-note">Release gate warning: ' + safeText(releaseGateReason, '') + '</div>' : ''),
            '</div>',
            draftFlowRailSection,
            '<div class="cg-app-shell__meta">' + (isOperatorMode
                ? 'This sidebar is backed by the same cached DID and complaint workspace session used by the CLI, MCP tools, and browser SDK.'
                : 'Client mode keeps focus on next steps toward a filing-ready complaint for attorney review.') + '</div>',
            '</div>',
        ].join('');

        if (document.body) {
            document.body.classList.add('cg-app-shell-active');
            document.body.appendChild(shell);
        }
        shell.addEventListener('click', (event) => {
            const gatedLink = event.target.closest('a[aria-disabled="true"]');
            if (!gatedLink) {
                return;
            }
            event.preventDefault();
            const statusNode = shell.querySelector('#cg-app-shell-status');
            if (statusNode) {
                statusNode.textContent = gatedLink.dataset.disabledReason || 'That surface is intentionally gated until the case reaches the next phase.';
            }
        });
        window.__complaintAppShell = {
            did: state.did,
            toolCount: state.toolCount,
            sessionPayload: state.sessionPayload,
        };
    }

    async function bootShell() {
        if (window.__complaintAppShellDisabled) {
            return;
        }
        if (document.body && document.body.dataset.complaintShell === 'off') {
            return;
        }

        let did = null;
        let toolCount = 0;
        let sessionPayload = null;
        let complaintReadiness = null;
        let uiReadiness = null;
        let canonicalReleaseGate = null;
        let status = 'Using shared complaint workspace shell.';

        try {
            const sdkGlobal = globalThis.ComplaintMcpSdk;
            if (!sdkGlobal || !sdkGlobal.ComplaintMcpClient) {
                throw new Error('Complaint MCP SDK not available.');
            }

            const client = new sdkGlobal.ComplaintMcpClient();
            did = await client.getOrCreateDid();
            try {
                await client.initialize();
            } catch (error) {
                status = 'Identity ready, MCP initialize returned ' + error.message + '.';
            }
            try {
                const tools = await client.listTools();
                toolCount = Array.isArray(tools) ? tools.length : 0;
            } catch (error) {
                status = 'Identity ready, but MCP tool discovery is unavailable.';
            }
            sessionPayload = await client.getSession(did);
            complaintReadiness = await client.getComplaintReadiness(did);
            uiReadiness = await client.getUiReadiness(did);
            canonicalReleaseGate = await client.getCanonicalReleaseGate(did);
            status = 'Shared session loaded for ' + did + '.';
        } catch (error) {
            status = 'Shared session unavailable: ' + error.message;
        }

        renderShell({
            did: did,
            toolCount: toolCount,
            sessionPayload: sessionPayload,
            complaintReadiness: complaintReadiness,
            uiReadiness: uiReadiness,
            canonicalReleaseGate: canonicalReleaseGate,
            status: status,
        });
    }

    const operationRetryBound = 3;
    const operationSurfaces = new Set(['graph', 'research', 'collaboration']);

    function escapeOperationText(value) {
        return String(value == null ? '' : value).replace(/[&<>"']/g, (character) => ({
            '&': '&amp;',
            '<': '&lt;',
            '>': '&gt;',
            '"': '&quot;',
            "'": '&#39;',
        }[character]));
    }

    function operationRevision(value) {
        if (value === null || value === undefined || value === '') {
            return '';
        }
        const text = String(value).trim();
        if (!text || /ready|supported|verified/i.test(text)) {
            return '';
        }
        return text.slice(0, 80);
    }

    function classifyOperationRecord(record) {
        const source = record && typeof record === 'object' ? record : {};
        const surface = operationSurfaces.has(source.surface) ? source.surface : 'graph';
        const code = String(source.code || source.error || source.conflict || '').trim().toLowerCase();
        const status = String(source.status || '').trim().toLowerCase();
        const mcpFailed = source.mcp_failed === true || source.mcp_ok === false || source.is_error === true
            || status === 'error' || code === 'mcp_tool_error';
        const missingProof = source.missing_proof === true || source.proof_present === false
            || source.proof_status === 'missing' || source.proof_status === 'not_executed';
        const unsupportedSource = source.unsupported_source === true || source.source_supported === false
            || source.source_status === 'unsupported';
        const queuedReplica = source.queued_replica === true || source.replica_status === 'queued'
            || source.replica_status === 'pending';
        const blocked = mcpFailed || missingProof || unsupportedSource || queuedReplica;
        const authorization = source.authorization_denied === true || code === 'authorization_denied'
            || status === 'denied' || status === 'authorization';
        const conflict = !authorization && (code === 'revision_conflict' || code === 'stale_question'
            || code === 'inquiry_mismatch' || status === 'conflict' || (source.conflict && code !== ''));
        let state = 'unavailable';
        if (authorization) {
            state = 'authorization';
        } else if (conflict) {
            state = 'conflict';
        } else if (source.cancelled === true) {
            state = 'unavailable';
        } else if (!blocked && (status === 'pending' || source.pending === true)) {
            state = 'pending';
        } else if (!blocked && status === 'ready' && source.verified === true && source.supported === true
            && source.proof_present === true && source.source_supported === true
            && source.replica_status === 'verified' && source.mcp_ok === true) {
            state = 'ready';
        }
        const attempts = Number.isInteger(source.attempts) && source.attempts >= 0 ? source.attempts : 0;
        const retryRemaining = state === 'ready' || state === 'authorization' || source.cancelled === true
            ? 0
            : Math.max(0, operationRetryBound - attempts);
        const revisions = {
            graph: operationRevision(source.graph_revision),
            session: operationRevision(source.session_revision),
            research: operationRevision(source.research_revision),
            collaboration: operationRevision(source.collaboration_revision),
        };
        const reasons = [];
        if (mcpFailed) {
            reasons.push('The call failed.');
        }
        if (missingProof) {
            reasons.push('Proof is missing.');
        }
        if (unsupportedSource) {
            reasons.push('The source is not usable.');
        }
        if (queuedReplica) {
            reasons.push('The replica is still queued.');
        }
        if (source.cancelled === true) {
            reasons.push('Cancelled. The current revision is unchanged.');
        }
        const titles = {
            authorization: 'Authorization required',
            conflict: 'Revision conflict',
            unavailable: 'Unavailable',
            pending: 'Pending',
            ready: 'Ready',
        };
        const defaults = {
            authorization: 'This action is not authorized for the current actor.',
            conflict: 'The record changed. Compare the current revision before another attempt.',
            unavailable: 'This surface cannot be confirmed.',
            pending: 'Work is still in progress.',
            ready: 'The current revision is confirmed.',
        };
        return {
            surface: surface,
            state: state,
            title: titles[state],
            detail: reasons.length ? reasons.join(' ') : defaults[state],
            revisions: revisions,
            attempts: attempts,
            retryRemaining: retryRemaining,
            cancelEnabled: state === 'pending',
            ready: state === 'ready',
            supported: state === 'ready',
            verified: state === 'ready',
            fallbackBlocked: blocked,
        };
    }

    function renderOperationSurface(target, model) {
        const node = typeof target === 'string' ? document.getElementById(target) : target;
        if (!node || !model) {
            return null;
        }
        const revisions = model.revisions || {};
        node.dataset.task = 'CIMP-GUI-54';
        node.dataset.surface = model.surface;
        node.dataset.state = model.state;
        node.dataset.ready = model.ready ? 'true' : 'false';
        node.dataset.supported = model.supported ? 'true' : 'false';
        node.dataset.verified = model.verified ? 'true' : 'false';
        node.dataset.retryRemaining = String(model.retryRemaining);
        node.dataset.cancelEnabled = model.cancelEnabled ? 'true' : 'false';
        node.dataset.graphRevision = revisions.graph || '';
        node.dataset.sessionRevision = revisions.session || '';
        node.dataset.researchRevision = revisions.research || '';
        node.dataset.collaborationRevision = revisions.collaboration || '';
        node.setAttribute('role', 'status');
        const revisionLine = [
            ['Graph revision', revisions.graph],
            ['Session revision', revisions.session],
            ['Research revision', revisions.research],
            ['Collaboration revision', revisions.collaboration],
        ].filter((pair) => pair[1]).map((pair) => pair[0] + ' ' + pair[1]).join('. ');
        node.innerHTML = [
            '<p class="operation-surface__title">' + escapeOperationText(model.title) + '</p>',
            '<p class="operation-surface__detail">' + escapeOperationText(model.detail) + '</p>',
            '<p class="operation-surface__revisions">' + escapeOperationText(revisionLine || 'Current revision unavailable.') + '</p>',
            '<div class="button-row">',
            '<button type="button" data-operation-action="retry"' + (model.retryRemaining > 0 ? '' : ' disabled') + '>Retry</button>',
            '<button type="button" data-operation-action="cancel"' + (model.cancelEnabled ? '' : ' disabled') + '>Cancel</button>',
            '</div>',
        ].join('');
        return model;
    }

    function applyOperationSurface(target, record) {
        const model = classifyOperationRecord(record);
        renderOperationSurface(target, model);
        const node = typeof target === 'string' ? document.getElementById(target) : target;
        if (node) {
            node.dataset.operationRecord = JSON.stringify(record || {});
        }
        return model;
    }

    window.ComplaintOperationSurfaces = {
        retryBound: operationRetryBound,
        classify: classifyOperationRecord,
        render: renderOperationSurface,
        apply: applyOperationSurface,
    };

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', bootShell);
    } else {
        bootShell();
    }
})();
