window.ChatPage = (function() {
    const websocketOrigin = (function() {
        if (typeof window !== 'undefined' && window.location) {
            const socketProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
            return `${socketProtocol}//${window.location.host}`;
        }
        return 'ws://localhost:19030';
    })();
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

    function parseJsonLike(value, fallback) {
        if (value === null || value === undefined || value === '') {
            return fallback;
        }
        if (typeof value === 'object') {
            return value;
        }
        if (typeof value !== 'string') {
            return fallback;
        }
        try {
            return JSON.parse(value);
        } catch (error) {
            return fallback;
        }
    }

    function stringValue(value) {
        return String(value || '').trim();
    }

    function normalizeChatContext(rawContext) {
        const context = parseJsonLike(rawContext, null);
        if (!context || typeof context !== 'object') {
            return null;
        }
        const filing = context.filing && typeof context.filing === 'object' ? context.filing : {};
        const labels = Array.isArray(context.labels)
            ? context.labels
            : (Array.isArray(filing.labels) ? filing.labels : []);
        return {
            kind: stringValue(context.kind || context.type || 'workspace-handoff'),
            sourceSurface: stringValue(context.source_surface || context.sourceSurface || context.source || ''),
            routerMode: stringValue(context.router_mode || context.routerMode || ''),
            status: stringValue(context.status || ''),
            filing: {
                id: stringValue(filing.id || filing.document_id || filing.documentId || context.filing_id || context.document_id || context.docket_item_id),
                title: stringValue(filing.title || filing.document_title || filing.documentTitle || context.filing_title || context.document_title || context.title),
                date: stringValue(filing.date || filing.date_filed || filing.dateFiled || context.filing_date),
                use: stringValue(filing.use || filing.suggested_use || filing.suggestedUse || context.suggested_use || context.document_type),
                source: stringValue(filing.source || filing.source_ref || filing.sourceRef || context.source || context.source_ref),
                documentType: stringValue(filing.document_type || filing.documentType || context.document_type || context.type),
            },
            labels: labels.map((label) => stringValue(label)).filter(Boolean).slice(0, 8),
            note: stringValue(context.note || context.annotation_note || context.annotationNote || ''),
            excerpt: stringValue(context.excerpt || context.summary || context.preview || '').slice(0, 600),
        };
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
        const chatContext = normalizeChatContext(params.get('chat_context'));
        if (!(source || userId || caseSynopsis || prefillMessage || returnTo)) {
            try {
                const cached = window.localStorage.getItem('complaintWorkspaceHandoff');
                if (!cached) {
                    return null;
                }
                const payload = JSON.parse(cached);
                if (!payload || typeof payload !== 'object') {
                    return null;
                }
                return {
                    source: String(payload.source || '').trim(),
                    userId: String(payload.userId || '').trim(),
                    caseSynopsis: String(payload.caseSynopsis || '').trim(),
                    prefillMessage: String(payload.prefillMessage || '').trim(),
                    returnTo: String(payload.returnTo || '').trim(),
                    chatContext: normalizeChatContext(payload.chatContext || payload.chat_context),
                };
            } catch (error) {
                return null;
            }
        }
        return {
            source,
            userId,
            caseSynopsis,
            prefillMessage,
            returnTo,
            chatContext,
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

    function setTextForId(id, text) {
        const node = document.getElementById(id);
        if (node) {
            node.textContent = text;
        }
    }

    function getCurrentLinks() {
        return {
            workspace: (document.getElementById('chat-open-workspace') || {}).href || '/workspace',
            review: (document.getElementById('chat-open-review') || {}).href || '/claim-support-review',
            builder: (document.getElementById('chat-open-builder') || {}).href || '/document',
        };
    }

    function setStageItemState(id, status, isCurrent) {
        const item = document.getElementById(id);
        if (!item) {
            return;
        }
        item.classList.toggle('is-current', Boolean(isCurrent));
        const statusNode = item.querySelector('.stage-status');
        if (statusNode) {
            statusNode.textContent = status;
        }
    }

    function describeChatStage(handoff, chatContext) {
        const filing = chatContext && chatContext.filing ? chatContext.filing : {};
        const stageText = `${(handoff && handoff.source) || ''} ${(chatContext && chatContext.kind) || ''} ${(chatContext && chatContext.sourceSurface) || ''}`;
        if (filing.title || filing.id || /docket|filing|evidence|annotation|document/i.test(stageText)) {
            return 'evidence';
        }
        if (/review|support/i.test(stageText)) {
            return 'review';
        }
        if (/draft|builder|pleading/i.test(stageText)) {
            return 'draft';
        }
        return 'intake';
    }

    function updateActiveContextStrip(handoff, chatContext, stage) {
        const strip = document.getElementById('chat-active-context-strip');
        if (!strip) {
            return;
        }
        const filing = chatContext && chatContext.filing ? chatContext.filing : {};
        const hasHandoff = Boolean(handoff);
        const modeLabels = {
            intake: 'Intake',
            evidence: 'Filing',
            review: 'Review',
            draft: 'Draft',
        };
        const title = stage === 'evidence'
            ? (filing.title || filing.id || 'Selected filing attached')
            : (stage === 'review'
                ? 'Review context attached'
                : (stage === 'draft' ? 'Drafting context attached' : 'Complaint intake active'));
        const details = [];
        if (filing.date) {
            details.push(`Filed or dated ${filing.date}.`);
        }
        if (filing.use) {
            details.push(`Suggested use: ${filing.use}.`);
        }
        if (handoff && handoff.userId) {
            details.push(`Complaint session ${handoff.userId}.`);
        }
        if (stage === 'intake' && (!details.length || !hasHandoff)) {
            details.push('Messages can be carried into review, evidence organization, or drafting.');
        }
        setTextForId('chat-active-context-mode', modeLabels[stage] || 'Context');
        setTextForId('chat-active-context-title', title);
        setTextForId('chat-active-context-detail', details.join(' ') || 'The selected complaint context will stay attached to this conversation.');
        const fields = document.getElementById('chat-active-context-fields');
        if (fields) {
            const hasFiling = Boolean(filing.title || filing.id);
            setTextForId('chat-context-field-filing', filing.title || filing.id || 'none selected');
            setTextForId('chat-context-field-date', filing.date || 'not found');
            setTextForId('chat-context-field-use', filing.use || 'not classified');
            setTextForId('chat-context-field-router', stage === 'evidence' ? 'document-aware Q&A' : 'general intake');
            fields.hidden = !hasFiling;
        }
        strip.hidden = false;
    }

    function updateComposerReadiness(handoff, chatContext) {
        const input = document.querySelector('#chat-form input');
        const sendButton = document.getElementById('send');
        const readiness = document.getElementById('chat-composer-readiness');
        if (!input || !sendButton || !readiness) {
            return;
        }
        const filing = chatContext && chatContext.filing ? chatContext.filing : {};
        const stage = describeChatStage(handoff, chatContext);
        const hasText = Boolean(input.value.trim());
        const hasFiling = Boolean(filing.title || filing.id);
        sendButton.disabled = !hasText;
        sendButton.setAttribute('aria-disabled', hasText ? 'false' : 'true');
        if (!hasText) {
            readiness.textContent = stage === 'evidence' && hasFiling
                ? 'Ready: selected filing context is attached. Type a question to enable Send.'
                : 'Type a question or fact to send. General intake context is active.';
            readiness.classList.toggle('is-ready', false);
            readiness.classList.toggle('is-warning', true);
            return;
        }
        readiness.textContent = stage === 'evidence' && hasFiling
            ? 'Ready to send with the selected filing attached to the router request.'
            : 'Ready to send as part of the current complaint intake session.';
        readiness.classList.toggle('is-ready', true);
        readiness.classList.toggle('is-warning', false);
    }

    function truncateForPreview(value, maxLength) {
        const text = String(value || '').replace(/\s+/g, ' ').trim();
        const limit = maxLength || 220;
        if (text.length <= limit) {
            return text;
        }
        return `${text.slice(0, limit - 3)}...`;
    }

    function updateGroundingPreview(handoff, chatContext) {
        const preview = document.getElementById('chat-grounding-preview');
        if (!preview) {
            return;
        }
        const filing = chatContext && chatContext.filing ? chatContext.filing : {};
        const hasFiling = Boolean(filing.title || filing.id);
        const routerMode = String(
            (chatContext && (chatContext.routerMode || chatContext.router_mode))
            || (hasFiling ? 'multimodal_router / llm_router' : 'llm_router')
        ).trim();
        const sourceSurface = String(
            (chatContext && (chatContext.sourceSurface || chatContext.source_surface))
            || (handoff && handoff.source)
            || 'workspace handoff'
        ).trim();
        const labels = chatContext && Array.isArray(chatContext.labels) ? chatContext.labels.filter(Boolean) : [];
        const excerpt = truncateForPreview(
            (chatContext && chatContext.excerpt)
            || filing.excerpt
            || filing.summary
            || filing.text
            || filing.preview
            || ''
        );
        setTextForId('chat-grounding-route', hasFiling ? routerMode : 'general intake');
        setTextForId('chat-grounding-document', filing.title || filing.id || 'none selected');
        setTextForId('chat-grounding-labels', labels.length ? labels.join(', ') : (filing.use || 'none'));
        setTextForId(
            'chat-grounding-route-rationale',
            hasFiling
                ? 'Use document-aware routing because a filing is attached'
                : 'Use intake routing because no filing is selected'
        );
        setTextForId('chat-grounding-source', sourceSurface || 'workspace handoff');
        setTextForId(
            'chat-grounding-excerpt',
            excerpt
                ? `Passage preview: ${excerpt}`
                : (hasFiling
                    ? 'This selected filing will be attached to the next router request. No passage excerpt was provided.'
                    : 'Select a filing from the dashboard to preview the passage or summary that will guide the next answer.')
        );
        const returnTarget = (handoff && handoff.returnTo) || '/dashboards#docket-dataset-parquet-dashboard';
        const changeLink = document.getElementById('chat-grounding-change-link');
        const returnLink = document.getElementById('chat-grounding-return-link');
        if (changeLink) {
            changeLink.href = returnTarget.includes('#') ? returnTarget : `${returnTarget}#docket-dataset-parquet-dashboard`;
        }
        if (returnLink) {
            returnLink.href = returnTarget;
        }
        preview.hidden = !hasFiling;
    }

    function updateSelectedFilingHero(handoff, chatContext) {
        const hero = document.getElementById('chat-selected-filing-hero');
        if (!hero) {
            return;
        }
        const filing = chatContext && chatContext.filing ? chatContext.filing : {};
        const hasFiling = Boolean(filing.title || filing.id);
        document.body.classList.toggle('has-selected-filing-chat', hasFiling);
        hero.hidden = !hasFiling;
        if (!hasFiling) {
            return;
        }
        const routerMode = String(
            (chatContext && (chatContext.routerMode || chatContext.router_mode))
            || 'llm_router / multimodal_router'
        ).trim();
        const returnTarget = (handoff && handoff.returnTo) || '/workspace?target_tab=docket';
        const preparedQuestion = String((handoff && handoff.prefillMessage) || '').trim()
            || `Ask what this document affects and whether it supports the complaint: ${filing.title || filing.id}`;
        setTextForId('chat-selected-filing-badge', 'Selected filing attached');
        setTextForId('chat-selected-filing-title', filing.title || filing.id || 'Selected filing attached');
        setTextForId(
            'chat-selected-filing-detail',
            `Chat will answer with this ${filing.documentType || filing.use || 'document'} in scope. Source: ${filing.source || 'workspace handoff'}.`
        );
        setTextForId('chat-selected-filing-question', `Prepared question: ${preparedQuestion}`);
        setTextForId('chat-selected-filing-source', filing.source || 'workspace handoff');
        setTextForId('chat-selected-filing-type', filing.documentType || filing.use || 'document');
        setTextForId('chat-selected-filing-scope', routerMode);
        setTextForId('chat-selected-filing-persistence', 'Draft only: nothing is saved as a label, annotation, deadline, or answer until you confirm it back in Docket.');
        const returnLink = document.getElementById('chat-selected-filing-return-link');
        if (returnLink) {
            returnLink.href = returnTarget;
        }
        const askLink = document.getElementById('chat-selected-filing-ask-link');
        if (askLink) {
            askLink.href = '#chat-form';
        }
    }

    function updateStageRail(handoff, chatContext) {
        const stage = describeChatStage(handoff, chatContext);
        const links = getCurrentLinks();
        const primary = document.getElementById('chat-primary-next-action');
        const stageCopy = {
            intake: {
                label: 'Current step',
                title: 'Continue intake questioning',
                detail: 'Use the chat to clarify facts, people, dates, harms, and missing proof before moving to review or drafting.',
                action: 'Ask the next intake question',
                href: '#chat-form',
            },
            evidence: {
                label: 'Selected filing',
                title: 'Ask about this document',
                detail: 'Use the attached docket or evidence context to label the document, identify important facts, and decide how it supports the complaint.',
                action: 'Ask about selected filing',
                href: '#chat-form',
            },
            review: {
                label: 'Support review',
                title: 'Check legal support',
                detail: 'Move from narrative collection into element-by-element review once the key facts and proof are organized.',
                action: 'Open support review',
                href: links.review,
            },
            draft: {
                label: 'Drafting',
                title: 'Build the complaint draft',
                detail: 'Use the draft builder after the record has enough facts, evidence labels, and reviewed legal support.',
                action: 'Open draft builder',
                href: links.builder,
            },
        };
        const copy = stageCopy[stage] || stageCopy.intake;
        setTextForId('chat-stage-label', copy.label);
        setTextForId('chat-stage-title', copy.title);
        setTextForId('chat-stage-detail', copy.detail);
        if (primary) {
            primary.textContent = copy.action;
            primary.href = copy.href;
        }

        setStageItemState('chat-stage-intake', stage === 'intake' ? 'Current' : 'Done', stage === 'intake');
        setStageItemState('chat-stage-evidence', stage === 'evidence' ? 'Current' : (stage === 'intake' ? 'Next' : 'Done'), stage === 'evidence');
        setStageItemState('chat-stage-review', stage === 'review' ? 'Current' : (stage === 'draft' ? 'Done' : 'Later'), stage === 'review');
        setStageItemState('chat-stage-draft', stage === 'draft' ? 'Current' : 'Later', stage === 'draft');
        updateActiveContextStrip(handoff, chatContext, stage);
        updateGroundingPreview(handoff, chatContext);
        updateSelectedFilingHero(handoff, chatContext);
        updateComposerReadiness(handoff, chatContext);
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
        if (handoff && handoff.chatContext) {
            chatParams.set('chat_context', JSON.stringify(handoff.chatContext));
        }
        return chatParams.toString() ? `/chat?${chatParams.toString()}` : '/chat';
    }

    function updateRouterStatus(message, visible) {
        const node = document.getElementById('chat-router-status');
        if (!node) {
            return;
        }
        if (message) {
            node.textContent = message;
        }
        node.classList.toggle('is-visible', Boolean(visible || message));
    }

    function applyWorkspaceHandoff() {
        const handoff = readWorkspaceHandoff();
        updateChatNextStepLinks(handoff);
        if (!handoff) {
            updateStageRail(null, null);
            return;
        }

        const contextCard = document.getElementById('chat-context-card');
        const contextSummary = document.getElementById('chat-context-summary');
        const contextPrefill = document.getElementById('chat-context-prefill');
        const contextTitle = document.getElementById('chat-context-title');
        const intakeDenoiseCard = document.getElementById('chat-intake-denoise-card');
        const returnLink = document.getElementById('chat-context-return-link');
        const input = document.querySelector('#chat-form input');
        if (!contextCard || !contextSummary || !contextPrefill || !returnLink || !input) {
            return;
        }

        const chatContext = normalizeChatContext(handoff.chatContext);
        const filing = chatContext && chatContext.filing ? chatContext.filing : {};
        const isIntakeDenoising = Boolean(
            (chatContext && /intake|denois|question/i.test(`${chatContext.kind} ${chatContext.sourceSurface}`))
            || /intake|denois|question/i.test(String(handoff.source || ''))
        );
        const isFilingContext = Boolean(filing.title || filing.id || /docket|filing/i.test(String(handoff.source || '')));
        if (contextTitle) {
            contextTitle.textContent = isIntakeDenoising
                ? 'Intake question plan'
                : (isFilingContext ? 'Active filing context' : 'Workspace handoff');
        }
        contextCard.classList.toggle('is-secondary-context', Boolean(isFilingContext));
        if (intakeDenoiseCard) {
            intakeDenoiseCard.hidden = !isIntakeDenoising;
        }
        const summaryParts = [];
        if (isIntakeDenoising) {
            summaryParts.push('Intake mode: the chat should ask targeted questions that clarify the legal basis, facts, evidence, dates, harms, and remedies.');
        }
        if (filing.title || filing.id) {
            summaryParts.push(`Active filing: ${filing.title || filing.id}.`);
        }
        if (filing.date) {
            summaryParts.push(`Date found: ${filing.date}.`);
        }
        if (filing.use) {
            summaryParts.push(`Suggested use: ${filing.use}.`);
        }
        if (handoff.userId) {
            summaryParts.push(`Shared complaint session: ${handoff.userId}.`);
        }
        if (handoff.caseSynopsis) {
            summaryParts.push(handoff.caseSynopsis);
        }
        contextSummary.textContent = summaryParts.join(' ') || 'Chat was opened from the workspace with the shared complaint context.';
        const contextDetails = [];
        if (chatContext && chatContext.labels && chatContext.labels.length) {
            contextDetails.push(`Labels: ${chatContext.labels.join(', ')}.`);
        }
        const routerMode = chatContext && (chatContext.routerMode || chatContext.router_mode);
        if (routerMode) {
            contextDetails.push(`Analysis route: ${routerMode}.`);
        }
        if (chatContext && chatContext.excerpt) {
            contextDetails.push(`Excerpt: ${chatContext.excerpt}`);
        }
        contextPrefill.textContent = [
            handoff.prefillMessage ? `Prepared question: ${handoff.prefillMessage}` : 'Use this chat to turn the current case framing into cleaner testimony and follow-up questions.',
            contextDetails.join(' '),
        ].filter(Boolean).join(' ');
        returnLink.href = handoff.returnTo || '/workspace';
        if (handoff.prefillMessage && !input.value.trim()) {
            input.value = handoff.prefillMessage;
        }
        updateRouterStatus(
            isIntakeDenoising
                ? 'Ready to ask targeted intake questions. Your answers stay attached to this complaint session.'
                : (isFilingContext ? 'Ready to answer questions with the selected filing context attached.' : 'Chat context is attached.'),
            true
        );
        updateStageRail(handoff, chatContext);
        contextCard.hidden = false;
    }

	    function initialize() {
	        let cookies = "";
	        $("body").css("background-color", "transparent");
	        const activeHandoff = readWorkspaceHandoff();
	        applyWorkspaceHandoff();
        $.ajax({
            url: "/cookies",
            type: "get",
            async: false,
            data: {},
            success: function(data) {
                cookies = data;
            }
        });

        const parsedCookies = parseJsonLike(cookies, {});
        const hashedUsername = stringValue(parsedCookies["hashed_username"]);
        const hashedPassword = stringValue(parsedCookies["hashed_password"]);
        const profile = loadProfile(hashedUsername, hashedPassword);
        let testdata = (profile && profile["data"]) || {};
        const parent = $("#messages");

        testdata = parseJsonLike(testdata, {});

        const chatHistory = testdata["chat_history"] || {};

        for (const timestamp in chatHistory) {
            renderMessage(parent, chatHistory[timestamp], hashedUsername);
        }

        let socket = null;
        let socketReady = false;
        let lastOptimisticMessage = null;

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
	                    user_id: getActiveComplaintUserId(activeHandoff),
	                    source: (activeHandoff && activeHandoff.source) || '',
	                    chat_context: (activeHandoff && activeHandoff.chatContext) || null,
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
	                if (/timeout|fallback|backup|context.*attached|context.*preserved/i.test(String((entry && entry.message) || ''))) {
	                    updateRouterStatus('The router was slow, so backup chat responded. Your selected context is still attached.', true);
	                }
	                renderMessage(parent, entry, hashedUsername);
	            });
	        }

        try {
            socket = new WebSocket(websocketOrigin + "/api/chat");
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
                if (
                    lastOptimisticMessage
                    && String(data && data.sender || '').trim() === String(lastOptimisticMessage.sender || '').trim()
                    && String(data && data.message || '').trim() === String(lastOptimisticMessage.message || '').trim()
                ) {
                    lastOptimisticMessage = null;
                    return;
                }
	                if (/timeout|fallback|backup|context.*attached|context.*preserved/i.test(String((data && data.message) || ''))) {
	                    updateRouterStatus('The router was slow, so backup chat responded. Your selected context is still attached.', true);
	                }
	                renderMessage(parent, data, hashedUsername);
	            };
	        } catch (error) {
	            socketReady = false;
        }

            $("#chat-form").on("submit", async function(e) {
            e.preventDefault();
            const inputNode = document.querySelector('#chat-form input');
            const message = inputNode ? inputNode.value.trim() : "";
            if (message) {
                try {
                    if (socket && socketReady && socket.readyState === WebSocket.OPEN) {
	                        const data = {
	                            "sender": hashedUsername,
	                            "message": message,
	                            "user_id": getActiveComplaintUserId(activeHandoff),
	                            "source": (activeHandoff && activeHandoff.source) || '',
	                            "chat_context": (activeHandoff && activeHandoff.chatContext) || null
	                        };
                        lastOptimisticMessage = data;
                        renderMessage(parent, data, hashedUsername);
                        socket.send(JSON.stringify(data));
                    } else {
                        await sendViaFallback(message);
                    }
                    if (inputNode) {
                        inputNode.value = "";
                        updateComposerReadiness(activeHandoff, normalizeChatContext(activeHandoff && activeHandoff.chatContext));
                    }
                } catch (error) {
                    showError(error && error.message ? error.message : "Unable to submit the chat message.");
                }
            }
            });

	        const composerInput = document.querySelector('#chat-form input');
	        if (composerInput) {
	            composerInput.addEventListener('input', () => {
	                updateComposerReadiness(activeHandoff, normalizeChatContext(activeHandoff && activeHandoff.chatContext));
	            });
	            updateComposerReadiness(activeHandoff, normalizeChatContext(activeHandoff && activeHandoff.chatContext));
	        }

	        document.querySelectorAll('[data-chat-prompt]').forEach((button) => {
	            button.addEventListener('click', () => {
	                const prompt = String(button.getAttribute('data-chat-prompt') || '').trim();
	                const input = document.querySelector('#chat-form input');
	                if (prompt && input) {
	                    input.value = prompt;
	                    updateComposerReadiness(activeHandoff, normalizeChatContext(activeHandoff && activeHandoff.chatContext));
	                    input.focus();
	                }
	            });
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
