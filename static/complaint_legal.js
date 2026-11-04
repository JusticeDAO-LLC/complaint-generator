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
    }

    window.complaintLegal = {install: install, renderQuestions: renderQuestions};
}());
