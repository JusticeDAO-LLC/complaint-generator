/* Private evidence upload. Progress comes from the case upload API.
   The browser does not treat a local file selection as ingestion. */
(function () {
    var CHUNK = 32 * 1024;

    function panel() {
        return document.getElementById("evidence-private-upload");
    }

    function text(id, value) {
        var node = document.getElementById(id);
        if (node) node.textContent = value;
    }

    function caseContext() {
        var client = window.workspaceClient;
        return client && client.caseContext ? client.caseContext : null;
    }

    function headers() {
        var client = window.workspaceClient;
        var context = caseContext();
        var result = {"Content-Type": "application/json", "Accept": "application/json"};
        if (context) {
            result["x-tenant-id"] = context.tenant_id;
            result["x-case-id"] = context.case_id;
            result["x-resource-id"] = context.resource_id;
            if (context.expected_revision) result["x-expected-revision"] = String(context.expected_revision);
        }
        if (client && client.csrfToken) result["x-csrf-token"] = client.csrfToken;
        return result;
    }

    function identity(extra) {
        var context = caseContext();
        var body = {
            tenant_id: context.tenant_id,
            case_id: context.case_id,
            resource_id: context.resource_id,
            expected_revision: context.expected_revision
        };
        Object.keys(extra || {}).forEach(function (key) { body[key] = extra[key]; });
        return body;
    }

    function paint(state, status, ingestion, percent) {
        var root = panel();
        if (!root) return;
        var bounded = Math.max(0, Math.min(100, Number(percent) || 0));
        if (state !== "sealed") bounded = Math.min(bounded, 99);
        root.dataset.state = state;
        root.dataset.progress = String(bounded);
        if (state === "pending") {
            var prior = Number(root.dataset.maxPending || "0");
            if (bounded > prior) root.dataset.maxPending = String(bounded);
        }
        text("evidence-upload-status", status);
        var ingestionNode = document.getElementById("evidence-upload-ingestion");
        if (ingestionNode) {
            ingestionNode.dataset.ingestion = ingestion || "";
            ingestionNode.textContent = ingestion ? ("Ingestion status: " + ingestion) : "Ingestion has not started.";
        }
        var progress = document.getElementById("evidence-upload-progress");
        if (progress) {
            progress.value = bounded;
            progress.textContent = bounded + "%";
        }
    }

    function classify(error) {
        if (error === "key_unavailable") return "locked";
        if (error === "operation_revoked" || error === "unauthenticated") return "revoked";
        if (error === "revision_conflict" || error === "upload_stale") return "stale";
        if (error === "not_owner" || error === "tenant_mismatch" || error === "media_rejected" || error === "oversized" || error === "selector_rejected") return "denied";
        return "error";
    }

    function bytesToBase64(bytes) {
        var binary = "";
        var step = 0x8000;
        for (var index = 0; index < bytes.length; index += step) {
            binary += String.fromCharCode.apply(null, bytes.subarray(index, index + step));
        }
        return btoa(binary);
    }

    async function sha256(bytes) {
        var digest = await crypto.subtle.digest("SHA-256", bytes);
        return Array.from(new Uint8Array(digest)).map(function (part) {
            return part.toString(16).padStart(2, "0");
        }).join("");
    }

    function mediaFor(file) {
        var name = String(file.name || "").toLowerCase();
        if (name.endsWith(".html") || name.endsWith(".htm") || name.endsWith(".svg") || name.endsWith(".js") || name.endsWith(".exe")) {
            return file.type || "text/html";
        }
        if (file.type && file.type.indexOf("/") > 0) return file.type;
        if (name.endsWith(".pdf")) return "application/pdf";
        if (name.endsWith(".png")) return "image/png";
        if (name.endsWith(".jpg") || name.endsWith(".jpeg")) return "image/jpeg";
        if (name.endsWith(".tif") || name.endsWith(".tiff")) return "image/tiff";
        if (name.endsWith(".csv")) return "text/csv";
        if (name.endsWith(".txt")) return "text/plain";
        return file.type || "application/octet-stream";
    }

    async function post(path, body, signal) {
        var response = await fetch(path, {
            method: "POST",
            credentials: "same-origin",
            headers: headers(),
            body: JSON.stringify(body),
            signal: signal
        });
        var payload = null;
        try { payload = await response.json(); } catch (error) { payload = null; }
        return {ok: response.ok, status: response.status, payload: payload || {}};
    }

    function remember(payload) {
        var root = panel();
        if (!root || !payload) return;
        if (payload.upload_id) root.dataset.uploadId = payload.upload_id;
        if (payload.upload_generation) root.dataset.uploadGeneration = String(payload.upload_generation);
        if (payload.evidence_id) root.dataset.evidenceId = payload.evidence_id;
        root.dataset.uploadState = payload.upload_state || "";
    }

    function fail(payload) {
        var error = payload && payload.error ? payload.error : "upload_failed";
        var root = panel();
        if (root) {
            root.dataset.error = error;
            root.dataset.evidenceId = "";
        }
        paint(classify(error), "Upload stopped: " + error + ".", payload && payload.ingestion_status, 0);
        return payload;
    }

    async function selectedFile() {
        var input = document.getElementById("evidence-attachment");
        if (!input || !input.files || !input.files[0]) return null;
        return input.files[0];
    }

    async function begin(file) {
        var root = panel();
        var signature = [file.name, file.size, file.lastModified].join(":");
        if (!root.dataset.idempotencyKey || root.dataset.fileSignature !== signature) {
            root.dataset.idempotencyKey = "ev-upload-" + signature.replace(/[^A-Za-z0-9._-]+/g, "-").slice(0, 80);
            root.dataset.fileSignature = signature;
            root.dataset.evidenceId = "";
        }
        var bytes = new Uint8Array(await file.arrayBuffer());
        root._fileBytes = bytes;
        var opened = await post("/api/cases/evidence/uploads", identity({
            source_filename: file.name,
            original_filename: file.name,
            media_type: mediaFor(file),
            byte_length: bytes.length,
            content_sha256: await sha256(bytes),
            idempotency_key: root.dataset.idempotencyKey
        }));
        if (!opened.ok) return fail(opened.payload);
        remember(opened.payload);
        paint(opened.payload.upload_state === "sealed" ? "sealed" : "pending", "Private upload started.", opened.payload.ingestion_status, opened.payload.progress_percent);
        return opened.payload;
    }

    async function sendChunks(signal) {
        var root = panel();
        var bytes = root._fileBytes;
        var offset = 0;
        while (bytes && offset < bytes.length) {
            if (signal.aborted) throw new DOMException("aborted", "AbortError");
            var slice = bytes.subarray(offset, offset + CHUNK);
            var sent = await post("/api/cases/evidence/uploads/chunk", identity({
                upload_id: root.dataset.uploadId,
                upload_generation: Number(root.dataset.uploadGeneration),
                offset: offset,
                content_base64: bytesToBase64(slice)
            }), signal);
            if (!sent.ok) return fail(sent.payload);
            remember(sent.payload);
            paint("pending", "Uploading through the private case store.", "", sent.payload.progress_percent);
            offset += slice.length;
        }
        return true;
    }

    async function complete() {
        var root = panel();
        var done = await post("/api/cases/evidence/uploads/complete", identity({
            upload_id: root.dataset.uploadId,
            upload_generation: Number(root.dataset.uploadGeneration)
        }));
        if (!done.ok) return fail(done.payload);
        remember(done.payload);
        root._fileBytes = null;
        paint("sealed", "Upload sealed in the private case store.", done.payload.ingestion_status, 100);
        if (window.complaintEvidenceLibrary) window.complaintEvidenceLibrary.refresh();
        return done.payload;
    }

    async function start() {
        var root = panel();
        if (!root) return;
        if (!caseContext() || !caseContext().expected_revision) {
            paint("denied", "Select the case before uploading evidence.", "", 0);
            return;
        }
        var file = await selectedFile();
        if (!file) {
            paint("empty", "Choose a file to upload through the private case store.", "", 0);
            return;
        }
        root._controller = new AbortController();
        paint("pending", "Opening a private upload.", "", 0);
        var opened = await begin(file);
        if (!opened || opened.error || opened.upload_state === "sealed") return opened;
        var streamed = await sendChunks(root._controller.signal).catch(function (error) {
            if (error && error.name === "AbortError") return null;
            throw error;
        });
        if (streamed == null) return null;
        if (streamed !== true) return streamed;
        return complete();
    }

    async function cancel() {
        var root = panel();
        if (!root || !root.dataset.uploadId) {
            paint("empty", "There is no private upload to cancel.", "", 0);
            return;
        }
        if (root._controller) root._controller.abort();
        var stopped = await post("/api/cases/evidence/uploads/cancel", identity({
            upload_id: root.dataset.uploadId,
            upload_generation: Number(root.dataset.uploadGeneration)
        }));
        root._fileBytes = null;
        if (!stopped.ok && !(stopped.payload && stopped.payload.error === "operation_revoked")) {
            if (stopped.payload && stopped.payload.error) return fail(stopped.payload);
        }
        remember(stopped.payload);
        root.dataset.evidenceId = "";
        paint("revoked", "Upload cancelled. The file was not ingested.", "", 0);
        return stopped.payload;
    }

    async function retry() {
        var root = panel();
        if (!root || !root.dataset.uploadId) {
            paint("empty", "There is no private upload to retry.", "", 0);
            return;
        }
        if (root.dataset.uploadState === "sealed") {
            var again = await post("/api/cases/evidence/uploads/retry", identity({
                upload_id: root.dataset.uploadId,
                upload_generation: Number(root.dataset.uploadGeneration)
            }));
            if (!again.ok) return fail(again.payload);
            remember(again.payload);
            paint("sealed", "Idempotent retry returned the sealed upload.", again.payload.ingestion_status, 100);
            if (window.complaintEvidenceLibrary) window.complaintEvidenceLibrary.refresh();
            return again.payload;
        }
        var resumed = await post("/api/cases/evidence/uploads/retry", identity({
            upload_id: root.dataset.uploadId,
            upload_generation: Number(root.dataset.uploadGeneration)
        }));
        if (!resumed.ok) return fail(resumed.payload);
        remember(resumed.payload);
        var file = await selectedFile();
        if (!file) {
            paint("error", "Choose the same file again before retrying the upload.", "", 0);
            return resumed.payload;
        }
        root._controller = new AbortController();
        root._fileBytes = new Uint8Array(await file.arrayBuffer());
        paint("pending", "Retrying the private upload.", "", 0);
        var streamed = await sendChunks(root._controller.signal);
        if (streamed !== true) return streamed;
        return complete();
    }

    function bind() {
        var startButton = document.getElementById("evidence-upload-start");
        var cancelButton = document.getElementById("evidence-upload-cancel");
        var retryButton = document.getElementById("evidence-upload-retry");
        if (startButton) startButton.addEventListener("click", function () { start().catch(function () { paint("error", "Upload failed before the private store responded.", "", 0); }); });
        if (cancelButton) cancelButton.addEventListener("click", function () { cancel().catch(function () { paint("error", "Cancel failed before the private store responded.", "", 0); }); });
        if (retryButton) retryButton.addEventListener("click", function () { retry().catch(function () { paint("error", "Retry failed before the private store responded.", "", 0); }); });
    }

    window.complaintEvidenceUpload = {start: start, cancel: cancel, retry: retry};
    if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", bind);
    else bind();
}());

(function () {
    var QUALITIES = ["authenticity", "relevance", "admissibility", "claim_support"];
    var generation = 0;
    var previewGeneration = 0;
    var items = [];
    var itemsScope = null;
    var selectedId = "";
    var readAt = "";
    var previewBlobs = [];
    var previewController = null;

    function root() {
        return document.getElementById("evidence-library");
    }

    function caseContext() {
        var client = window.workspaceClient;
        return client && client.caseContext ? client.caseContext : null;
    }

    function captureScope() {
        var client = window.workspaceClient;
        var context = caseContext();
        if (!client || !context || client._privacyActive === false) return null;
        return {
            client: client,
            epoch: client._privacyEpoch,
            principal: client.activePrincipalId,
            caseKey: JSON.stringify([context.tenant_id, context.case_id, context.resource_id])
        };
    }

    function currentScope(scope) {
        var current = captureScope();
        return sameIdentity(scope, current) && scope.epoch === current.epoch;
    }

    function sameIdentity(scope, current) {
        return Boolean(scope && current && scope.client === current.client
            && scope.principal === current.principal && scope.caseKey === current.caseKey);
    }

    function clearPrivateState() {
        generation += 1;
        items = [];
        itemsScope = null;
        selectedId = "";
        readAt = "";
        var host = root();
        if (host) {
            host.dataset.selectedId = "";
            delete host.dataset.catalogRead;
        }
        var list = document.getElementById("evidence-library-list");
        if (list) list.textContent = "";
        clearPreview();
        paintDetail(null);
        setState("locked", "Private evidence was cleared. Open an authorized case to read its catalog again.");
    }

    function revokePreviewBlobs() {
        previewBlobs.splice(0).forEach(function (url) {
            try { URL.revokeObjectURL(url); } catch (error) { /* already revoked */ }
        });
    }

    function clearPreview() {
        previewGeneration += 1;
        if (previewController) {
            previewController.abort();
            previewController = null;
        }
        revokePreviewBlobs();
        var host = document.getElementById("evidence-preview");
        if (!host) return;
        host.dataset.kind = "";
        host.dataset.supported = "";
        host.dataset.scope = "";
        host.dataset.evidenceId = "";
        host.dataset.version = "";
        text("evidence-preview-status", "");
        text("evidence-preview-zoom-value", "100%");
        host.dataset.zoom = "100";
        var anchors = document.getElementById("evidence-preview-anchors");
        var stage = document.getElementById("evidence-preview-stage");
        var alternative = document.getElementById("evidence-preview-alternative");
        if (anchors) anchors.textContent = "";
        if (stage) {
            stage.textContent = "";
            stage.style.fontSize = "16px";
            stage.style.transform = "scale(1)";
        }
        if (alternative) {
            alternative.hidden = true;
            alternative.textContent = "";
        }
    }

    function ensurePreview() {
        var detail = document.getElementById("evidence-library-detail");
        if (!detail || document.getElementById("evidence-preview")) return;
        var section = document.createElement("section");
        section.id = "evidence-preview";
        section.dataset.kind = "";
        section.dataset.zoom = "100";
        section.dataset.supported = "";
        section.style.overflow = "auto";
        section.style.maxWidth = "100%";
        var heading = document.createElement("h4");
        heading.textContent = "Preview";
        var status = document.createElement("p");
        status.id = "evidence-preview-status";
        var controls = document.createElement("div");
        controls.id = "evidence-preview-zoom";
        controls.style.display = "flex";
        controls.style.flexWrap = "wrap";
        controls.style.gap = "8px";
        function zoomButton(id, label, delta) {
            var button = document.createElement("button");
            button.type = "button";
            button.className = "secondary";
            button.id = id;
            button.textContent = label;
            button.addEventListener("click", function () { setZoom(delta); });
            return button;
        }
        controls.appendChild(zoomButton("evidence-preview-zoom-out", "Zoom out", -25));
        controls.appendChild(zoomButton("evidence-preview-zoom-in", "Zoom in", 25));
        var reset = document.createElement("button");
        reset.type = "button";
        reset.className = "secondary";
        reset.id = "evidence-preview-zoom-reset";
        reset.textContent = "Reset zoom";
        reset.addEventListener("click", function () { applyZoom(100); });
        controls.appendChild(reset);
        var value = document.createElement("span");
        value.id = "evidence-preview-zoom-value";
        value.textContent = "100%";
        controls.appendChild(value);
        var versionLabel = document.createElement("label");
        versionLabel.htmlFor = "evidence-preview-version";
        versionLabel.textContent = "Artifact version";
        var version = document.createElement("select");
        version.id = "evidence-preview-version";
        version.addEventListener("change", function () {
            var current = items.filter(function (item) { return item.evidence_id === selectedId; })[0];
            if (current) loadPreview(current);
        });
        var anchors = document.createElement("nav");
        anchors.id = "evidence-preview-anchors";
        anchors.setAttribute("aria-label", "Preview pages and spans");
        var viewport = document.createElement("div");
        viewport.id = "evidence-preview-viewport";
        viewport.style.overflow = "auto";
        viewport.style.maxWidth = "100%";
        viewport.style.maxHeight = "320px";
        var stage = document.createElement("div");
        stage.id = "evidence-preview-stage";
        stage.style.transformOrigin = "top left";
        stage.style.fontSize = "16px";
        viewport.appendChild(stage);
        var alternative = document.createElement("p");
        alternative.id = "evidence-preview-alternative";
        alternative.hidden = true;
        section.appendChild(heading);
        section.appendChild(status);
        section.appendChild(controls);
        section.appendChild(versionLabel);
        section.appendChild(version);
        section.appendChild(anchors);
        section.appendChild(viewport);
        section.appendChild(alternative);
        detail.appendChild(section);
    }

    function applyZoom(next) {
        var zoom = Math.max(50, Math.min(200, next));
        var host = document.getElementById("evidence-preview");
        var stage = document.getElementById("evidence-preview-stage");
        if (host) host.dataset.zoom = String(zoom);
        if (stage) {
            stage.style.fontSize = (16 * zoom / 100) + "px";
            stage.style.transform = "scale(" + (zoom / 100) + ")";
        }
        text("evidence-preview-zoom-value", zoom + "%");
    }

    function setZoom(delta) {
        var host = document.getElementById("evidence-preview");
        var current = host ? Number(host.dataset.zoom || "100") : 100;
        applyZoom((Number.isFinite(current) ? current : 100) + delta);
    }

    function fillVersions(item) {
        var select = document.getElementById("evidence-preview-version");
        if (!select) return "";
        var versions = (item && item.artifact_versions) || [];
        var wanted = select.value;
        select.textContent = "";
        versions.forEach(function (version) {
            var option = document.createElement("option");
            option.value = String(version.version);
            option.textContent = "Version " + version.version + (version.kind ? " (" + version.kind + ")" : "");
            select.appendChild(option);
        });
        if (wanted && Array.prototype.some.call(select.options, function (option) { return option.value === wanted; })) {
            select.value = wanted;
        } else if (versions.length) {
            select.value = String(versions[versions.length - 1].version);
        }
        return select.value;
    }

    function renderPreview(body, scope, token) {
        if (token !== previewGeneration || !currentScope(scope)) return;
        if (!body || body.case_id !== caseContext().case_id || body.tenant_id !== caseContext().tenant_id) return;
        if (body.evidence_id !== selectedId) return;
        ensurePreview();
        var host = document.getElementById("evidence-preview");
        var stage = document.getElementById("evidence-preview-stage");
        var anchors = document.getElementById("evidence-preview-anchors");
        var alternative = document.getElementById("evidence-preview-alternative");
        if (!host || !stage || !anchors || !alternative) return;
        revokePreviewBlobs();
        stage.textContent = "";
        anchors.textContent = "";
        alternative.hidden = true;
        alternative.textContent = "";
        host.dataset.kind = body.preview_kind || "";
        host.dataset.supported = body.supported ? "true" : "false";
        host.dataset.scope = body.cache_scope || "";
        host.dataset.evidenceId = body.evidence_id || "";
        host.dataset.version = String(body.version || "");
        host.dataset.modelInvoked = "false";
        if (!body.supported) {
            var note = (body.alternative && body.alternative.message) || "This format cannot be previewed safely inside the workspace.";
            var safeText = (body.alternative && body.alternative.safe_text) || "";
            alternative.hidden = false;
            alternative.textContent = note + (safeText ? "\nReadable excerpt:\n" + safeText : "\nNo readable text is available.");
            text("evidence-preview-status", "Safe alternative. The original file was not executed.");
            return;
        }
        (body.pages || []).forEach(function (page) {
            var pageAnchor = document.createElement("a");
            pageAnchor.href = "#evidence-preview-" + page.anchor;
            pageAnchor.textContent = "Page " + page.page;
            pageAnchor.addEventListener("click", function (event) {
                event.preventDefault();
                var target = document.getElementById("evidence-preview-" + page.anchor);
                if (target) target.focus();
            });
            anchors.appendChild(pageAnchor);
            anchors.appendChild(document.createTextNode(" "));
            var block = document.createElement("section");
            block.id = "evidence-preview-" + page.anchor;
            block.tabIndex = -1;
            var pageLabel = document.createElement("h5");
            pageLabel.textContent = "Page " + page.page;
            block.appendChild(pageLabel);
            (page.spans || []).forEach(function (span) {
                var link = document.createElement("a");
                link.href = "#evidence-preview-" + span.anchor;
                link.textContent = "Span " + span.span;
                link.addEventListener("click", function (event) {
                    event.preventDefault();
                    var target = document.getElementById("evidence-preview-" + span.anchor);
                    if (target) target.focus();
                });
                anchors.appendChild(link);
                anchors.appendChild(document.createTextNode(" "));
                var row = document.createElement("p");
                row.id = "evidence-preview-" + span.anchor;
                row.tabIndex = 0;
                row.textContent = span.text || "";
                block.appendChild(row);
            });
            stage.appendChild(block);
        });
        if (body.preview_kind === "image" && body.image && body.image.content_base64) {
            var media = body.image.media_type;
            if (media !== "image/png" && media !== "image/jpeg" && media !== "image/webp") return;
            var binary = atob(body.image.content_base64);
            var bytes = new Uint8Array(binary.length);
            for (var index = 0; index < binary.length; index += 1) bytes[index] = binary.charCodeAt(index);
            var blob = new Blob([bytes], {type: media});
            var url = URL.createObjectURL(blob);
            previewBlobs.push(url);
            var image = document.createElement("img");
            image.id = "evidence-preview-image";
            image.alt = body.accessible_text || "Evidence image preview";
            image.src = url;
            image.style.maxWidth = "100%";
            image.style.height = "auto";
            stage.appendChild(image);
        }
        text("evidence-preview-status", body.preview_kind === "image"
            ? "Image preview. Zoom changes the display size. The image is not sent to a model."
            : "Text preview. Choose a page or span. Zoom changes the display size.");
        applyZoom(Number(host.dataset.zoom || "100"));
    }

    function loadPreview(item) {
        ensurePreview();
        var scope = captureScope();
        var context = caseContext();
        if (!item || !scope || !context) {
            clearPreview();
            return;
        }
        var token = ++previewGeneration;
        if (previewController) previewController.abort();
        previewController = new AbortController();
        var signal = previewController.signal;
        var version = fillVersions(item);
        var params = new URLSearchParams({
            tenant_id: context.tenant_id,
            case_id: context.case_id,
            resource_id: context.resource_id,
            evidence_id: item.evidence_id
        });
        if (version) params.set("version", version);
        text("evidence-preview-status", "Opening the encrypted preview…");
        fetch("/api/cases/evidence/preview?" + params.toString(), {
            credentials: "same-origin",
            headers: {"Accept": "application/json"},
            signal: signal
        }).then(function (response) {
            return response.json().then(function (body) { return {ok: response.ok, status: response.status, body: body}; });
        }).then(function (result) {
            if (token !== previewGeneration || !currentScope(scope)) return;
            if (!result.ok || !result.body || result.body.error) {
                ensurePreview();
                text("evidence-preview-status", result.status === 401 || result.status === 403
                    ? "This preview is not available for the current case."
                    : "The preview could not be opened. The encrypted artifact is unchanged.");
                var stage = document.getElementById("evidence-preview-stage");
                if (stage) stage.textContent = "";
                revokePreviewBlobs();
                return;
            }
            renderPreview(result.body, scope, token);
        }).catch(function (error) {
            if (error && error.name === "AbortError") return;
            if (token !== previewGeneration || !currentScope(scope)) return;
            text("evidence-preview-status", "The preview could not be opened. The encrypted artifact is unchanged.");
        });
    }

    function currentRead(token, scope, rescopeCount) {
        if (token !== generation) return false;
        if (currentScope(scope)) return true;
        var current = captureScope();
        var requestedSelection = selectedId;
        clearPrivateState();
        // A same-case SDK rebind also retires pending reads. Obtain a new
        // authorized catalog once; never reuse the response from its old epoch.
        if (rescopeCount < 1 && sameIdentity(scope, current)) {
            selectedId = requestedSelection;
            load(rescopeCount + 1);
        }
        return false;
    }

    function text(id, value) {
        var node = document.getElementById(id);
        if (node) node.textContent = value;
    }

    function show(id, visible) {
        var node = document.getElementById(id);
        if (node) node.hidden = !visible;
    }

    function layout() {
        var host = root();
        if (!host) return;
        var mobile = window.matchMedia("(max-width: 767px)").matches;
        host.dataset.layout = mobile ? "list-detail" : "master-detail";
        if (!mobile) host.dataset.pane = "both";
        else if (host.dataset.pane !== "detail") host.dataset.pane = "list";
    }

    function recorded(value) {
        return typeof value === "string" && value.trim() ? value.trim() : "Not recorded";
    }

    function notesFor(item) {
        var notes = item.notes || item.attributed_notes || [];
        if (!Array.isArray(notes)) return [];
        return notes.filter(function (note) { return note && typeof note === "object"; });
    }

    function linksFor(item) {
        var links = [];
        if (item.complaint_link_id) links.push(String(item.complaint_link_id));
        if (Array.isArray(item.complaint_links)) {
            item.complaint_links.forEach(function (link) {
                var value = typeof link === "string" ? link : (link && (link.complaint_link_id || link.id));
                if (value) links.push(String(value));
            });
        }
        return links;
    }

    function haystack(item) {
        var notes = notesFor(item).map(function (note) {
            return [note.note, note.text, note.author, note.actor_principal_id].join(" ");
        }).join(" ");
        return [
            item.source_filename, item.original_filename, item.evidence_id,
            item.ingestion_status, item.complaint_link_id, item.failure_code,
            item.actor_principal_id, notes
        ].join(" ").toLowerCase();
    }

    function visibleItems() {
        var query = (document.getElementById("evidence-library-search").value || "").trim().toLowerCase();
        var status = document.getElementById("evidence-library-status-filter").value;
        return items.filter(function (item) {
            if (status && item.ingestion_status !== status) return false;
            if (query && haystack(item).indexOf(query) === -1) return false;
            return true;
        });
    }

    function paintDetail(item) {
        var detail = document.getElementById("evidence-library-detail");
        if (!item) {
            if (detail) detail.dataset.evidenceId = "";
            text("evidence-detail-title", "No artifact selected");
            text("evidence-detail-status", "Select an artifact from the library.");
            text("evidence-detail-source", "");
            text("evidence-detail-dates", "");
            text("evidence-detail-notes", "");
            text("evidence-detail-classification", "");
            text("evidence-detail-links", "");
            document.dispatchEvent(new CustomEvent("evidence-library-selected", {detail: {evidenceId: "", artifactVersion: ""}}));
            clearPreview();
            return;
        }
        var version = (item.artifact_versions || [])[item.artifact_versions.length - 1] || {};
        var notes = notesFor(item);
        text("evidence-detail-title", item.original_filename || item.source_filename || item.evidence_id);
        text("evidence-detail-status", [
            "Status: " + (item.ingestion_status || "unknown"),
            item.prior_ingestion_status ? "Previous status: " + item.prior_ingestion_status : "",
            item.failure_code ? "Failure: " + item.failure_code : "",
            "Version: " + String(item.current_version || version.version || ""),
            "Integrity verified: " + (item.integrity_verified === true ? "yes" : "no"),
            "Recorded by: " + (item.actor_principal_id || "Not recorded")
        ].filter(Boolean).join("\n"));
        text("evidence-detail-source", [
            "Source file: " + (item.source_filename || "Not recorded"),
            "Original file: " + (item.original_filename || "Not recorded"),
            "Media type: " + (item.media_type || "Not recorded")
        ].join("\n"));
        text("evidence-detail-dates", [
            "Source date: " + recorded(item.source_date || item.received_at),
            "Version date: " + recorded(version.recorded_at || item.version_date),
            "Catalog read: " + (readAt || "Not recorded")
        ].join("\n"));
        text("evidence-detail-notes", notes.length ? notes.map(function (note) {
            var author = note.actor_principal_id || note.author || "unattributed";
            return author + ": " + (note.note || note.text || "");
        }).join("\n") : "No attributed note is stored for this artifact.");
        text("evidence-detail-classification", QUALITIES.map(function (name) {
            var value = item[name] || (item.legal && item.legal[name]) || "not_recorded";
            return name + ": " + value;
        }).join("\n") + "\nClassification is not verified support or governing law.");
        document.dispatchEvent(new CustomEvent("evidence-library-selected", {
            detail: {
                evidenceId: item.evidence_id || "",
                artifactVersion: item.current_version || (version && version.version) || ""
            }
        }));
        var links = linksFor(item);
        text("evidence-detail-links", links.length ? links.join("\n") : "No current complaint link.");
        if (detail) detail.dataset.evidenceId = item.evidence_id || "";
        loadPreview(item);
    }

    function render() {
        var host = root();
        var list = document.getElementById("evidence-library-list");
        if (!host || !list || host.dataset.state !== "ready") return;
        if (!currentScope(itemsScope)) {
            var current = captureScope();
            var previous = itemsScope;
            var requestedSelection = selectedId;
            clearPrivateState();
            if (sameIdentity(previous, current)) {
                selectedId = requestedSelection;
                load(1);
            }
            return;
        }
        layout();
        var shown = visibleItems();
        list.textContent = "";
        if (!shown.length) {
            var empty = document.createElement("p");
            empty.id = "evidence-library-filter-empty";
            empty.textContent = items.length
                ? "No artifacts match this search or status. Clear filters to see the catalog again."
                : "The catalog has no artifacts.";
            list.appendChild(empty);
        }
        shown.forEach(function (item) {
            var button = document.createElement("button");
            button.type = "button";
            button.className = "evidence-library-item";
            button.setAttribute("role", "option");
            button.setAttribute("data-evidence-id", item.evidence_id || "");
            button.setAttribute("aria-pressed", item.evidence_id === selectedId ? "true" : "false");
            var title = document.createElement("strong");
            title.textContent = item.original_filename || item.source_filename || item.evidence_id;
            var meta = document.createElement("small");
            meta.textContent = (item.ingestion_status || "unknown") + " · " + (item.source_filename || "source not recorded");
            button.appendChild(title);
            button.appendChild(meta);
            button.addEventListener("click", function () {
                selectedId = item.evidence_id || "";
                host.dataset.selectedId = selectedId;
                if (host.dataset.layout === "list-detail") host.dataset.pane = "detail";
                render();
            });
            list.appendChild(button);
        });
        var selected = items.filter(function (item) { return item.evidence_id === selectedId; })[0] || null;
        if (!selected && shown[0] && !selectedId) {
            selected = shown[0];
            selectedId = selected.evidence_id || "";
            host.dataset.selectedId = selectedId;
            var first = list.querySelector("[data-evidence-id]");
            if (first) first.setAttribute("aria-pressed", "true");
        }
        host.dataset.selectedId = selected ? selected.evidence_id : "";
        paintDetail(selected);
        text("evidence-library-summary", items.length
            ? (shown.length + " of " + items.length + " artifacts shown.")
            : "No artifacts are in this case catalog.");
    }

    function setState(state, detail) {
        var host = root();
        if (!host) return;
        host.dataset.state = state;
        show("evidence-library-empty", state === "empty");
        show("evidence-library-error", state === "error");
        show("evidence-library-locked", state === "locked");
        show("evidence-library-body", state === "ready");
        if (state === "error") text("evidence-library-error-detail", detail || "The catalog request failed. The previous selection is kept.");
        if (state === "locked") text("evidence-library-locked-detail", detail || "Unlock the case key or open an authorized case, then refresh. Locked evidence is not shown.");
        if (state !== "ready" && detail) text("evidence-library-summary", detail);
    }

    async function load(rescopeCount) {
        var host = root();
        if (!host) return;
        rescopeCount = rescopeCount === 1 ? 1 : 0;
        var scope = captureScope();
        if (itemsScope && !currentScope(itemsScope)) {
            var previous = itemsScope;
            var requestedSelection = selectedId;
            clearPrivateState();
            if (sameIdentity(previous, scope)) selectedId = requestedSelection;
        }
        var token = ++generation;
        var context = caseContext();
        if (!scope || !context) {
            clearPrivateState();
            setState("locked", "Select an authorized case before opening its evidence library.");
            return;
        }
        itemsScope = scope;
        var params = new URLSearchParams({
            tenant_id: context.tenant_id,
            case_id: context.case_id,
            resource_id: context.resource_id
        });
        var response;
        try {
            response = await fetch("/api/cases/evidence?" + params.toString(), {
                credentials: "same-origin",
                headers: {"Accept": "application/json"}
            });
        } catch (error) {
            if (!currentRead(token, scope, rescopeCount)) return;
            setState("error", "The catalog request did not reach the server. Try again.");
            return;
        }
        if (!currentRead(token, scope, rescopeCount)) return;
        var body = {};
        try { body = await response.json(); } catch (error) { body = {}; }
        if (!currentRead(token, scope, rescopeCount)) return;
        if (response.status === 401 || response.status === 403 || body.error === "key_unavailable" || body.error === "not_owner" || body.error === "unauthenticated") {
            items = [];
            selectedId = host.dataset.selectedId || selectedId;
            var list = document.getElementById("evidence-library-list");
            if (list) list.textContent = "";
            setState("locked", response.status === 403
                ? "This account cannot open the evidence catalog for the selected case."
                : "The case key or session cannot open the evidence catalog. Refresh after access returns.");
            clearPreview();
            paintDetail(null);
            return;
        }
        if (!response.ok || body.error) {
            setState("error", "The catalog returned " + (body.error || response.status) + ". Try the catalog again.");
            return;
        }
        items = Array.isArray(body.items) ? body.items : [];
        readAt = new Date().toISOString();
        window.dispatchEvent(new CustomEvent("complaint-evidence-catalog", {detail: {items: items}}));
        host.dataset.catalogRead = readAt;
        if (selectedId && !items.some(function (item) { return item.evidence_id === selectedId; })) selectedId = "";
        if (!items.length) {
            selectedId = "";
            host.dataset.selectedId = "";
            setState("empty");
            text("evidence-library-summary", "No artifacts are in this case catalog.");
            paintDetail(null);
            return;
        }
        setState("ready");
        render();
    }

    function bind() {
        var host = root();
        if (!host || host.dataset.bound === "true") return;
        host.dataset.bound = "true";
        ensurePreview();
        layout();
        document.getElementById("evidence-library-search").addEventListener("input", render);
        document.getElementById("evidence-library-status-filter").addEventListener("change", render);
        document.getElementById("evidence-library-refresh").addEventListener("click", function () { load(); });
        document.getElementById("evidence-library-retry").addEventListener("click", function () { load(); });
        document.getElementById("evidence-library-unlock").addEventListener("click", function () { load(); });
        document.getElementById("evidence-library-clear").addEventListener("click", function () {
            document.getElementById("evidence-library-search").value = "";
            document.getElementById("evidence-library-status-filter").value = "";
            render();
        });
        document.getElementById("evidence-library-add").addEventListener("click", function () {
            var input = document.getElementById("evidence-attachment");
            if (input) input.focus();
        });
        document.getElementById("evidence-library-show-list").addEventListener("click", function () {
            layout();
            host.dataset.pane = "list";
        });
        document.getElementById("evidence-library-show-detail").addEventListener("click", function () {
            layout();
            if (host.dataset.layout === "list-detail") host.dataset.pane = "detail";
        });
        window.addEventListener("resize", layout);
        var tab = document.querySelector("[data-tab-target='evidence']");
        if (tab) tab.addEventListener("click", function () { load(); });
    }

    window.complaintEvidenceLibrary = {
        refresh: load,
        clearPrivateState: clearPrivateState,
        selectedId: function () { return selectedId; }
    };
    if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", bind);
    else bind();
}());

/* Label, annotation, and reminder editors.
   Saves go to the case evidence annotation API. A date the user marks is an
   attributed reminder unless admitted source, jurisdiction, date, version,
   and review are all present. The client does not derive a filing deadline. */
(function () {
    var mode = "label";
    var trigger = null;
    var catalog = [];
    var listed = [];
    var observedAt = "";

    function dialog() { return document.getElementById("evidence-annotation-editor"); }
    function form() { return document.getElementById("evidence-annotation-form"); }
    function node(id) { return document.getElementById(id); }

    function caseContext() {
        var client = window.workspaceClient;
        return client && client.caseContext ? client.caseContext : null;
    }

    function caseRevision(context) {
        var value = context.expected_revision;
        if (value === undefined || value === null || value === "") value = context.revision;
        return value;
    }

    function headers() {
        var client = window.workspaceClient;
        var context = caseContext();
        var result = {"Content-Type": "application/json", "Accept": "application/json"};
        if (context) {
            result["x-tenant-id"] = context.tenant_id;
            result["x-case-id"] = context.case_id;
            result["x-resource-id"] = context.resource_id;
        }
        if (client && client.csrfToken) result["x-csrf-token"] = client.csrfToken;
        return result;
    }

    function setState(state, message) {
        var status = node("evidence-annotation-editor-state");
        var root = dialog();
        if (status) {
            status.dataset.saveState = state;
            status.textContent = message;
        }
        if (root) root.dataset.saveState = state;
        var save = node("evidence-annotation-save");
        if (save) save.disabled = state === "pending";
    }

    function focusable() {
        var root = dialog();
        if (!root) return [];
        return Array.prototype.filter.call(root.querySelectorAll("input, select, textarea, button"), function (element) {
            return !element.disabled && !element.closest("[hidden]");
        });
    }

    function focusEditor() {
        var preferred = mode === "annotation"
            ? "evidence-annotation-note"
            : mode === "reminder"
                ? "evidence-annotation-reminder-date"
                : "evidence-annotation-label";
        var field = node(preferred);
        var evidence = node("evidence-annotation-evidence");
        var target = evidence && !evidence.value ? evidence : field;
        if (target) target.focus();
    }

    function onKey(event) {
        if (event.key === "Escape") {
            event.preventDefault();
            close();
            return;
        }
        if (event.key !== "Tab") return;
        var nodes = focusable();
        if (!nodes.length) return;
        var first = nodes[0];
        var last = nodes[nodes.length - 1];
        if (event.shiftKey && document.activeElement === first) {
            event.preventDefault();
            last.focus();
        } else if (!event.shiftKey && document.activeElement === last) {
            event.preventDefault();
            first.focus();
        }
    }

    function panels() {
        Array.prototype.forEach.call(document.querySelectorAll("[data-editor-panel]"), function (panel) {
            panel.hidden = panel.getAttribute("data-editor-panel") !== mode;
        });
        var title = node("evidence-annotation-editor-title");
        var note = node("evidence-annotation-editor-kind-note");
        if (mode === "label") {
            if (title) title.textContent = "Add label";
            if (note) note.textContent = "A label is an attributed note on this artifact version. It does not adopt the note as evidence.";
        } else if (mode === "annotation") {
            if (title) title.textContent = "Add annotation";
            if (note) note.textContent = "Save a note, or a note with a page and span, on the selected artifact version.";
        } else {
            if (title) title.textContent = "Mark an attributed reminder";
            if (note) note.textContent = "A date you mark here is your reminder. It is not a filing deadline and it is not a legal requirement unless you supply admitted source, jurisdiction, date, version, and review.";
        }
    }

    function selectedVersion() {
        var select = node("evidence-annotation-version");
        var value = select ? Number(select.value) : NaN;
        return Number.isInteger(value) && value >= 1 ? value : null;
    }

    function fillVersions() {
        var evidenceId = node("evidence-annotation-evidence").value;
        var item = catalog.filter(function (entry) { return entry.evidence_id === evidenceId; })[0];
        var select = node("evidence-annotation-version");
        var versions = item && Array.isArray(item.artifact_versions) ? item.artifact_versions : [];
        select.textContent = "";
        versions.forEach(function (version) {
            var number = Number(version && version.version);
            if (!Number.isInteger(number)) return;
            var option = document.createElement("option");
            option.value = String(number);
            option.textContent = "version " + number;
            select.appendChild(option);
        });
        if (!select.options.length) {
            var missing = document.createElement("option");
            missing.value = "";
            missing.textContent = "No artifact version";
            select.appendChild(missing);
        }
    }

    function scopeQuery() {
        var context = caseContext();
        if (!context) return null;
        var evidenceId = node("evidence-annotation-evidence").value;
        var version = selectedVersion();
        if (!evidenceId || version === null) return null;
        return new URLSearchParams({
            tenant_id: context.tenant_id,
            case_id: context.case_id,
            resource_id: context.resource_id,
            evidence_id: evidenceId,
            artifact_version: String(version),
            expected_case_revision: String(caseRevision(context))
        });
    }

    function reminderClass(note) {
        var text = String(note || "");
        if (text.indexOf("record_class: reviewed_lineage_claim") === 0) return "reviewed";
        if (text.indexOf("record_class: attributed_reminder") === 0) return "reminder";
        return "";
    }

    function paintSaved() {
        var list = node("evidence-annotation-saved");
        var docket = node("docket-annotation-list");
        if (!list) return;
        list.textContent = "";
        if (!listed.length) {
            var empty = document.createElement("li");
            empty.textContent = "No annotations saved on this artifact version yet.";
            list.appendChild(empty);
        }
        listed.forEach(function (item) {
            var row = document.createElement("li");
            row.tabIndex = -1;
            row.dataset.annotationId = item.annotation_id || "";
            var title = document.createElement("strong");
            var kind = reminderClass(item.note);
            if (item.kind === "label") title.textContent = "Label: " + (item.label || "");
            else if (kind === "reminder") title.textContent = "Attributed reminder";
            else if (kind === "reviewed") title.textContent = "Reviewed lineage claim";
            else if (item.kind === "page_span") title.textContent = "Annotation " + (item.anchor || "");
            else title.textContent = "Annotation";
            var body = document.createElement("div");
            body.textContent = item.kind === "label" ? "" : (item.note || "");
            var meta = document.createElement("div");
            meta.textContent = "Author: " + (item.actor_principal_id || "unknown")
                + ". Artifact version: " + item.artifact_version
                + ". Annotation revision: " + (item.annotation_revision || form().dataset.expectedRevision || "")
                + ". Record time: not provided by the annotation API."
                + (observedAt ? " Browser observed the list at " + observedAt + "." : "");
            if (kind === "reminder") {
                var limit = document.createElement("div");
                limit.textContent = "This reminder is not a filing deadline and it is not a legal requirement.";
                row.appendChild(limit);
            }
            if (kind === "reviewed") {
                var claim = document.createElement("div");
                claim.textContent = "The admitted source, jurisdiction, date, and version were recorded with review. The system did not derive this claim.";
                row.appendChild(claim);
            }
            row.appendChild(title);
            if (body.textContent) row.appendChild(body);
            row.appendChild(meta);
            list.appendChild(row);
        });
        if (docket) {
            docket.textContent = "";
            var source = list.textContent || "No annotations saved on this artifact version yet.";
            var copy = document.createElement("div");
            copy.className = "item";
            copy.textContent = source;
            docket.appendChild(copy);
        }
    }

    async function refreshList() {
        var params = scopeQuery();
        var current = form();
        if (!params || !current) return;
        var response = await fetch("/api/cases/evidence/annotations?" + params.toString(), {
            credentials: "same-origin",
            headers: headers()
        });
        var body = {};
        try { body = await response.json(); } catch (error) { body = {}; }
        if (!response.ok) {
            setState("error", "The annotation list returned " + (body.error || response.status) + ".");
            return;
        }
        listed = Array.isArray(body.items) ? body.items : [];
        current.dataset.expectedRevision = typeof body.annotation_revision === "string" ? body.annotation_revision : "";
        observedAt = new Date().toISOString();
        paintSaved();
    }

    async function loadCatalog(preferredId, preferredVersion) {
        var context = caseContext();
        var select = node("evidence-annotation-evidence");
        select.textContent = "";
        catalog = [];
        if (!context) {
            setState("locked", "Select an authorized case before editing labels, annotations, or reminders.");
            return;
        }
        var params = new URLSearchParams({
            tenant_id: context.tenant_id,
            case_id: context.case_id,
            resource_id: context.resource_id
        });
        var response = await fetch("/api/cases/evidence?" + params.toString(), {
            credentials: "same-origin",
            headers: {"Accept": "application/json"}
        });
        var body = {};
        try { body = await response.json(); } catch (error) { body = {}; }
        if (response.status === 401 || response.status === 403) {
            setState("locked", "The case key or session cannot open evidence annotations.");
            return;
        }
        if (!response.ok) {
            setState("error", "The evidence catalog returned " + (body.error || response.status) + ".");
            return;
        }
        catalog = Array.isArray(body.items) ? body.items : [];
        if (!catalog.length) {
            var empty = document.createElement("option");
            empty.value = "";
            empty.textContent = "No sealed evidence in this case";
            select.appendChild(empty);
            setState("empty", "Save sealed evidence before adding a label, annotation, or reminder.");
            return;
        }
        catalog.forEach(function (item) {
            var option = document.createElement("option");
            option.value = item.evidence_id;
            option.textContent = item.original_filename || item.source_filename || item.evidence_id;
            select.appendChild(option);
        });
        if (preferredId && catalog.some(function (item) { return item.evidence_id === preferredId; })) select.value = preferredId;
        fillVersions();
        var versionSelect = node("evidence-annotation-version");
        if (preferredVersion && Array.prototype.some.call(versionSelect.options, function (option) {
            return option.value === String(preferredVersion);
        })) versionSelect.value = String(preferredVersion);
        setState("pending", "Loading saved annotations.");
        await refreshList();
        if (dialog().dataset.saveState !== "error") {
            setState("idle", "Editor ready. Nothing is saved until you use Save.");
        }
    }

    function lineage() {
        return {
            source: node("evidence-annotation-lineage-source").value.trim(),
            jurisdiction: node("evidence-annotation-lineage-jurisdiction").value.trim(),
            date: node("evidence-annotation-lineage-date").value.trim(),
            version: node("evidence-annotation-lineage-version").value.trim(),
            reviewed: node("evidence-annotation-lineage-reviewed").checked,
            claim: node("evidence-annotation-claim-filing-deadline").checked
        };
    }

    function buildPayload() {
        var context = caseContext();
        var evidenceId = node("evidence-annotation-evidence").value;
        var version = selectedVersion();
        if (!context) return {error: "Select an authorized case first.", focus: "evidence-annotation-evidence"};
        if (!evidenceId || version === null) return {error: "Choose a sealed evidence artifact and version.", focus: "evidence-annotation-evidence"};
        var payload = {
            tenant_id: context.tenant_id,
            case_id: context.case_id,
            resource_id: context.resource_id,
            evidence_id: evidenceId,
            artifact_version: version,
            expected_case_revision: caseRevision(context),
            expected_annotation_revision: form().dataset.expectedRevision || "",
            idempotency_key: "ann-" + Date.now().toString(36) + "-" + Math.random().toString(36).slice(2, 10)
        };
        if (mode === "label") {
            var label = node("evidence-annotation-label").value.trim();
            if (!label || label.length > 80) return {error: "Enter a label of 1 to 80 characters.", focus: "evidence-annotation-label"};
            payload.kind = "label";
            payload.label = label;
            payload.note = "";
            return {payload: payload};
        }
        if (mode === "annotation") {
            var note = node("evidence-annotation-note").value.trim();
            var pageRaw = node("evidence-annotation-page").value.trim();
            var startRaw = node("evidence-annotation-span-start").value.trim();
            var endRaw = node("evidence-annotation-span-end").value.trim();
            if (!note) return {error: "Enter the annotation note.", focus: "evidence-annotation-note"};
            var hasSpan = pageRaw !== "" || startRaw !== "" || endRaw !== "";
            if (!hasSpan) {
                payload.kind = "comment";
                payload.note = note;
                payload.label = "";
                return {payload: payload};
            }
            var page = Number(pageRaw);
            var start = Number(startRaw);
            var end = Number(endRaw);
            if (!Number.isInteger(page) || page < 1 || !Number.isInteger(start) || start < 0 || !Number.isInteger(end) || end <= start) {
                return {error: "A page span needs a page, a start, and an end after the start.", focus: "evidence-annotation-page"};
            }
            payload.kind = "page_span";
            payload.note = note;
            payload.label = "";
            payload.page = page;
            payload.span_start = start;
            payload.span_end = end;
            return {payload: payload};
        }
        var when = node("evidence-annotation-reminder-date").value.trim();
        var reminderNote = node("evidence-annotation-reminder-note").value.trim();
        if (!when) return {error: "Choose the reminder date.", focus: "evidence-annotation-reminder-date"};
        if (!reminderNote) return {error: "Enter what this reminder is for.", focus: "evidence-annotation-reminder-note"};
        var admitted = lineage();
        if (admitted.claim) {
            var missing = !admitted.source ? "evidence-annotation-lineage-source"
                : !admitted.jurisdiction ? "evidence-annotation-lineage-jurisdiction"
                : !admitted.date ? "evidence-annotation-lineage-date"
                : !admitted.version ? "evidence-annotation-lineage-version"
                : !admitted.reviewed ? "evidence-annotation-lineage-reviewed"
                : "";
            if (missing) {
                return {
                    error: "A filing deadline or legal requirement needs admitted source, jurisdiction, date, version, and review. Nothing was saved.",
                    focus: missing
                };
            }
            payload.note = [
                "record_class: reviewed_lineage_claim",
                "when: " + when,
                "text: " + reminderNote,
                "admitted_source: " + admitted.source,
                "jurisdiction: " + admitted.jurisdiction,
                "authority_date: " + admitted.date,
                "authority_version: " + admitted.version,
                "reviewed: true",
                "system_derived_filing_deadline: false",
                "legal_requirement_derived: false"
            ].join("\n");
        } else {
            payload.note = [
                "record_class: attributed_reminder",
                "when: " + when,
                "text: " + reminderNote,
                "filing_deadline: false",
                "legal_requirement: false",
                "system_derived_filing_deadline: false"
            ].join("\n");
        }
        payload.kind = "comment";
        payload.label = "";
        return {payload: payload};
    }

    async function save(event) {
        event.preventDefault();
        if (dialog() && dialog().dataset.saveState === "pending") return;
        var built = buildPayload();
        if (built.error) {
            setState("error", built.error);
            var field = node(built.focus);
            if (field) field.focus();
            return;
        }
        setState("pending", "Saving through the evidence annotation API.");
        var response;
        try {
            response = await fetch("/api/cases/evidence/annotations", {
                method: "POST",
                credentials: "same-origin",
                headers: headers(),
                body: JSON.stringify(built.payload)
            });
        } catch (error) {
            setState("error", "The annotation request did not reach the server. Nothing was saved.");
            node("evidence-annotation-editor-state").focus();
            return;
        }
        var body = {};
        try { body = await response.json(); } catch (error) { body = {}; }
        if (response.status === 409 || body.error === "revision_conflict") {
            await refreshList().catch(function () { return null; });
            setState("conflict", "Someone saved this artifact version first. The editor loaded the current revision. Review it, then save again.");
            node("evidence-annotation-editor-state").focus();
            return;
        }
        if (!response.ok) {
            setState("error", "The annotation API returned " + (body.error || response.status) + ". Nothing new was saved.");
            node("evidence-annotation-editor-state").focus();
            return;
        }
        form().dataset.expectedRevision = body.annotation_revision || form().dataset.expectedRevision || "";
        await refreshList();
        setState("saved", "Saved " + (body.annotation_id || "annotation") + " by " + (body.actor_principal_id || "the session actor") + " on artifact version " + body.artifact_version + ", revision " + (body.annotation_revision || "") + ".");
        var saved = node("evidence-annotation-saved").querySelector("[data-annotation-id='" + body.annotation_id + "']");
        if (saved) saved.focus();
        else node("evidence-annotation-editor-state").focus();
    }

    function close() {
        var root = dialog();
        if (root && root.open) root.close();
        if (trigger && typeof trigger.focus === "function") trigger.focus();
    }

    async function open(options) {
        options = options || {};
        mode = options.mode === "annotation" || options.mode === "reminder" ? options.mode : "label";
        trigger = options.trigger || document.activeElement;
        var root = dialog();
        if (!root || !form()) return;
        panels();
        setState("pending", "Loading the evidence catalog and saved annotations.");
        if (!root.open) root.showModal();
        try {
            await loadCatalog(options.evidenceId || "", options.artifactVersion || "");
        } catch (error) {
            setState("error", "The editor could not reach the evidence annotation API.");
        }
        if (root.dataset.saveState !== "error" && root.dataset.saveState !== "locked" && root.dataset.saveState !== "empty") {
            setState(root.dataset.saveState || "idle", node("evidence-annotation-editor-state").textContent);
        }
        focusEditor();
    }

    function bind() {
        var root = dialog();
        var current = form();
        if (!root || !current || root.dataset.bound === "true") return;
        root.dataset.bound = "true";
        root.addEventListener("keydown", onKey);
        current.addEventListener("submit", function (event) {
            save(event).catch(function () { setState("error", "The save stopped before the annotation API answered."); });
        });
        node("evidence-annotation-close").addEventListener("click", close);
        node("evidence-annotation-evidence").addEventListener("change", function () {
            fillVersions();
            refreshList().catch(function () { setState("error", "The annotation list could not be loaded."); });
        });
        node("evidence-annotation-version").addEventListener("change", function () {
            refreshList().catch(function () { setState("error", "The annotation list could not be loaded."); });
        });
        node("evidence-annotation-editor-state").tabIndex = -1;
    }

    window.complaintEvidenceAnnotations = {open: open, close: close};
    if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", bind);
    else bind();
}());

/* Classification choices follow the current case context.
   Fixed retaliation or HR claim elements are not a menu. A user label, an
   AI suggestion, and a reviewed acceptance stay different records. Unknown
   legal context stays unknown. */
(function () {
    var FIXED = {
        protected_activity: true,
        employer_knowledge: true,
        causation: true,
        hr: true,
        human_resources: true
    };
    var shownId = "";
    var generation = 0;

    function caseContext() {
        var client = window.workspaceClient;
        return client && client.caseContext ? client.caseContext : null;
    }

    function headers() {
        var client = window.workspaceClient;
        var context = caseContext();
        var result = {"Content-Type": "application/json", "Accept": "application/json"};
        if (context) {
            result["x-tenant-id"] = context.tenant_id;
            result["x-case-id"] = context.case_id;
            result["x-resource-id"] = context.resource_id;
            if (context.expected_revision) result["x-expected-revision"] = String(context.expected_revision);
        }
        if (client && client.csrfToken) result["x-csrf-token"] = client.csrfToken;
        return result;
    }

    function panel() {
        var host = document.getElementById("evidence-detail-classification");
        if (!host || !host.parentNode) return null;
        var existing = document.getElementById("evidence-classification-panel");
        if (existing) return existing;
        var root = document.createElement("div");
        root.id = "evidence-classification-panel";
        root.dataset.state = "empty";
        root.innerHTML = ""
            + "<p id=\"evidence-classification-status\"></p>"
            + "<div id=\"evidence-classification-choices\"></div>"
            + "<label for=\"evidence-classification-label\">Your label</label>"
            + "<input id=\"evidence-classification-label\" type=\"text\" maxlength=\"80\" autocomplete=\"off\">"
            + "<button type=\"button\" id=\"evidence-classification-save-label\">Save label</button>"
            + "<button type=\"button\" id=\"evidence-classification-save-choice\">Record selected choice as my label</button>"
            + "<button type=\"button\" id=\"evidence-classification-accept\">Record reviewed acceptance</button>"
            + "<p id=\"evidence-classification-user-labels\"></p>"
            + "<p id=\"evidence-classification-suggestions\"></p>"
            + "<p id=\"evidence-classification-reviewed\"></p>"
            + "<p id=\"evidence-classification-retired\"></p>"
            + "<p id=\"evidence-classification-error\"></p>";
        host.parentNode.appendChild(root);
        document.getElementById("evidence-classification-save-label").addEventListener("click", function () {
            saveLabel().catch(function () { setState("error", "The label was not saved."); });
        });
        document.getElementById("evidence-classification-save-choice").addEventListener("click", function () {
            saveChoice().catch(function () { setState("error", "The selected choice was not saved."); });
        });
        document.getElementById("evidence-classification-accept").addEventListener("click", function () {
            acceptSuggestion().catch(function () { setState("error", "The acceptance was not saved."); });
        });
        return root;
    }

    function text(id, value) {
        var node = document.getElementById(id);
        if (node) node.textContent = value;
    }

    function setState(state, detail) {
        var root = panel();
        if (!root) return;
        root.dataset.state = state;
        text("evidence-classification-status", detail || "");
        if (state === "error") text("evidence-classification-error", detail || "Classification choices could not be loaded.");
        else text("evidence-classification-error", "");
    }

    function selectedChoice() {
        var picked = document.querySelector("#evidence-classification-choices input[name='evidence-classification-choice']:checked");
        if (!picked) return null;
        return {
            id: picked.value,
            kind: picked.getAttribute("data-target-kind") || "",
            label: picked.getAttribute("data-label") || picked.value
        };
    }

    function selectedSuggestion() {
        var picked = document.querySelector("#evidence-classification-suggestions input[name='evidence-classification-suggestion']:checked");
        if (!picked) return null;
        return {id: picked.value, targetId: picked.getAttribute("data-target-id") || ""};
    }

    async function readJson(url, options) {
        var response = await fetch(url, options);
        var body = {};
        try { body = await response.json(); } catch (error) { body = {}; }
        return {response: response, body: body};
    }

    async function caseContextSnapshot() {
        var context = caseContext();
        var snapshot = {
            legal_context_status: "unknown",
            context_owner: "request",
            factual_graph_revision: "",
            source_version: "",
            jurisdiction: "",
            authority_version: "",
            factual_gaps: [],
            admitted_requirements: []
        };
        if (!context || !context.case_id) return snapshot;
        var factual;
        var legal;
        try {
            factual = await readJson("/api/graphs/" + encodeURIComponent(context.case_id) + "/factual?case_id=" + encodeURIComponent(context.case_id), {
                credentials: "same-origin",
                headers: headers()
            });
        } catch (error) {
            factual = null;
        }
        try {
            legal = await readJson("/api/legal-analysis/" + encodeURIComponent(context.case_id) + "/dependency-requirements?case_id=" + encodeURIComponent(context.case_id), {
                credentials: "same-origin",
                headers: headers()
            });
        } catch (error) {
            legal = null;
        }
        if (factual && factual.response && factual.response.ok && factual.body) {
            snapshot.factual_graph_revision = String(factual.body.private_revision || factual.body.graph_revision || "");
            (factual.body.unresolved || []).forEach(function (item) {
                if (!item || typeof item !== "object") return;
                var gapId = String(item.graph_entity_id || item.gap_id || "");
                if (!gapId || FIXED[gapId.toLowerCase()]) return;
                snapshot.factual_gaps.push({gap_id: gapId, label: String(item.label || item.reason || gapId)});
            });
        }
        if (legal && legal.response && legal.response.ok && legal.body) {
            var requirements = Array.isArray(legal.body.requirements) ? legal.body.requirements : [];
            var admitted = legal.body.admitted_law === true && requirements.length > 0;
            if (admitted) {
                var first = requirements[0] || {};
                snapshot.legal_context_status = "admitted";
                snapshot.source_version = String(first.source_hash || first.authority_version || legal.body.private_revision || "");
                snapshot.jurisdiction = String(first.jurisdiction || "");
                snapshot.authority_version = String(first.authority_version || "");
                requirements.forEach(function (item) {
                    if (!item || item.admitted_law !== true) return;
                    var requirementId = String(item.requirement_id || item.passage_id || "");
                    if (!requirementId || FIXED[requirementId.toLowerCase()]) return;
                    snapshot.admitted_requirements.push({
                        requirement_id: requirementId,
                        passage_id: String(item.passage_id || requirementId),
                        label: String(item.name || item.citation || requirementId),
                        source_version: snapshot.source_version,
                        jurisdiction: snapshot.jurisdiction,
                        authority_version: snapshot.authority_version,
                        admitted_law: true
                    });
                });
                if (!snapshot.source_version || !snapshot.jurisdiction || !snapshot.authority_version || !snapshot.admitted_requirements.length) {
                    snapshot.legal_context_status = "unknown";
                    snapshot.admitted_requirements = [];
                }
            } else if (legal.body.status === "unresolved_research") {
                snapshot.legal_context_status = "unresolved";
            }
        }
        return snapshot;
    }

    function paintOffer(body) {
        var choices = document.getElementById("evidence-classification-choices");
        if (!choices) return;
        choices.textContent = "";
        var offered = Array.isArray(body.choices) ? body.choices : [];
        if (!offered.length) {
            var empty = document.createElement("p");
            empty.textContent = "No current factual gap or admitted legal requirement is available.";
            choices.appendChild(empty);
        }
        offered.forEach(function (choice) {
            if (!choice || FIXED[String(choice.choice_id || "").toLowerCase()]) return;
            var row = document.createElement("label");
            var input = document.createElement("input");
            input.type = "radio";
            input.name = "evidence-classification-choice";
            input.value = String(choice.choice_id || "");
            input.setAttribute("data-target-kind", String(choice.target_kind || ""));
            input.setAttribute("data-label", String(choice.label || choice.choice_id || ""));
            row.appendChild(input);
            var kind = choice.target_kind === "factual_gap"
                ? "Factual gap"
                : choice.target_kind === "legal_requirement"
                    ? "Admitted legal requirement"
                    : "Unknown legal context";
            row.appendChild(document.createTextNode(" " + kind + ": " + (choice.label || choice.choice_id)));
            choices.appendChild(row);
        });
        text("evidence-classification-user-labels", (body.user_labels || []).concat(body.annotation_user_labels || []).map(function (item) {
            return "User label by " + (item.actor_principal_id || "unattributed")
                + ": " + (item.label || "")
                + (item.target_id ? " target " + item.target_id : "");
        }).join("\n") || "No user label is stored.");
        text("evidence-classification-suggestions", (body.ai_suggestions || []).map(function (item) {
            return "AI suggestion " + item.classifier_id + " by model " + (item.model_id || "unattributed")
                + " invocation " + (item.invocation_id || "unattributed")
                + " for " + (item.target_id || "")
                + ". Accepted: " + (item.accepted === true ? "yes" : "no") + ".";
        }).join("\n") || "No AI suggestion is stored.");
        var suggestionHost = document.getElementById("evidence-classification-suggestions");
        (body.ai_suggestions || []).forEach(function (item) {
            if (!suggestionHost || item.status === "retired") return;
            var row = document.createElement("label");
            var input = document.createElement("input");
            input.type = "radio";
            input.name = "evidence-classification-suggestion";
            input.value = String(item.classifier_id || "");
            input.setAttribute("data-target-id", String(item.target_id || ""));
            row.appendChild(input);
            row.appendChild(document.createTextNode(" Select suggestion " + item.classifier_id));
            suggestionHost.appendChild(row);
        });
        text("evidence-classification-reviewed", (body.reviewed_acceptances || []).map(function (item) {
            return "Reviewed acceptance " + item.classifier_id + " by " + (item.actor_principal_id || "unattributed")
                + " of " + (item.prior_classifier_id || "none")
                + " target " + (item.target_id || "")
                + ". Legal support established: no.";
        }).join("\n") || "No reviewed acceptance is stored.");
        text("evidence-classification-retired", (body.retired || []).map(function (item) {
            return "Retired " + (item.origin || "choice") + " " + (item.classifier_id || "")
                + " by " + (item.actor_principal_id || "unattributed")
                + " target " + (item.target_id || item.label || "")
                + " reason " + (item.retired_reason || "stale")
                + (item.model_id ? " model " + item.model_id : "")
                + (item.invocation_id ? " invocation " + item.invocation_id : "");
        }).join("\n") || "No stale classification is retained.");
        var legal = body.legal_context_status || "unknown";
        setState("ready", legal === "admitted"
            ? "Choices are the current factual gaps and admitted legal requirements. They are not verified support."
            : legal === "unresolved"
                ? "Legal requirements are unresolved. Unknown legal context is not a statute."
                : "Legal context is unknown. Fixed claim elements are not offered.");
    }

    function scopeBody(extra) {
        var context = caseContext();
        var detail = document.getElementById("evidence-library-detail");
        var version = detail ? Number(detail.getAttribute("data-artifact-version") || "") : NaN;
        var body = {
            tenant_id: context.tenant_id,
            case_id: context.case_id,
            resource_id: context.resource_id,
            evidence_id: shownId,
            artifact_version: version,
            expected_case_revision: context.expected_revision || context.revision
        };
        Object.keys(extra || {}).forEach(function (key) { body[key] = extra[key]; });
        return body;
    }

    async function refresh() {
        var root = panel();
        var context = caseContext();
        var token = ++generation;
        if (!root) return;
        if (!context || !shownId) {
            setState("locked", "Select an authorized case and an artifact before classifying it.");
            return;
        }
        setState("pending", "Loading classification choices from the current case.");
        var snapshot;
        try {
            snapshot = await caseContextSnapshot();
        } catch (error) {
            snapshot = {legal_context_status: "unknown", factual_gaps: [], admitted_requirements: [], context_owner: "request"};
        }
        if (token !== generation) return;
        var result;
        try {
            result = await readJson("/api/cases/evidence/classifications/offer", {
                method: "POST",
                credentials: "same-origin",
                headers: headers(),
                body: JSON.stringify(scopeBody({case_context: snapshot}))
            });
        } catch (error) {
            setState("error", "Classification choices did not reach the server.");
            return;
        }
        if (token !== generation) return;
        if (!result.response.ok) {
            var code = result.body && result.body.error;
            if (code === "key_unavailable" || code === "unauthenticated") {
                setState("locked", "Unlock the case before loading classification choices.");
            } else {
                setState("error", "Classification choices returned " + (code || result.response.status) + ".");
            }
            return;
        }
        root.dataset.legalContext = result.body.legal_context_status || "unknown";
        root.dataset.fingerprint = result.body.context_fingerprint || "";
        paintOffer(result.body);
    }

    async function saveLabel() {
        var label = (document.getElementById("evidence-classification-label").value || "").trim();
        if (!label) {
            setState("error", "Enter a user label. A blank label is not a claim element.");
            document.getElementById("evidence-classification-label").focus();
            return;
        }
        setState("pending", "Saving the user label.");
        var snapshot = await caseContextSnapshot();
        var result = await readJson("/api/cases/evidence/classifications", {
            method: "POST",
            credentials: "same-origin",
            headers: headers(),
            body: JSON.stringify(scopeBody({
                origin: "user_label",
                label: label,
                case_context: snapshot,
                idempotency_key: "ux19-label-" + Date.now().toString(36) + "-" + Math.random().toString(36).slice(2, 8)
            }))
        });
        if (!result.response.ok) {
            setState("error", "The user label was refused (" + (result.body.error || result.response.status) + ").");
            return;
        }
        document.getElementById("evidence-classification-label").value = "";
        await refresh();
    }

    async function saveChoice() {
        var choice = selectedChoice();
        if (!choice || !choice.id || FIXED[choice.id.toLowerCase()]) {
            setState("error", "Select a current factual gap, admitted requirement, or unknown legal context.");
            return;
        }
        setState("pending", "Saving your label for the selected choice. This is not an AI suggestion or a reviewed acceptance.");
        var snapshot = await caseContextSnapshot();
        var result = await readJson("/api/cases/evidence/classifications", {
            method: "POST",
            credentials: "same-origin",
            headers: headers(),
            body: JSON.stringify(scopeBody({
                origin: "user_label",
                target_id: choice.id,
                label: choice.label,
                case_context: snapshot,
                idempotency_key: "ux19-choice-" + Date.now().toString(36) + "-" + Math.random().toString(36).slice(2, 8)
            }))
        });
        if (!result.response.ok) {
            setState("error", "The selected choice was refused (" + (result.body.error || result.response.status) + ").");
            return;
        }
        await refresh();
    }

    async function acceptSuggestion() {
        var suggestion = selectedSuggestion();
        if (!suggestion) {
            setState("error", "Select an AI suggestion before recording reviewed acceptance.");
            return;
        }
        setState("pending", "Recording reviewed acceptance. This does not establish legal support.");
        var snapshot = await caseContextSnapshot();
        var result = await readJson("/api/cases/evidence/classifications", {
            method: "POST",
            credentials: "same-origin",
            headers: headers(),
            body: JSON.stringify(scopeBody({
                origin: "reviewed_acceptance",
                target_id: suggestion.targetId,
                prior_classifier_id: suggestion.id,
                accept: true,
                case_context: snapshot,
                idempotency_key: "ux19-accept-" + Date.now().toString(36) + "-" + Math.random().toString(36).slice(2, 8)
            }))
        });
        if (!result.response.ok) {
            setState("error", "Reviewed acceptance was refused (" + (result.body.error || result.response.status) + ").");
            return;
        }
        await refresh();
    }

    function onSelected(event) {
        var detail = event.detail || {};
        shownId = detail.evidenceId || "";
        var host = document.getElementById("evidence-library-detail");
        if (host) host.setAttribute("data-artifact-version", detail.artifactVersion === undefined || detail.artifactVersion === null ? "" : String(detail.artifactVersion));
        refresh().catch(function () { setState("error", "Classification choices could not be loaded."); });
    }

    document.addEventListener("evidence-library-selected", onSelected);
    window.complaintEvidenceClassification = {refresh: refresh};
}());

/* Evidence span links cite a current fact or sourced requirement.
   Allegation, hypothesis, corroboration, contradiction, and unavailable
   stay distinct. A checkbox or classifier does not verify legal support. */
(function () {
    var shownId = "";
    var generation = 0;
    var latest = null;

    function caseContext() {
        var client = window.workspaceClient;
        return client && client.caseContext ? client.caseContext : null;
    }

    function headers() {
        var client = window.workspaceClient;
        var context = caseContext();
        var result = {"Content-Type": "application/json", "Accept": "application/json"};
        if (context) {
            result["x-tenant-id"] = context.tenant_id;
            result["x-case-id"] = context.case_id;
            result["x-resource-id"] = context.resource_id;
            if (context.expected_revision) result["x-expected-revision"] = String(context.expected_revision);
        }
        if (client && client.csrfToken) result["x-csrf-token"] = client.csrfToken;
        return result;
    }

    function text(id, value) {
        var node = document.getElementById(id);
        if (node) node.textContent = value || "";
    }

    function setState(state, detail) {
        var root = document.getElementById("evidence-support-panel");
        if (root) root.dataset.state = state;
        text("evidence-support-status", detail || "");
        if (state === "error") text("evidence-support-error", detail || "The support link was not recorded.");
        else text("evidence-support-error", "");
    }

    function panel() {
        var host = document.getElementById("evidence-detail-links");
        if (!host || !host.parentNode) return null;
        var existing = document.getElementById("evidence-support-panel");
        if (existing) return existing;
        var root = document.createElement("div");
        root.id = "evidence-support-panel";
        root.dataset.state = "empty";
        root.innerHTML = ""
            + "<p id=\"evidence-support-status\"></p>"
            + "<label for=\"evidence-support-target\">Current fact or sourced requirement</label>"
            + "<select id=\"evidence-support-target\"></select>"
            + "<label for=\"evidence-support-page\">Page</label>"
            + "<input id=\"evidence-support-page\" type=\"number\" min=\"1\" value=\"1\">"
            + "<label for=\"evidence-support-span-start\">Span start</label>"
            + "<input id=\"evidence-support-span-start\" type=\"number\" min=\"0\" value=\"0\">"
            + "<label for=\"evidence-support-span-end\">Span end</label>"
            + "<input id=\"evidence-support-span-end\" type=\"number\" min=\"1\" value=\"1\">"
            + "<label for=\"evidence-support-checkbox\"><input id=\"evidence-support-checkbox\" type=\"checkbox\"> I checked this box</label>"
            + "<button type=\"button\" id=\"evidence-support-checkbox-submit\">Submit the checkbox as support</button>"
            + "<button type=\"button\" id=\"evidence-support-allegation\">Record allegation</button>"
            + "<button type=\"button\" id=\"evidence-support-hypothesis\">Record hypothesis</button>"
            + "<button type=\"button\" id=\"evidence-support-corroboration\">Accept corroboration</button>"
            + "<button type=\"button\" id=\"evidence-support-contradiction\">Accept contradiction</button>"
            + "<p id=\"evidence-support-allegations\"></p>"
            + "<p id=\"evidence-support-hypotheses\"></p>"
            + "<p id=\"evidence-support-corroborations\"></p>"
            + "<p id=\"evidence-support-contradictions\"></p>"
            + "<p id=\"evidence-support-unavailable\"></p>"
            + "<p id=\"evidence-support-error\"></p>";
        host.parentNode.appendChild(root);
        document.getElementById("evidence-support-checkbox-submit").addEventListener("click", function () {
            submitCheckedBox().catch(function () { setState("error", "The checkbox was not accepted as support."); });
        });
        document.getElementById("evidence-support-allegation").addEventListener("click", function () {
            save("allegation", "human_statement", false).catch(function () { setState("error", "The allegation was not recorded."); });
        });
        document.getElementById("evidence-support-hypothesis").addEventListener("click", function () {
            save("hypothesis", "ai_suggested", false).catch(function () { setState("error", "The hypothesis was not recorded."); });
        });
        document.getElementById("evidence-support-corroboration").addEventListener("click", function () {
            save("corroboration", "human_acceptance", true).catch(function () { setState("error", "Corroboration was not accepted."); });
        });
        document.getElementById("evidence-support-contradiction").addEventListener("click", function () {
            save("contradiction", "human_acceptance", true).catch(function () { setState("error", "Contradiction was not accepted."); });
        });
        return root;
    }

    async function readJson(url, options) {
        var response = await fetch(url, options);
        var body = {};
        try { body = await response.json(); } catch (error) { body = {}; }
        return {response: response, body: body};
    }

    function numberValue(id) {
        var node = document.getElementById(id);
        var value = node ? Number(node.value) : NaN;
        return Number.isInteger(value) ? value : NaN;
    }

    function selectedTarget() {
        var node = document.getElementById("evidence-support-target");
        if (!node || !node.value) return null;
        var option = node.options[node.selectedIndex];
        return {id: node.value, kind: option ? option.getAttribute("data-kind") : "", label: option ? option.textContent : ""};
    }

    async function snapshot() {
        var context = caseContext();
        var result = {
            legal_context_status: "unknown",
            context_owner: "request",
            factual_graph_revision: "",
            source_version: "",
            jurisdiction: "",
            authority_version: "",
            factual_gaps: [],
            admitted_requirements: [],
            factual_assertions: []
        };
        if (!context || !context.case_id) return result;
        var factual = null;
        var legal = null;
        try {
            factual = await readJson("/api/graphs/" + encodeURIComponent(context.case_id) + "/factual?case_id=" + encodeURIComponent(context.case_id), {
                credentials: "same-origin", headers: headers()
            });
        } catch (error) { factual = null; }
        try {
            legal = await readJson("/api/legal-analysis/" + encodeURIComponent(context.case_id) + "/dependency-requirements?case_id=" + encodeURIComponent(context.case_id), {
                credentials: "same-origin", headers: headers()
            });
        } catch (error) { legal = null; }
        if (factual && factual.response && factual.response.ok && factual.body) {
            result.factual_graph_revision = String(factual.body.private_revision || factual.body.graph_revision || factual.body.graph_version || "");
            (factual.body.user_statements || []).forEach(function (item) {
                if (!item || item.activity_status !== "active" || item.authority_is_user_fact !== true) return;
                var assertionId = String(item.assertion_id || "");
                if (!assertionId || !result.factual_graph_revision) return;
                result.factual_assertions.push({
                    assertion_id: assertionId,
                    text: String(item.text || assertionId),
                    status: "current",
                    graph_revision: result.factual_graph_revision
                });
            });
        }
        if (legal && legal.response && legal.response.ok && legal.body && legal.body.admitted_law === true) {
            var requirements = Array.isArray(legal.body.requirements) ? legal.body.requirements : [];
            if (requirements.length) {
                var first = requirements[0] || {};
                result.legal_context_status = "admitted";
                result.source_version = String(first.source_hash || first.authority_version || "");
                result.jurisdiction = String(first.jurisdiction || "");
                result.authority_version = String(first.authority_version || "");
                requirements.forEach(function (item) {
                    if (!item || item.admitted_law !== true) return;
                    result.admitted_requirements.push({
                        requirement_id: String(item.requirement_id || item.passage_id || ""),
                        passage_id: String(item.passage_id || item.requirement_id || ""),
                        label: String(item.name || item.citation || item.requirement || item.requirement_id || ""),
                        source_version: result.source_version,
                        jurisdiction: result.jurisdiction,
                        authority_version: result.authority_version,
                        admitted_law: true
                    });
                });
            }
        }
        return result;
    }

    function scopeBody(extra) {
        var context = caseContext();
        var detail = document.getElementById("evidence-library-detail");
        var version = detail ? Number(detail.getAttribute("data-artifact-version") || "") : NaN;
        var body = {
            tenant_id: context.tenant_id,
            case_id: context.case_id,
            resource_id: context.resource_id,
            evidence_id: shownId,
            artifact_version: version,
            expected_case_revision: context.expected_revision || context.revision,
            page: numberValue("evidence-support-page"),
            span_start: numberValue("evidence-support-span-start"),
            span_end: numberValue("evidence-support-span-end")
        };
        Object.keys(extra || {}).forEach(function (key) { body[key] = extra[key]; });
        return body;
    }

    function paint(body) {
        latest = body;
        var select = document.getElementById("evidence-support-target");
        if (select) {
            var previous = select.value;
            select.innerHTML = "";
            var targets = (body.factual_assertions || []).map(function (item) {
                return {id: item.target_id, kind: "factual_assertion", label: "Fact: " + (item.label || item.target_id)};
            }).concat((body.sourced_requirements || []).map(function (item) {
                return {id: item.target_id, kind: "sourced_requirement", label: "Requirement: " + (item.label || item.target_id)};
            }));
            if (!targets.length) {
                var empty = document.createElement("option");
                empty.value = "";
                empty.textContent = "No current fact or sourced requirement";
                select.appendChild(empty);
            }
            targets.forEach(function (item) {
                var option = document.createElement("option");
                option.value = item.id;
                option.setAttribute("data-kind", item.kind);
                option.textContent = item.label;
                select.appendChild(option);
            });
            if (previous) select.value = previous;
        }
        function line(item) {
            return (item.posture || "link") + " " + (item.span_ref || "")
                + " version " + String(item.artifact_version || "")
                + " target " + (item.target_id || "")
                + " by " + (item.actor_principal_id || "unattributed")
                + " owner " + (item.canonical_owner_principal_id || "")
                + " fact " + (item.fact_id || "")
                + " accepted " + (item.explicit_acceptance ? "yes" : "no")
                + " verified legal support no";
        }
        text("evidence-support-allegations", (body.allegations || []).map(line).join("\n") || "No allegation is linked.");
        text("evidence-support-hypotheses", (body.hypotheses || []).map(line).join("\n") || "No hypothesis is linked.");
        text("evidence-support-corroborations", (body.corroborations || []).map(line).join("\n") || "No corroboration is accepted.");
        text("evidence-support-contradictions", (body.contradictions || []).map(line).join("\n") || "No contradiction is accepted.");
        text("evidence-support-unavailable", (body.unavailable || []).length
            ? (body.unavailable || []).map(line).join("\n")
            : "Unavailable support is not stored as a successful link.");
        var count = (body.factual_assertions || []).length + (body.sourced_requirements || []).length;
        setState("ready", count
            ? "Choose an exact page and span. Acceptance does not verify legal support."
            : "No current factual assertion or sourced requirement is available. Support stays unavailable.");
    }

    async function refresh() {
        var root = panel();
        var context = caseContext();
        var token = ++generation;
        if (!root) return;
        if (!context || !shownId) {
            setState("locked", "Select an authorized case and an artifact before linking support.");
            return;
        }
        setState("pending", "Loading current facts and sourced requirements.");
        var contextSnapshot = await snapshot();
        if (token !== generation) return;
        var result;
        try {
            result = await readJson("/api/cases/evidence/support-links/offer", {
                method: "POST", credentials: "same-origin", headers: headers(),
                body: JSON.stringify(scopeBody({case_context: contextSnapshot}))
            });
        } catch (error) {
            setState("error", "Support targets did not reach the server.");
            return;
        }
        if (token !== generation) return;
        if (!result.response.ok) {
            var code = result.body && result.body.error;
            if (code === "key_unavailable" || code === "unauthenticated") setState("locked", "Unlock the case before linking support.");
            else setState("error", "Support targets returned " + (code || result.response.status) + ".");
            return;
        }
        paint(result.body);
    }

    async function save(posture, origin, accept) {
        var target = selectedTarget();
        if (!target) {
            setState("unavailable", "No current factual assertion or sourced requirement is available.");
            text("evidence-support-unavailable", "Support is unavailable until a current fact or sourced requirement exists.");
            return;
        }
        var page = numberValue("evidence-support-page");
        var start = numberValue("evidence-support-span-start");
        var end = numberValue("evidence-support-span-end");
        if (!Number.isInteger(page) || !Number.isInteger(start) || !Number.isInteger(end) || end <= start) {
            setState("error", "Enter an exact page and span. A checkbox is not a span.");
            return;
        }
        setState("pending", "Recording " + posture + " against the exact span.");
        var contextSnapshot = await snapshot();
        var extra = {
            posture: posture,
            origin: origin,
            accept: accept,
            target_kind: target.kind,
            target_id: target.id,
            client_checkbox: false,
            verified_legal_support: false,
            establishes_legal_support: false,
            case_context: contextSnapshot,
            idempotency_key: "ux20-" + posture + "-" + Date.now().toString(36) + "-" + Math.random().toString(36).slice(2, 8)
        };
        if (origin === "ai_suggested") {
            extra.model_id = "workspace-ui";
            extra.invocation_id = "ui-" + Date.now().toString(36);
        }
        var result = await readJson("/api/cases/evidence/support-links", {
            method: "POST", credentials: "same-origin", headers: headers(),
            body: JSON.stringify(scopeBody(extra))
        });
        if (!result.response.ok) {
            setState("error", "The support link was refused (" + ((result.body && result.body.error) || result.response.status) + "). A checkbox or classifier does not verify legal support.");
            return;
        }
        if (result.body.posture === "unavailable" || result.body.operation_succeeded === false) {
            setState("unavailable", "Support is unavailable (" + (result.body.reason || "unavailable") + "). Nothing was verified.");
            text("evidence-support-unavailable", "Unavailable: " + (result.body.reason || "support was not recorded") + ". Verified legal support: no.");
            return;
        }
        await refresh();
    }

    async function submitCheckedBox() {
        setState("pending", "Sending the checkbox. It cannot verify legal support.");
        var contextSnapshot = await snapshot();
        var target = selectedTarget();
        var result = await readJson("/api/cases/evidence/support-links", {
            method: "POST", credentials: "same-origin", headers: headers(),
            body: JSON.stringify(scopeBody({
                posture: "corroboration",
                origin: "human_acceptance",
                accept: true,
                client_checkbox: true,
                verified_legal_support: true,
                target_kind: target ? target.kind : "factual_assertion",
                target_id: target ? target.id : "checkbox-target",
                case_context: contextSnapshot,
                idempotency_key: "ux20-checkbox-" + Date.now().toString(36)
            }))
        });
        if (result.response.ok && result.body && result.body.verified_legal_support === true) {
            setState("error", "The checkbox was incorrectly treated as verified support.");
            return;
        }
        setState("error", "A client checkbox does not mint verified legal support (" + ((result.body && result.body.error) || result.body.reason || result.response.status) + ").");
    }

    function onSelected(event) {
        var detail = event.detail || {};
        shownId = detail.evidenceId || "";
        refresh().catch(function () { setState("error", "Support targets could not be loaded."); });
    }

    document.addEventListener("evidence-library-selected", onSelected);
    window.complaintEvidenceSupport = {refresh: refresh};
}());

