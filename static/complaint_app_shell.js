(function () {
    const readinessStorageKey = 'complaintGenerator.uiReadiness';
    const navItems = [
        ['Landing', '/'],
        ['Account', '/home'],
        ['Chat', '/chat'],
        ['Profile', '/profile'],
        ['Results', '/results'],
        ['Workspace', '/workspace'],
        ['Review', '/claim-support-review'],
        ['Builder', '/document'],
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

    function buildSummary(payload) {
        const review = payload && payload.review ? payload.review : {};
        const overview = review.overview || {};
        const session = payload && payload.session ? payload.session : {};
        const nextQuestion = payload && payload.next_question ? payload.next_question.prompt : 'Intake complete.';
        const draft = session.draft || null;
        const draftSummary = draft && draft.title
            ? draft.title
            : (draft ? 'Draft available.' : 'No draft generated yet.');
        return {
            answeredQuestions: countAnsweredQuestions(payload),
            supportedElements: overview.supported_elements || 0,
            missingElements: overview.missing_elements || 0,
            evidenceCount: (overview.testimony_items || 0) + (overview.document_items || 0),
            nextQuestion: nextQuestion,
            draftSummary: draftSummary,
        };
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

    function renderShell(state) {
        const existing = document.getElementById('cg-app-shell');
        if (existing) {
            existing.remove();
        }

        const summary = buildSummary(state.sessionPayload);
        const shell = document.createElement('aside');
        shell.id = 'cg-app-shell';
        shell.className = 'cg-app-shell';
        shell.setAttribute('aria-label', 'Complaint Generator Application Sidebar');

        const navHtml = navItems.map(([label, href]) => {
            const active = window.location.pathname === href ? ' is-active' : '';
            return '<a class="cg-app-shell__nav-link' + active + '" href="' + href + '">' + label + '</a>';
        }).join('');
        const readiness = loadCachedReadiness();
        const readinessVerdict = readiness && readiness.verdict ? readiness.verdict : 'No UI verdict cached';
        const readinessScore = readiness && Number.isFinite(Number(readiness.score)) ? String(readiness.score) + '/100' : 'pending';
        const readinessUpdated = readiness && readiness.updated_at ? readiness.updated_at : '';
        const readinessStages = readiness && Array.isArray(readiness.tested_stages) ? readiness.tested_stages : [];
        const readinessBlockers = readiness && Array.isArray(readiness.release_blockers) ? readiness.release_blockers : [];
        const readinessTools = readiness && Array.isArray(readiness.exposed_tools) ? readiness.exposed_tools : [];
        const readinessTone = readiness && String(readiness.verdict || '').toLowerCase() === 'client-safe'
            ? ' is-good'
            : readiness
                ? ' is-warn'
                : '';

        shell.innerHTML = [
            '<div class="cg-app-shell__inner">',
            '<div class="cg-app-shell__eyebrow">Complaint Generator</div>',
            '<h2 class="cg-app-shell__title">' + safeText(findPageTitle(), 'Complaint Generator') + '</h2>',
            '<p class="cg-app-shell__copy">' + safeText(findPageDescription(), '') + '</p>',
            '<div class="cg-app-shell__status" id="cg-app-shell-status">' + safeText(state.status, 'Shell ready.') + '</div>',
            '<div class="cg-app-shell__section-title">Identity</div>',
            '<div class="cg-app-shell__chip-row">',
            '<div class="cg-app-shell__chip"><span class="cg-app-shell__chip-label">DID</span><span class="cg-app-shell__chip-value" id="cg-app-shell-did">' + safeText(state.did, 'Unavailable') + '</span></div>',
            '<div class="cg-app-shell__chip"><span class="cg-app-shell__chip-label">Tools</span><span class="cg-app-shell__chip-value">' + safeText(state.toolCount, '0') + ' MCP tools</span></div>',
            '</div>',
            '<div class="cg-app-shell__section-title">Navigate</div>',
            '<div class="cg-app-shell__nav">' + navHtml + '</div>',
            '<div class="cg-app-shell__section-title">Session</div>',
            '<div class="cg-app-shell__stats">',
            '<div class="cg-app-shell__stat"><span class="cg-app-shell__stat-label">Intake</span><span class="cg-app-shell__stat-value" id="cg-app-shell-intake-count">' + summary.answeredQuestions + '</span><span class="cg-app-shell__stat-detail">' + safeText(summary.nextQuestion, 'Intake complete.') + '</span></div>',
            '<div class="cg-app-shell__stat"><span class="cg-app-shell__stat-label">Support Review</span><span class="cg-app-shell__stat-value" id="cg-app-shell-supported-count">' + summary.supportedElements + '</span><span class="cg-app-shell__stat-detail">' + summary.missingElements + ' claim elements still need support.</span></div>',
            '<div class="cg-app-shell__stat"><span class="cg-app-shell__stat-label">Evidence</span><span class="cg-app-shell__stat-value" id="cg-app-shell-evidence-count">' + summary.evidenceCount + '</span><span class="cg-app-shell__stat-detail">' + safeText(summary.draftSummary, 'No draft generated yet.') + '</span></div>',
            '</div>',
            '<div class="cg-app-shell__section-title">UI Readiness</div>',
            '<div class="cg-app-shell__readiness' + readinessTone + '" id="cg-app-shell-readiness">',
            '<div class="cg-app-shell__readiness-header"><strong>' + safeText(readinessVerdict, 'No UI verdict cached') + '</strong><span>' + safeText(readinessScore, 'pending') + '</span></div>',
            '<div class="cg-app-shell__readiness-copy">' + safeText(readinessBlockers[0], readiness ? 'The latest actor/critic review did not return a release blocker.' : 'Run UX Audit in the workspace to cache an actor/critic verdict for the rest of the site.') + '</div>',
            '<div class="cg-app-shell__readiness-meta">' + (readinessStages.length ? ('Stages: ' + readinessStages.join(', ')) : 'Stages: not reviewed yet') + '</div>',
            '<div class="cg-app-shell__readiness-meta">' + (readinessTools.length ? ('Shared tools: ' + readinessTools.slice(0, 3).join(', ')) : 'Shared tools: not cached yet') + '</div>',
            (readinessUpdated ? '<div class="cg-app-shell__readiness-meta">Updated: ' + safeText(readinessUpdated, '') + '</div>' : ''),
            '<a class="cg-app-shell__action" href="/workspace?target_tab=ux-review">Open UX Audit</a>',
            '</div>',
            '<div class="cg-app-shell__section-title">Next Actions</div>',
            '<div class="cg-app-shell__actions">',
            '<a class="cg-app-shell__action" href="/workspace">Open Workspace</a>',
            '<a class="cg-app-shell__action" href="/document">Open Builder</a>',
            '<a class="cg-app-shell__action" href="/claim-support-review">Open Review</a>',
            '<a class="cg-app-shell__action" href="/mlwysiwyg">Edit Draft</a>',
            '</div>',
            '<div class="cg-app-shell__meta">This sidebar is backed by the same cached DID and complaint workspace session used by the CLI, MCP tools, and browser SDK.</div>',
            '</div>',
        ].join('');

        const anchor = document.querySelector('[data-surface-nav="primary"]')
            || document.querySelector('h1')
            || document.body.firstChild;
        if (anchor && anchor.parentNode) {
            anchor.parentNode.insertBefore(shell, anchor.nextSibling);
        } else {
            document.body.appendChild(shell);
        }
        window.__complaintAppShell = {
            did: state.did,
            toolCount: state.toolCount,
            sessionPayload: state.sessionPayload,
        };
    }

    async function bootShell() {
        if (document.body && document.body.dataset.complaintShell === 'off') {
            return;
        }

        let did = null;
        let toolCount = 0;
        let sessionPayload = null;
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
            status = 'Shared session loaded for ' + did + '.';
        } catch (error) {
            status = 'Shared session unavailable: ' + error.message;
        }

        renderShell({
            did: did,
            toolCount: toolCount,
            sessionPayload: sessionPayload,
            status: status,
        });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', bootShell);
    } else {
        bootShell();
    }
})();
