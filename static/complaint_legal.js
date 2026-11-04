/* Legal context questions and separated source decisions.
   Discovery uses the case legal-context route, which calls the Dataset
   corpus lookup. Custody, review, applicability, and governing law are
   rendered from that response and are not inferred from snippets. */
(function () {
    var client = null;
    var reviewedPassageId = '';

    function questionsNode() {
        return document.getElementById('legal-context-questions');
    }

    function renderQuestions(questions) {
        var list = questionsNode();
        if (!list) return;
        list.replaceChildren();
        (Array.isArray(questions) ? questions : []).forEach(function (item) {
            var row = document.createElement('li');
            row.dataset.questionId = item.question_id || '';
            row.dataset.field = item.field || '';
            row.textContent = item.prompt || '';
            list.appendChild(row);
        });
    }

    function caseId() {
        var node = document.getElementById('legal-context-case-id');
        return node ? node.value.trim() : '';
    }

    function cacheBody() {
        var raw = document.getElementById('legal-source-flow-cache').value.trim();
        if (!raw) return {};
        return JSON.parse(raw);
    }

    function requestBody(extra) {
        var body = {
            query: document.getElementById('legal-source-flow-query').value.trim(),
            offline_cache: cacheBody(),
            review_passage_id: reviewedPassageId,
            review_decision: reviewedPassageId ? 'admit' : '',
            applicability_decision: document.getElementById('legal-source-flow-applicability-choice').value,
            governing_law_passage_id: '',
            governing_law_text: ''
        };
        Object.keys(extra || {}).forEach(function (key) { body[key] = extra[key]; });
        return body;
    }

    function renderFlow(payload) {
        var status = document.getElementById('legal-source-flow-status');
        var decisions = payload.decisions || {};
        status.dataset.status = payload.status || 'unavailable';
        status.dataset.tool = payload.tool || '';
        status.dataset.governingLawDefaulted = 'false';
        status.textContent = payload.status === 'questions_open'
            ? 'Jurisdiction, forum, and relevant dates are still open. No source search has run.'
            : 'Source tool ' + (payload.tool || 'unavailable') + '. Status ' + (payload.status || 'unavailable') + '.';
        renderQuestions(payload.questions || []);
        var discovery = document.getElementById('legal-source-flow-discovery');
        discovery.replaceChildren();
        (decisions.discovery || []).forEach(function (item) {
            var row = document.createElement('p');
            row.dataset.decision = 'discovery';
            row.dataset.kind = item.kind || '';
            row.dataset.admittedLaw = 'false';
            row.dataset.passageId = item.passage_id || '';
            row.textContent = (item.kind || 'gap') + ' admitted_law=false ' + (item.passage_id || item.snippet || item.model_text || '');
            discovery.appendChild(row);
        });
        var custody = document.getElementById('legal-source-flow-custody');
        custody.replaceChildren();
        (decisions.custody || []).forEach(function (item) {
            var label = document.createElement('label');
            var input = document.createElement('input');
            input.type = 'radio';
            input.name = 'legal-source-custody';
            input.value = item.passage_id || '';
            input.dataset.passageId = item.passage_id || '';
            label.appendChild(input);
            label.appendChild(document.createTextNode(' Custodied passage ' + (item.passage_id || '')));
            var row = document.createElement('p');
            row.dataset.decision = 'custody';
            row.dataset.admittedLaw = 'false';
            row.dataset.passageId = item.passage_id || '';
            row.appendChild(label);
            custody.appendChild(row);
        });
        var review = decisions.review_admission || {};
        var reviewNode = document.getElementById('legal-source-flow-review');
        reviewNode.dataset.admittedLaw = review.admitted_law === true ? 'true' : 'false';
        reviewNode.dataset.passageId = review.passage_id || '';
        reviewNode.dataset.reason = review.reason || '';
        reviewNode.textContent = 'Review ' + (review.reason || 'not_reviewed')
            + '. Admitted law: ' + (review.admitted_law === true ? 'true' : 'false')
            + '. Passage ' + (review.passage_id || 'none') + '.';
        var applicability = decisions.applicability || {};
        var applicabilityNode = document.getElementById('legal-source-flow-applicability');
        applicabilityNode.dataset.value = applicability.value || 'unknown';
        applicabilityNode.dataset.admittedLaw = 'false';
        var governing = decisions.governing_law || {};
        var governingNode = document.getElementById('legal-source-flow-governing');
        governingNode.dataset.admittedAuthority = governing.admitted_authority === true ? 'true' : 'false';
        governingNode.dataset.defaulted = 'false';
        governingNode.dataset.reason = governing.reason || '';
        governingNode.dataset.passageId = governing.passage_id || '';
    }

    function showFailure(message) {
        var status = document.getElementById('legal-source-flow-status');
        status.dataset.status = 'unavailable';
        status.dataset.governingLawDefaulted = 'false';
        status.textContent = message;
    }

    async function postFlow(extra) {
        var id = caseId();
        if (!id || !client) {
            showFailure('Select a case before searching. Nothing was admitted.');
            return;
        }
        try {
            var payload = await client._request('/api/legal-context/' + encodeURIComponent(id) + '/source-flow', {
                method: 'POST',
                body: JSON.stringify(requestBody(extra))
            });
            if (payload && payload.decisions && payload.decisions.review_admission && payload.decisions.review_admission.admitted_law === true) {
                reviewedPassageId = payload.decisions.review_admission.passage_id || '';
            }
            renderFlow(payload);
        } catch (error) {
            showFailure('Source search or review was refused. Nothing was admitted.');
        }
    }

    function install(bound) {
        client = bound || window.workspaceClient;
        var search = document.getElementById('legal-source-flow-search');
        if (!search || search.dataset.bound === 'true') return;
        search.dataset.bound = 'true';
        search.addEventListener('click', function () {
            reviewedPassageId = '';
            postFlow({review_decision: '', review_passage_id: '', applicability_decision: 'unknown', governing_law_passage_id: '', governing_law_text: ''});
        });
        document.getElementById('legal-source-flow-review-admit').addEventListener('click', function () {
            var selected = document.querySelector('input[name="legal-source-custody"]:checked');
            reviewedPassageId = selected ? selected.value : 'snippet-not-a-passage';
            postFlow({review_decision: 'admit', review_passage_id: reviewedPassageId, governing_law_passage_id: '', governing_law_text: ''});
        });
        document.getElementById('legal-source-flow-applicability-save').addEventListener('click', function () {
            postFlow({governing_law_passage_id: '', governing_law_text: ''});
        });
        document.getElementById('legal-source-flow-governing-save').addEventListener('click', function () {
            postFlow({
                governing_law_passage_id: document.getElementById('legal-source-flow-governing-passage').value.trim(),
                governing_law_text: document.getElementById('legal-source-flow-governing-text').value.trim()
            });
        });
        bindProvenance();
    }

    var provenance = {requirements: [], links: [], facts: [], evidence: [], suggestions: [], contradictions: [], selected: '', submittedFacts: [], binding: null};

    function text(value) {
        return value === undefined || value === null ? '' : String(value);
    }

    function provenanceRoot() {
        return document.getElementById('legal-provenance');
    }

    function clearList(id) {
        var node = document.getElementById(id);
        if (node) node.replaceChildren();
        return node;
    }

    function note(list, role, message, extra) {
        if (!list) return;
        var item = document.createElement('li');
        item.className = 'legal-provenance-note';
        item.dataset.role = role;
        item.dataset.present = 'true';
        Object.keys(extra || {}).forEach(function (key) { item.dataset[key] = extra[key]; });
        item.textContent = message;
        list.appendChild(item);
    }

    function paintProvenanceState(name, message) {
        var host = provenanceRoot();
        if (!host) return;
        host.dataset.state = name;
        host.dataset.loaded = 'true';
        var status = document.getElementById('legal-provenance-status');
        if (status) {
            status.dataset.status = name;
            status.textContent = message;
        }
        ['legal-provenance-empty', 'legal-provenance-error', 'legal-provenance-locked'].forEach(function (id) {
            var node = document.getElementById(id);
            if (!node) return;
            var show = (id === 'legal-provenance-empty' && name === 'empty')
                || (id === 'legal-provenance-error' && (name === 'error' || name === 'unavailable' || name === 'conflict'))
                || (id === 'legal-provenance-locked' && name === 'locked');
            node.hidden = !show;
        });
    }

    function setLabel(id, message, attrs) {
        var node = document.getElementById(id);
        if (!node) return;
        node.textContent = message;
        Object.keys(attrs || {}).forEach(function (key) { node.dataset[key] = attrs[key]; });
    }

    function spanOf(item) {
        var provenanceRow = item && item.source_provenance && typeof item.source_provenance === 'object' ? item.source_provenance : {};
        var span = provenanceRow.source_span && typeof provenanceRow.source_span === 'object' ? provenanceRow.source_span : (item && item.source_span && typeof item.source_span === 'object' ? item.source_span : {});
        return {text: text(span.text), start: text(span.start), end: text(span.end), verified: provenanceRow.verified === true};
    }

    function renderLabels(requirement) {
        var admitted = requirement && requirement.admitted_law === true;
        setLabel('legal-provenance-admission', admitted
            ? 'Source admission: this requirement is admitted law from passage ' + text(requirement.passage_id) + '.'
            : 'Source admission: this row is not admitted law.',
            {admittedLaw: admitted ? 'true' : 'false', label: 'source-admission'});
        var suggestions = provenance.suggestions;
        setLabel('legal-provenance-suggestion', suggestions.length
            ? 'AI suggestion: ' + suggestions.length + ' recorded. None of them is admitted law or legal sufficiency.'
            : 'AI suggestion: none is recorded. A suggestion is not admitted law.',
            {admittedLaw: 'false', present: suggestions.length ? 'true' : 'false', label: 'ai-suggestion'});
        var sufficient = requirement && requirement.legal_sufficiency === true;
        setLabel('legal-provenance-sufficiency', sufficient
            ? 'Legal sufficiency: the current record says this requirement is legally sufficient.'
            : 'Legal sufficiency: not established. Admission and support are not sufficiency.',
            {legalSufficiency: sufficient ? 'true' : 'false', label: 'legal-sufficiency'});
        var support = document.getElementById('legal-provenance-support');
        if (support) {
            var state = requirement ? text(requirement.support_state || 'unknown') : 'unknown';
            support.dataset.supportState = state;
            support.dataset.label = 'support';
            support.textContent = requirement ? 'Support: ' + state + '.' : 'Support has not been read.';
        }
    }

    function fillStep(id, label, filled) {
        var button = document.getElementById(id);
        if (!button) return;
        button.textContent = label;
        button.disabled = !filled;
        button.dataset.filled = filled ? 'true' : 'false';
    }

    function selectRequirement(requirementId) {
        provenance.selected = requirementId;
        var requirement = provenance.requirements.filter(function (item) { return item.id === requirementId; })[0];
        document.querySelectorAll('#legal-provenance-requirements [data-role="requirement"]').forEach(function (button) {
            button.setAttribute('aria-pressed', button.dataset.requirementId === requirementId ? 'true' : 'false');
        });
        var passage = document.getElementById('legal-provenance-passage');
        if (!requirement) {
            if (passage) passage.textContent = '';
            fillStep('legal-provenance-step-requirement', 'Requirement', false);
            fillStep('legal-provenance-step-passage', 'Law passage', false);
            fillStep('legal-provenance-step-assertion', 'Factual assertion', false);
            fillStep('legal-provenance-step-evidence', 'Evidence span', false);
            renderLabels(null);
            return;
        }
        renderLabels(requirement);
        fillStep('legal-provenance-step-requirement', requirement.name || 'Requirement', true);
        var passageText = text(requirement.rule_text || requirement.description);
        if (passage) {
            passage.dataset.role = 'law-passage-text';
            passage.dataset.passageId = text(requirement.passage_id);
            passage.dataset.admittedLaw = requirement.admitted_law === true ? 'true' : 'false';
            passage.textContent = passageText ? passageText : 'The admitted passage text is missing.';
        }
        fillStep('legal-provenance-step-passage', passageText ? 'Law passage' : 'Law passage missing', Boolean(passageText));
        var linked = linkedAssertions(requirement);
        var evidence = linked.length ? evidenceFor(linked[0]) : [];
        fillStep('legal-provenance-step-assertion', linked.length ? 'Factual assertion' : 'Factual assertion missing', linked.length > 0);
        fillStep('legal-provenance-step-evidence', evidence.length ? 'Evidence span' : 'Evidence span missing', evidence.length > 0);
        renderAssertions(linked, requirement);
        renderEvidence(evidence, requirement);
    }

    function linkedAssertions(requirement) {
        var support = Array.isArray(requirement.fact_support) ? requirement.fact_support : [];
        var ids = {};
        support.forEach(function (item) { if (item && item.fact_id) ids[item.fact_id] = true; });
        provenance.submittedFacts.forEach(function (fact) {
            if (ids[fact.id] && !provenance.facts.some(function (item) { return item.id === fact.id; })) {
                provenance.facts.push({id: fact.id, entityId: '', text: fact.text, span: '', adopted: false, origin: 'requirement-support'});
            }
        });
        var fromGraph = provenance.facts.filter(function (fact) {
            return ids[fact.id] || ids[fact.entityId] || (fact.text && requirement.rule_text && sharesWord(fact.text, requirement.rule_text));
        });
        if (fromGraph.length) return fromGraph;
        return support.map(function (item) {
            return {id: text(item.fact_id), text: text(item.fact_id), entityId: '', span: '', adopted: false, origin: 'requirement-support', overlap: item.overlap || []};
        }).filter(function (item) { return item.id; });
    }

    function sharesWord(left, right) {
        var words = {};
        text(right).toLowerCase().split(/\s+/).forEach(function (word) {
            var clean = word.replace(/[^a-z0-9]/g, '');
            if (clean.length > 4) words[clean] = true;
        });
        return text(left).toLowerCase().split(/\s+/).some(function (word) {
            return words[word.replace(/[^a-z0-9]/g, '')];
        });
    }

    function evidenceFor(assertion) {
        var rows = provenance.evidence.filter(function (item) {
            return item.text && (item.adopted || item.assertionId === assertion.id || sharesWord(item.text, assertion.text));
        });
        if (rows.length) return rows;
        if (assertion.span) return [{id: assertion.id + '-span', text: assertion.span, adopted: assertion.adopted === true, start: assertion.spanStart, end: assertion.spanEnd}];
        var related = provenance.facts.filter(function (fact) {
            return fact.span && fact.text && sharesWord(fact.text, assertion.text);
        });
        return related.map(function (fact) {
            return {id: fact.id + '-span', text: fact.span, adopted: false, start: fact.spanStart, end: fact.spanEnd};
        });
    }

    function renderAssertions(rows, requirement) {
        var list = clearList('legal-provenance-assertions');
        if (!list) return;
        if (!rows.length) {
            note(list, 'missing-input', 'No factual assertion is linked to this requirement.', {missing: 'factual-assertion', requirementId: requirement ? requirement.id : ''});
            return;
        }
        rows.forEach(function (row) {
            var button = document.createElement('button');
            button.type = 'button';
            button.className = 'legal-provenance-assertion';
            button.dataset.role = 'factual-assertion';
            button.dataset.factId = row.id;
            button.dataset.graphKind = 'factual';
            button.dataset.admittedLaw = 'false';
            button.dataset.origin = row.origin || 'factual-graph';
            button.setAttribute('aria-pressed', 'false');
            button.textContent = row.text || row.id;
            button.addEventListener('click', function () {
                document.querySelectorAll('#legal-provenance-assertions [data-role="factual-assertion"]').forEach(function (item) {
                    item.setAttribute('aria-pressed', item === button ? 'true' : 'false');
                });
                var evidence = evidenceFor(row);
                fillStep('legal-provenance-step-assertion', 'Factual assertion', true);
                fillStep('legal-provenance-step-evidence', evidence.length ? 'Evidence span' : 'Evidence span missing', evidence.length > 0);
                renderEvidence(evidence, requirement);
                var step = document.getElementById('legal-provenance-step-assertion');
                if (step) step.setAttribute('aria-current', 'step');
            });
            var item = document.createElement('li');
            item.appendChild(button);
            list.appendChild(item);
        });
    }

    function renderEvidence(rows, requirement) {
        var list = clearList('legal-provenance-evidence');
        if (!list) return;
        if (!rows.length) {
            note(list, 'missing-input', 'No evidence span is linked. Support cannot be treated as adopted evidence.', {missing: 'evidence-span', requirementId: requirement ? requirement.id : ''});
            return;
        }
        rows.forEach(function (row) {
            var button = document.createElement('button');
            button.type = 'button';
            button.className = 'legal-provenance-evidence';
            button.dataset.role = 'evidence-span';
            button.dataset.graphKind = 'factual';
            button.dataset.adopted = row.adopted ? 'true' : 'false';
            button.dataset.admittedLaw = 'false';
            button.dataset.spanStart = text(row.start);
            button.dataset.spanEnd = text(row.end);
            button.textContent = row.text;
            button.addEventListener('click', function () {
                button.setAttribute('aria-pressed', 'true');
                var step = document.getElementById('legal-provenance-step-evidence');
                if (step) {
                    step.disabled = false;
                    step.dataset.filled = 'true';
                    step.textContent = 'Evidence span';
                    step.setAttribute('aria-current', 'step');
                }
            });
            var item = document.createElement('li');
            item.appendChild(button);
            list.appendChild(item);
        });
    }

    function renderRequirements() {
        var list = clearList('legal-provenance-requirements');
        provenance.requirements.forEach(function (requirement) {
            var button = document.createElement('button');
            button.type = 'button';
            button.className = 'legal-provenance-requirement';
            button.dataset.role = 'requirement';
            button.dataset.graphKind = 'legal-dependency';
            button.dataset.requirementId = requirement.id;
            button.dataset.passageId = text(requirement.passage_id);
            button.dataset.admittedLaw = requirement.admitted_law === true ? 'true' : 'false';
            button.dataset.supportState = text(requirement.support_state || 'unknown');
            button.dataset.current = 'true';
            button.dataset.conclusionCurrent = 'true';
            button.dataset.legalSufficiency = requirement.legal_sufficiency === true ? 'true' : 'false';
            button.setAttribute('aria-pressed', provenance.selected === requirement.id ? 'true' : 'false');
            var title = document.createElement('strong');
            var span = requirement.source_span && typeof requirement.source_span === 'object' ? requirement.source_span : {};
            title.textContent = text(requirement.rule_text || requirement.description || span.text || requirement.name) || 'Requirement';
            var meta = document.createElement('span');
            var citation = text(requirement.citation || requirement.name);
            meta.textContent = (citation && citation !== title.textContent ? ' ' + citation + '.' : '')
                + ' Support ' + text(requirement.support_state || 'unknown') + '. Sufficiency ' + (requirement.legal_sufficiency === true ? 'true' : 'false') + '.';
            button.appendChild(title);
            button.appendChild(document.createTextNode(' '));
            button.appendChild(meta);
            button.addEventListener('click', function () {
                selectRequirement(requirement.id);
                var step = document.getElementById('legal-provenance-step-requirement');
                if (step) step.setAttribute('aria-current', 'step');
            });
            var item = document.createElement('li');
            item.appendChild(button);
            list.appendChild(item);
        });
    }

    function renderGaps(payload, lawGraph) {
        var contradictions = clearList('legal-provenance-contradictions');
        var missing = clearList('legal-provenance-missing');
        var suggestions = clearList('legal-provenance-suggestions');
        (payload.unresolved_research || []).forEach(function (item) {
            if (!item || typeof item !== 'object') return;
            var reason = text(item.reason || 'unresolved');
            if (reason === 'conflicting_authority') note(contradictions, 'contradiction', 'Conflicting admitted authority is unresolved.', {reason: reason});
            else note(missing, 'missing-input', 'Missing input: ' + reason + '.', {missing: reason});
        });
        (lawGraph && lawGraph.factual_links || []).forEach(function (link) {
            if (!link || typeof link !== 'object') return;
            if (link.link_kind === 'contradicts') note(contradictions, 'contradiction', 'A factual link contradicts ' + text(link.requirement_id) + '.', {reason: 'contradicts', requirementId: text(link.requirement_id)});
            if (link.link_kind === 'missing_evidence') note(missing, 'missing-input', 'Missing evidence for ' + text(link.requirement_id) + '.', {missing: 'evidence', requirementId: text(link.requirement_id)});
        });
        (provenance.contradictions || []).forEach(function (item) {
            note(contradictions, 'contradiction', text(item.text || item.reason || 'Unresolved factual contradiction.'), {reason: 'factual-conflict'});
        });
        if (contradictions && !contradictions.children.length) note(contradictions, 'contradiction', 'No contradiction is recorded on the current projection.', {present: 'false', reason: 'none'});
        if (missing && !missing.children.length) note(missing, 'missing-input', 'No missing input is recorded on the current projection.', {present: 'false', missing: 'none'});
        provenance.suggestions.forEach(function (item) {
            if (suggestions) note(suggestions, 'ai-suggestion', item.text || 'AI suggestion', {admittedLaw: 'false', label: 'ai-suggestion'});
        });
    }

    function requirementId(item, index) {
        return text(item.requirement_id || item.passage_id || item.authority_id || ('requirement-' + index));
    }

    function ensureRetirement() {
        var host = provenanceRoot();
        if (!host || document.getElementById('legal-support-retirement')) return;
        var section = document.createElement('section');
        section.id = 'legal-support-retirement';
        section.dataset.task = 'CIMP-UX-28';
        section.dataset.state = 'current';
        section.hidden = true;
        var prompt = document.createElement('p');
        prompt.id = 'legal-support-retirement-prompt';
        prompt.dataset.bounded = 'true';
        prompt.dataset.required = 'false';
        var changed = document.createElement('p');
        changed.id = 'legal-support-changed-context';
        var button = document.createElement('button');
        button.type = 'button';
        button.id = 'legal-support-refresh-review';
        button.textContent = 'Review and refresh support';
        var audit = document.createElement('ol');
        audit.id = 'legal-support-audit';
        audit.setAttribute('aria-label', 'Previous support versions');
        section.appendChild(prompt);
        section.appendChild(changed);
        section.appendChild(button);
        section.appendChild(audit);
        host.appendChild(section);
        button.addEventListener('click', function () { deriveProvenance({authorizedRefresh: true}); });
    }

    function evidenceFingerprint(factual) {
        var rows = [].concat(
            Array.isArray(factual && factual.adopted_evidence) ? factual.adopted_evidence : [],
            Array.isArray(factual && factual.evidence_revisions) ? factual.evidence_revisions : []
        );
        return rows.map(function (item) {
            var span = spanOf(item);
            return [text(item.graph_entity_id || item.assertion_id), text(item.revision || item.version), span.text || text(item.text)].join(':');
        }).filter(function (item) { return item !== '::'; }).join('|');
    }

    function fieldValue(id) {
        var node = document.getElementById(id);
        return node ? text(node.value).trim() : '';
    }

    function observedSupportContext(payload, factual, consentGeneration) {
        var bound = payload && payload.bound_context && typeof payload.bound_context === 'object' ? payload.bound_context : {};
        var observed = payload && payload.observed_context && typeof payload.observed_context === 'object' ? payload.observed_context : {};
        var requirement = (payload && payload.requirements && payload.requirements[0]) || {};
        return {
            authority_version: fieldValue('legal-provenance-authority-version')
                || text(observed.authority_version || requirement.authority_version || bound.authority_version),
            passage_id: reviewedPassageId || text(requirement.passage_id),
            effective_date: fieldValue('legal-context-applicable-law-date')
                || text(observed.effective_date || bound.effective_date || requirement.effective_date),
            as_of_date: fieldValue('legal-context-event-date')
                || text(observed.as_of_date || bound.as_of_date || requirement.applicable_date),
            jurisdiction: fieldValue('legal-context-jurisdiction')
                || text(observed.jurisdiction || bound.jurisdiction || requirement.jurisdiction),
            consent_generation: text(consentGeneration),
            evidence_version: evidenceFingerprint(factual) || text(observed.evidence_version)
        };
    }

    function contextDrift(previous, observed) {
        if (!previous) return [];
        return ['authority_version', 'passage_id', 'effective_date', 'as_of_date', 'jurisdiction', 'consent_generation', 'evidence_version'].filter(function (field) {
            return previous[field] && observed[field] && previous[field] !== observed[field];
        });
    }

    function retirePayload(payload, changed) {
        var copy = Object.assign({}, payload);
        var requirements = Array.isArray(payload.requirements) ? payload.requirements : [];
        var history = Array.isArray(payload.audit_history) ? payload.audit_history.slice() : [];
        if (requirements.length) {
            history.push({
                version: text(payload.request_id || 'previous'),
                current: false,
                conclusion_current: false,
                support_state: 'retired',
                changed_context: changed,
                requirements: requirements.map(function (item) {
                    var row = Object.assign({}, item);
                    row.support_state = 'retired';
                    row.current = false;
                    row.conclusion_current = false;
                    row.legal_sufficiency = false;
                    row.proof = false;
                    return row;
                })
            });
        }
        copy.requirements = [];
        copy.audit_history = history;
        copy.support_retired = true;
        copy.support_current = false;
        copy.admitted_law = false;
        copy.status = 'stale_support';
        copy.changed_context = changed;
        copy.refresh_review = payload.refresh_review && payload.refresh_review.prompt ? payload.refresh_review : {
            bounded: true,
            required: true,
            prompt: 'Support tied to the previous context is retired. An authorized review can refresh it. The previous conclusion stays in the audit history.'
        };
        return copy;
    }

    function renderAudit(history) {
        ensureRetirement();
        var list = document.getElementById('legal-support-audit');
        if (!list) return;
        (Array.isArray(history) ? history : []).forEach(function (entry) {
            (Array.isArray(entry.requirements) ? entry.requirements : []).forEach(function (requirement) {
                var version = text(entry.version || requirement.passage_id || 'previous');
                var span = requirement.source_span && typeof requirement.source_span === 'object' ? requirement.source_span : {};
                var conclusion = text(requirement.rule_text || requirement.description || span.text || requirement.name);
                var key = version + '|' + conclusion;
                var duplicate = Array.prototype.some.call(list.children, function (child) { return child.dataset.auditKey === key; });
                if (duplicate) return;
                var item = document.createElement('li');
                item.dataset.role = 'support-audit';
                item.dataset.current = 'false';
                item.dataset.conclusionCurrent = 'false';
                item.dataset.supportState = 'retired';
                item.dataset.version = version;
                item.dataset.auditKey = key;
                item.textContent = 'Previous version ' + version + ': ' + conclusion;
                list.appendChild(item);
            });
        });
    }

    function showRetirement(payload, observed) {
        ensureRetirement();
        var section = document.getElementById('legal-support-retirement');
        var prompt = document.getElementById('legal-support-retirement-prompt');
        var changed = document.getElementById('legal-support-changed-context');
        var review = payload.refresh_review || {};
        var fields = Array.isArray(payload.changed_context) ? payload.changed_context : [];
        if (section) {
            section.hidden = payload.support_retired !== true;
            section.dataset.state = payload.support_retired === true ? 'stale' : 'current';
            section.dataset.supportCurrent = payload.support_current === true ? 'true' : 'false';
            section.dataset.consentGeneration = text(observed && observed.consent_generation);
            section.dataset.evidenceVersion = text(observed && observed.evidence_version);
            section.dataset.authorityVersion = text(observed && observed.authority_version);
            section.dataset.jurisdiction = text(observed && observed.jurisdiction);
        }
        if (prompt) {
            prompt.dataset.bounded = 'true';
            prompt.dataset.required = payload.support_retired === true ? 'true' : 'false';
            prompt.textContent = payload.support_retired === true
                ? text(review.prompt || 'Support is retired. Review and refresh it from the current admitted passage.')
                : '';
        }
        if (changed) {
            changed.dataset.changedContext = fields.join(',');
            changed.textContent = fields.length ? 'Changed context: ' + fields.join(', ') + '.' : '';
        }
        renderAudit(payload.audit_history);
        var support = document.getElementById('legal-provenance-support');
        if (support && payload.support_retired === true) {
            support.dataset.supportState = 'retired';
            support.dataset.current = 'false';
            support.dataset.conclusionCurrent = 'false';
            support.textContent = 'Support: retired. The previous conclusion is audit history, not the current conclusion.';
        } else if (support && Array.isArray(payload.requirements) && payload.requirements.length) {
            support.dataset.current = 'true';
            support.dataset.conclusionCurrent = 'true';
        }
    }

    function applyProvenance(payload, factual, lawGraph) {
        payload = payload && typeof payload === 'object' ? payload : {requirements: []};
        factual = factual && typeof factual === 'object' ? factual : {};
        provenance.requirements = (Array.isArray(payload.requirements) ? payload.requirements : []).map(function (item, index) {
            var copy = Object.assign({}, item);
            copy.id = requirementId(item, index);
            copy.legal_sufficiency = item.legal_sufficiency === true && payload.legal_sufficiency === true;
            return copy;
        });
        provenance.facts = [];
        ['user_statements', 'allegations'].forEach(function (bucket) {
            (Array.isArray(factual[bucket]) ? factual[bucket] : []).forEach(function (item) {
                var span = spanOf(item);
                provenance.facts.push({
                    id: text(item.assertion_id || item.graph_entity_id || item.immutable_source_id),
                    entityId: text(item.graph_entity_id),
                    text: text(item.text),
                    span: span.text,
                    spanStart: span.start,
                    spanEnd: span.end,
                    adopted: false,
                    origin: 'factual-graph'
                });
            });
        });
        provenance.evidence = [];
        ['adopted_evidence', 'evidence_revisions'].forEach(function (bucket) {
            (Array.isArray(factual[bucket]) ? factual[bucket] : []).forEach(function (item) {
                var span = spanOf(item);
                if (!span.text && !text(item.text)) return;
                provenance.evidence.push({
                    id: text(item.assertion_id || item.graph_entity_id || bucket),
                    assertionId: text(item.assertion_id),
                    text: span.text || text(item.text),
                    start: span.start,
                    end: span.end,
                    adopted: item.explicitly_adopted_evidence === true
                });
            });
        });
        provenance.contradictions = Array.isArray(factual.contradictions) ? factual.contradictions : [];
        provenance.suggestions = [];
        (Array.isArray(factual.hypotheses) ? factual.hypotheses : []).forEach(function (item) {
            provenance.suggestions.push({text: text(item.text || item.reason || 'Hypothesis'), admitted_law: false});
        });
        ((lawGraph && lawGraph.rejected_narratives) || []).forEach(function (item) {
            var origin = text(item && item.origin);
            if (origin === 'model_output' || origin === 'llm_text' || origin === 'model') {
                provenance.suggestions.push({text: text(item.text || item.reason), admitted_law: false});
            }
        });
        var host = provenanceRoot();
        if (host) {
            host.dataset.legalSufficiency = payload.legal_sufficiency === true ? 'true' : 'false';
            host.dataset.admittedLaw = payload.admitted_law === true ? 'true' : 'false';
        }
        var legalPanel = document.getElementById('legal-dependency-graph');
        var factPanel = document.getElementById('factual-provenance-graph');
        if (legalPanel) legalPanel.dataset.state = lawGraph && lawGraph.error ? 'unavailable' : 'ready';
        if (factPanel) factPanel.dataset.state = factual.status === 'unavailable' ? 'unavailable' : 'ready';
        renderRequirements();
        renderGaps(payload, lawGraph);
        renderLabels(provenance.requirements[0] || null);
        if (payload.support_retired === true) {
            paintProvenanceState('stale', 'Support is retired. The previous conclusion remains in the audit history and is not current.');
            selectRequirement('');
            showRetirement(payload, payload.observed_support || null);
            return;
        }
        showRetirement(payload, payload.observed_support || null);
        if (!provenance.requirements.length) {
            paintProvenanceState(payload.status === 'empty' ? 'empty' : 'ready', payload.status === 'empty'
                ? 'No derived requirement is stored. Missing inputs stay visible.'
                : 'No current requirement was derived. Unresolved research stays visible.');
            selectRequirement('');
            return;
        }
        paintProvenanceState('ready', 'Current requirements are loaded. Choose one to follow its passage, assertion, and evidence span.');
        selectRequirement(provenance.selected && provenance.requirements.some(function (item) { return item.id === provenance.selected; })
            ? provenance.selected : provenance.requirements[0].id);
    }

    async function readJson(path) {
        return client._request(path, {method: 'GET'});
    }

    function activeCaseId() {
        if (client && client.caseContext && client.caseContext.case_id) return text(client.caseContext.case_id);
        return caseId();
    }

    async function loadProvenance() {
        var host = provenanceRoot();
        var id = activeCaseId();
        if (!host) return;
        if (!client || !id) {
            paintProvenanceState('empty', 'Select a case before reading requirement provenance.');
            return;
        }
        var factual = {status: 'unavailable', user_statements: [], adopted_evidence: [], evidence_revisions: []};
        var lawGraph = null;
        var payload = null;
        var consentGeneration = '';
        try {
            payload = await readJson('/api/legal-analysis/' + encodeURIComponent(id) + '/dependency-requirements');
        } catch (error) {
            var code = text(error && (error.code || error.message));
            paintProvenanceState(code.indexOf('unlock') >= 0 ? 'locked' : 'unavailable', code.indexOf('unlock') >= 0
                ? 'The case key is locked. Requirement text stays hidden.'
                : 'Requirement provenance could not be read. Nothing was marked admitted or sufficient.');
            return;
        }
        try {
            factual = await readJson('/api/complaint-workspace/factual-graph?case_id=' + encodeURIComponent(id));
        } catch (error) {
            factual = {status: 'unavailable', error: text(error && (error.code || error.message)), user_statements: [], contradictions: []};
        }
        try {
            lawGraph = await readJson('/api/graphs/' + encodeURIComponent(id) + '/legal-dependency');
        } catch (error) {
            lawGraph = {error: text(error && (error.code || error.message)), requirements: [], factual_links: [], rejected_narratives: []};
        }
        try {
            var consent = await readJson('/api/cases/' + encodeURIComponent(id) + '/processing-consent');
            consentGeneration = text(consent && consent.generation);
        } catch (error) {
            consentGeneration = '';
        }
        if (activeCaseId() !== id) return;
        var observed = observedSupportContext(payload, factual, consentGeneration);
        var derivation = text(payload.request_id || payload.private_revision);
        var sameDerivation = !!(provenance.binding && provenance.binding.request_id === derivation);
        var drift = sameDerivation ? contextDrift(provenance.binding, observed) : [];
        var changed = (Array.isArray(payload.changed_context) ? payload.changed_context : []).slice();
        drift.forEach(function (field) { if (changed.indexOf(field) < 0) changed.push(field); });
        if (changed.length && payload.support_retired !== true && Array.isArray(payload.requirements) && payload.requirements.length) {
            payload = retirePayload(payload, changed);
        } else if (payload.support_retired === true && changed.length) {
            payload.changed_context = changed;
        }
        payload.observed_support = observed;
        if (payload.support_retired !== true) {
            provenance.binding = Object.assign({request_id: derivation}, observed);
        }
        applyProvenance(payload, factual, lawGraph);
    }

    async function deriveProvenance(options) {
        var id = activeCaseId();
        if (!client || !id) {
            paintProvenanceState('empty', 'Select a case before deriving a requirement.');
            return;
        }
        var session;
        try {
            session = await readJson('/api/complaint-workspace/session?case_id=' + encodeURIComponent(id));
        } catch (error) {
            paintProvenanceState('unavailable', 'The case session could not be read. No requirement was derived.');
            return;
        }
        var head = session && session.encrypted_head ? session.encrypted_head : {};
        var shared = session && session.session && session.session.shared_interview ? session.session.shared_interview : {};
        var privateRevision = text(head.private_revision);
        var sessionRevision = shared.session_revision;
        var factId = text((document.getElementById('legal-provenance-fact-id') || {}).value).trim();
        var factText = text((document.getElementById('legal-provenance-fact-text') || {}).value).trim();
        provenance.submittedFacts = factId && factText ? [{id: factId, text: factText}] : [];
        var body = {
            request_id: (options && options.authorizedRefresh ? 'ux28-refresh-' : 'ux27-') + Date.now(),
            query: text((document.getElementById('legal-source-flow-query') || {}).value).trim(),
            offline_cache: cacheBody(),
            review_passage_id: reviewedPassageId,
            review_decision: reviewedPassageId ? 'admit' : '',
            authority_version: text((document.getElementById('legal-provenance-authority-version') || {}).value).trim(),
            expected_private_revision: privateRevision,
            expected_session_revision: sessionRevision,
            facts: factId && factText ? [{fact_id: factId, text: factText}] : []
        };
        if (options && options.authorizedRefresh) body.authorized_support_refresh = true;
        try {
            var derived = await client._request('/api/legal-analysis/' + encodeURIComponent(id) + '/dependency-requirements', {
                method: 'POST',
                body: JSON.stringify(body)
            });
            if (derived && Array.isArray(derived.requirements)) {
                derived.requirements.forEach(function (requirement) {
                    (requirement.fact_support || []).forEach(function (support) {
                        if (support && support.fact_id === factId) support.fact_text = factText;
                    });
                });
            }
            await loadProvenance();
            if (derived && derived.status) {
                var status = document.getElementById('legal-provenance-status');
                if (status && provenanceRoot() && provenanceRoot().dataset.state === 'ready') {
                    status.dataset.derivationStatus = derived.status;
                }
            }
        } catch (error) {
            var code = text(error && (error.code || error.message));
            var conflict = code.indexOf('revision_conflict') >= 0 || code.indexOf('409') >= 0 || code === 'http_409';
            var host = provenanceRoot();
            if (host) host.dataset.headMutated = 'false';
            paintProvenanceState(conflict ? 'conflict' : 'unavailable', conflict
                ? 'The refresh was refused. The encrypted case head was not changed, and the previous conclusion stays in the audit history.'
                : 'Derivation was refused. Nothing new was admitted and the encrypted case head was not changed.');
        }
    }

    function bindProvenance() {
        var refresh = document.getElementById('legal-provenance-refresh');
        if (!refresh || refresh.dataset.bound === 'true') return;
        refresh.dataset.bound = 'true';
        refresh.addEventListener('click', function () { loadProvenance(); });
        document.getElementById('legal-provenance-derive').addEventListener('click', function () { deriveProvenance(); });
        ensureRetirement();
        ['legal-provenance-step-requirement', 'legal-provenance-step-passage', 'legal-provenance-step-assertion', 'legal-provenance-step-evidence'].forEach(function (id) {
            var button = document.getElementById(id);
            if (!button) return;
            button.addEventListener('click', function () {
                document.querySelectorAll('#legal-provenance-trail button').forEach(function (item) { item.removeAttribute('aria-current'); });
                button.setAttribute('aria-current', 'step');
                var target = {requirement: 'legal-provenance-requirements', 'law-passage': 'legal-provenance-passage', 'factual-assertion': 'legal-provenance-assertions', 'evidence-span': 'legal-provenance-evidence'}[button.dataset.step];
                var node = target ? document.getElementById(target) : null;
                if (node) node.scrollIntoView({block: 'nearest'});
            });
        });
    }

    window.complaintLegal = {install: install, renderQuestions: renderQuestions, loadProvenance: loadProvenance};
}());
