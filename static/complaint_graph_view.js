/* Law-derived dependency graph view.

   Legal rules render only from admitted-authority fields. Factual support,
   contradiction, and missing-evidence links render in a separate section.
   User narratives and model output are not copied into a legal rule.
   This file does not open a WebSocket or SSE stream.
*/
"use strict";

function escapeHtml(value) {
  return String(value == null ? "" : value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function asList(value) {
  return Array.isArray(value) ? value : [];
}

function lawDerivedDependencyMarkup(payload) {
  var body = payload && typeof payload === "object" ? payload : {};
  var requirements = asList(body.requirements);
  var links = asList(body.factual_links);
  var rejected = asList(body.rejected_narratives);
  var rules = requirements.map(function (rule) {
    var exceptions = asList(rule.exceptions).map(function (item) {
      return "<li data-role=\"exception\">" + escapeHtml(item) + "</li>";
    }).join("");
    return [
      "<article data-role=\"legal-rule\" data-content-hash=\"" + escapeHtml(rule.content_hash) + "\" data-source=\"admitted_authority\">",
      "<h3 data-role=\"authority-identity\">" + escapeHtml(rule.authority_identity) + "</h3>",
      "<p data-role=\"requirement\">" + escapeHtml(rule.requirement) + "</p>",
      "<p data-role=\"burden\" data-burden-status=\"" + escapeHtml(rule.burden_status) + "\">" + escapeHtml(rule.burden) + "</p>",
      "<p data-role=\"applicability\">" + escapeHtml(rule.applicability) + "</p>",
      "<p data-role=\"jurisdiction\">" + escapeHtml(rule.jurisdiction) + "</p>",
      "<p data-role=\"effective-date\">" + escapeHtml(rule.effective_date) + "</p>",
      "<ul data-role=\"exceptions\">" + exceptions + "</ul>",
      "</article>",
    ].join("");
  }).join("");
  var factItems = links.map(function (link) {
    return [
      "<li data-role=\"factual-link\" data-link-kind=\"" + escapeHtml(link.link_kind) + "\" data-content-hash=\"" + escapeHtml(link.content_hash) + "\" data-rewrites-legal-rule=\"false\">",
      "<span data-role=\"fact-text\">" + escapeHtml(link.fact_text) + "</span>",
      "<span data-role=\"fact-source-id\">" + escapeHtml(link.fact_source_id) + "</span>",
      "<span data-role=\"fact-reason\">" + escapeHtml(link.reason) + "</span>",
      "</li>",
    ].join("");
  }).join("");
  var rejectedItems = rejected.map(function (item) {
    return "<li data-role=\"rejected-narrative\" data-reason=\"" + escapeHtml(item.reason) + "\">" + escapeHtml(item.text) + "</li>";
  }).join("");
  return [
    "<section data-role=\"law-derived-dependency-graph\" data-task-id=\"CIMP-GUI-27\" data-proof=\"false\" data-rules-rewritten=\"false\">",
    "<section data-role=\"legal-rules\">" + rules + "</section>",
    "<section data-role=\"factual-links\"><ul>" + factItems + "</ul></section>",
    "<section data-role=\"rejected-narratives\"><ul>" + rejectedItems + "</ul></section>",
    "</section>",
  ].join("");
}

function renderLawDerivedDependencyGraph(container, payload) {
  var html = lawDerivedDependencyMarkup(payload);
  if (container && typeof container === "object") {
    container.innerHTML = html;
  }
  return html;
}

var FACTUAL_BUCKETS = ["user_statements", "allegations", "evidence_revisions", "hypotheses"];
var FACTUAL_TASK = "CIMP-GUI-23";

function factualItems(payload) {
  var body = payload && typeof payload === "object" ? payload : {};
  var rows = [];
  FACTUAL_BUCKETS.forEach(function (bucket) {
    asList(body[bucket]).forEach(function (item) {
      if (item && typeof item === "object") rows.push({bucket: bucket, item: item});
    });
  });
  return rows;
}

function nodeKey(item, fallback) {
  var value = item && (item.assertion_id || item.graph_entity_id || item.immutable_source_id);
  return String(value || fallback);
}

function supportIsAuthorized(entry) {
  var item = entry.item || {};
  return entry.bucket === "user_statements"
    && item.authority_is_user_fact === true
    && item.admitted_user_fact === true
    && item.kind === "user_statement"
    && item.provenance_status === "verified"
    && item.activity_status === "active";
}

function itemByAssertion(rows) {
  var index = {};
  rows.forEach(function (entry) {
    var id = entry.item.assertion_id;
    if (id) index[String(id)] = entry;
    var entity = entry.item.graph_entity_id;
    if (entity) index["entity:" + String(entity)] = entry;
  });
  return index;
}

function lookupText(index, assertionId, entityId) {
  var entry = assertionId ? index[String(assertionId)] : null;
  if (!entry && entityId) entry = index["entity:" + String(entityId)];
  if (!entry || typeof entry.item.text !== "string") return "";
  return entry.item.text;
}

function sourceDetailMarkup(item) {
  return [
    "<dl data-role=\"source-details\">",
    "<dt>Source</dt><dd data-role=\"immutable-source-id\">" + escapeHtml(item.immutable_source_id) + "</dd>",
    "<dt>Provenance</dt><dd data-role=\"provenance-status\">" + escapeHtml(item.provenance_status) + "</dd>",
    "<dt>Activity</dt><dd data-role=\"activity-status\">" + escapeHtml(item.activity_status) + "</dd>",
    "<dt>Source identity</dt><dd data-role=\"source-identity\">" + escapeHtml(item.source_identity) + "</dd>",
    "<dt>Authority</dt><dd data-role=\"authority\">" + escapeHtml(item.authority) + "</dd>",
    "</dl>",
  ].join("");
}

function factualNodeMarkup(entry, ordinal, prefix) {
  var item = entry.item;
  var supported = supportIsAuthorized(entry);
  var unresolved = item.activity_status === "conflict"
    || item.activity_status === "unverified"
    || item.provenance_status !== "verified"
    || item.admitted_user_fact !== true;
  var nodeId = prefix + "-node-" + ordinal;
  return [
    "<article data-role=\"factual-node\" data-node-id=\"" + nodeId + "\" data-bucket=\"" + escapeHtml(entry.bucket) + "\"",
    " data-support=\"" + (supported ? "true" : "false") + "\" data-unresolved=\"" + (unresolved ? "true" : "false") + "\" data-hidden=\"false\"",
    " id=\"" + nodeId + "\">",
    "<h4 data-role=\"fact-text\">" + escapeHtml(item.text) + "</h4>",
    sourceDetailMarkup(item),
    "</article>",
  ].join("");
}

function unresolvedMarkup(payload, prefix) {
  return asList(payload.unresolved).map(function (item, index) {
    var row = item && typeof item === "object" ? item : {};
    return [
      "<article data-role=\"unresolved-node\" data-hidden=\"false\" data-unresolved=\"true\" id=\"" + prefix + "-unresolved-" + index + "\">",
      "<h4 data-role=\"unresolved-kind\">" + escapeHtml(row.kind || "unresolved") + "</h4>",
      "<p data-role=\"unresolved-reason\">" + escapeHtml(row.reason || "unresolved") + "</p>",
      "</article>",
    ].join("");
  }).join("");
}

function nodesMarkup(rows, payload, prefix) {
  return rows.map(function (entry, ordinal) {
    return factualNodeMarkup(entry, ordinal, prefix);
  }).join("") + unresolvedMarkup(payload, prefix);
}

function revisionDiffMarkup(payload, index) {
  return asList(payload.revisions).map(function (revision, ordinal) {
    var row = revision && typeof revision === "object" ? revision : {};
    var previous = lookupText(index, row.previous_assertion_id, row.previous_entity_id);
    var next = lookupText(index, row.new_assertion_id, row.new_entity_id);
    return [
      "<article data-role=\"revision-diff\" data-action=\"" + escapeHtml(row.action || "unrecognized") + "\" data-provenance=\"" + escapeHtml(row.provenance_status || "unverified") + "\">",
      "<h4>Revision " + escapeHtml(row.event_id || String(ordinal + 1)) + "</h4>",
      "<p data-role=\"diff-previous\" data-assertion-id=\"" + escapeHtml(row.previous_assertion_id) + "\">" + escapeHtml(previous) + "</p>",
      "<p data-role=\"diff-next\" data-assertion-id=\"" + escapeHtml(row.new_assertion_id) + "\">" + escapeHtml(next) + "</p>",
      "</article>",
    ].join("");
  }).join("");
}

function contradictionMarkup(payload) {
  var links = [];
  asList(payload.unresolved_conflicts).forEach(function (conflict, ordinal) {
    var row = conflict && typeof conflict === "object" ? conflict : {};
    var ids = asList(row.assertion_ids).filter(function (id) { return typeof id === "string" && id; });
    if (!ids.length) {
      links.push("<li data-role=\"contradiction-link\" data-unresolved=\"true\" data-hidden=\"false\" data-ordinal=\"" + ordinal + "\">Unresolved contradiction</li>");
      return;
    }
    for (var i = 0; i < ids.length; i += 1) {
      for (var j = i + 1; j < ids.length; j += 1) {
        links.push([
          "<li data-role=\"contradiction-link\" data-unresolved=\"true\" data-hidden=\"false\"",
          " data-from=\"" + escapeHtml(ids[i]) + "\" data-to=\"" + escapeHtml(ids[j]) + "\">",
          "<a href=\"#factual-contradiction-" + ordinal + "\">Contradiction " + escapeHtml(ids[i]) + " and " + escapeHtml(ids[j]) + "</a>",
          "</li>",
        ].join(""));
      }
    }
  });
  return links.join("");
}

function factualInspectorMarkup(payload, options) {
  var body = payload && typeof payload === "object" ? payload : {};
  var requestedHide = Boolean(options && options.hideUnresolved);
  var rows = factualItems(body);
  var index = itemByAssertion(rows);
  var contradictions = contradictionMarkup(body);
  var diffs = revisionDiffMarkup(body, index);
  var limitations = asList(body.limitations).map(function (item) {
    return "<li data-role=\"limitation\">" + escapeHtml(item) + "</li>";
  }).join("");
  return [
    "<div data-role=\"factual-graph-inspector\" data-task-id=\"" + FACTUAL_TASK + "\" data-read-only=\"true\"",
    " data-case-id=\"" + escapeHtml(body.case_id) + "\" data-support-fabricated=\"false\"",
    " data-unresolved-hidden=\"false\" data-hide-request-ignored=\"" + (requestedHide ? "true" : "false") + "\"",
    " data-private-boundary=\"true\" data-analytics=\"false\" data-persisted=\"false\">",
    "<div data-role=\"list-view\" role=\"region\" aria-label=\"Factual list\">" + nodesMarkup(rows, body, "list") + "</div>",
    "<div data-role=\"graph-view\" role=\"group\" aria-label=\"Factual graph\">",
    "<div data-role=\"graph-nodes\">" + nodesMarkup(rows, body, "graph") + "</div>",
    "<ul data-role=\"contradiction-links\">" + contradictions + "</ul>",
    "</div>",
    "<section data-role=\"revision-diffs\" aria-label=\"Revision diffs\">" + diffs + "</section>",
    "<section data-role=\"source-limitations\"><ul>" + limitations + "</ul></section>",
    "</div>",
  ].join("");
}

function renderFactualGraphInspector(container, payload, options) {
  var html = factualInspectorMarkup(payload, options);
  if (container && typeof container === "object") {
    container.innerHTML = html;
    if (container.dataset) {
      container.dataset.supportFabricated = "false";
      container.dataset.unresolvedHidden = "false";
      container.dataset.persisted = "false";
    }
  }
  return html;
}

function authorizedFactualPath(caseId) {
  var value = String(caseId || "");
  if (!/^[A-Za-z0-9_.:-]{1,200}$/.test(value)) return "";
  return "/api/graphs/" + encodeURIComponent(value) + "/factual";
}

function refusal(reason) {
  return {refused: true, reason: reason, stored: false, support: false};
}

function fabricateGraphSupport() {
  return refusal("client_cannot_fabricate_support");
}

function hideUnresolvedNodes() {
  return {refused: true, reason: "unresolved_nodes_remain_visible", hidden: false};
}

function persistPrivateFacts() {
  return refusal("private_boundary");
}

function reportAnalytics() {
  return refusal("private_boundary");
}

async function loadAuthorizedFactualGraph(container, spec) {
  var request = spec && typeof spec === "object" ? spec : {};
  var path = authorizedFactualPath(request.caseId);
  if (!path || request.method && String(request.method).toUpperCase() !== "GET") {
    renderFactualGraphInspector(container, {case_id: "", unresolved: [{kind: "request", reason: "unauthorized_graph_request"}]});
    return {ok: false, reason: "unauthorized_graph_request"};
  }
  if (request.analyticsUrl || request.storage || request.clientSupport) {
    renderFactualGraphInspector(container, {case_id: request.caseId, unresolved: [{kind: "request", reason: "private_boundary"}]});
    return refusal("private_boundary");
  }
  var fetchImpl = typeof request.fetchImpl === "function" ? request.fetchImpl : fetch;
  var response = await fetchImpl(path, {
    method: "GET",
    credentials: "same-origin",
    headers: request.headers || {},
  });
  if (!response || response.ok !== true) {
    renderFactualGraphInspector(container, {
      case_id: request.caseId,
      unresolved: [{kind: "request", reason: "graph_read_denied"}],
    });
    return {ok: false, reason: "graph_read_denied", status: response ? response.status : 0};
  }
  var payload = await response.json();
  if (!payload || payload.case_id !== request.caseId || payload.read_only !== true) {
    renderFactualGraphInspector(container, {case_id: request.caseId, unresolved: [{kind: "request", reason: "unauthorized_projection"}]});
    return {ok: false, reason: "unauthorized_projection"};
  }
  delete payload.client_support;
  delete payload.support_override;
  var html = renderFactualGraphInspector(container, payload, {hideUnresolved: request.hideUnresolved === true});
  return {ok: true, html: html, case_id: payload.case_id};
}

var complaintGraphView = {
  escapeHtml: escapeHtml,
  lawDerivedDependencyMarkup: lawDerivedDependencyMarkup,
  renderLawDerivedDependencyGraph: renderLawDerivedDependencyGraph,
  factualInspectorMarkup: factualInspectorMarkup,
  renderFactualGraphInspector: renderFactualGraphInspector,
  loadAuthorizedFactualGraph: loadAuthorizedFactualGraph,
  authorizedFactualPath: authorizedFactualPath,
  fabricateGraphSupport: fabricateGraphSupport,
  hideUnresolvedNodes: hideUnresolvedNodes,
  persistPrivateFacts: persistPrivateFacts,
  reportAnalytics: reportAnalytics,
};

if (typeof module !== "undefined" && module.exports) {
  module.exports = complaintGraphView;
}
if (typeof window !== "undefined") {
  window.complaintGraphView = complaintGraphView;
}
