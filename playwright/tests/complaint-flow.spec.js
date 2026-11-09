const fs = require('fs/promises');
const path = require('path');

const { test, expect } = require('@playwright/test');
const { installCommonMocks, documentGenerationResponse, reviewPayload } = require('./helpers/fixtures');

async function waitForWorkspaceReady(page, { requireIntakeVisible = true } = {}) {
  await expect(page.locator('body')).toContainText(/Unified Complaint Workspace/i, { timeout: 30000 });

  for (let attempt = 0; attempt < 2; attempt += 1) {
    try {
      const serverInfo = page.locator('#sdk-server-info');
      const workspaceStatus = page.locator('#workspace-status');
      await expect(workspaceStatus).toContainText(/synchronized|workspace ready|opened workspace|returned from|draft generated|intake answers saved|complaint readiness refreshed/i, { timeout: 20000 });
      const serverInfoText = await serverInfo.textContent();
      if (String(serverInfoText || '').trim()) {
        await expect(serverInfo).toContainText(/complaint-workspace-(mcp|mock)/i, { timeout: 5000 });
      }
      await expect(page.locator('body')).toHaveAttribute('data-workspace-hydrated', /ready|partial/, { timeout: 20000 });
      if (requireIntakeVisible) {
        await page.locator('[data-tab-target="intake"]').click();
        await expect(page.locator('#intake-party_name')).toBeVisible({ timeout: 10000 });
      }
      return;
    } catch (error) {
      if (attempt === 1) {
        throw error;
      }
      await page.reload({ waitUntil: 'networkidle' });
    }
  }
}

async function revealAllIntakeFields(page) {
  const toggle = page.locator('#intake-show-all-button');
  if (await toggle.count()) {
    const pressed = await toggle.getAttribute('aria-pressed');
    if (pressed !== 'true') {
      await toggle.click();
    }
  }
  await expect(page.locator('#intake-party_name')).toBeVisible({ timeout: 10000 });
}

async function fillIntakeWizardField(page, questionId, value) {
  if (questionId === 'court_header') {
    const courtDetails = page.locator('#intake-court-details');
    if (await courtDetails.count()) {
      await courtDetails.evaluate((node) => {
        node.open = true;
      });
    }
  } else {
    const step = page.locator(`[data-intake-step-target="${questionId}"]`);
    if (await step.count()) {
      await step.click();
    }
  }
  await page.locator(`#intake-${questionId}`).fill(value);
}

async function writeComplaintExportArtifact({
  routeUrl,
  markdownFilename,
  markdownText,
  pdfFilename,
  pdfBuffer,
  docxFilename,
  docxBuffer,
  uiSuggestionsExcerpt,
  claimType,
  draftStrategy,
  filingShapeScore,
  claimTypeAlignmentScore,
}) {
  const targetDir = String(process.env.COMPLAINT_UI_SCREENSHOT_DIR || '').trim();
  if (!targetDir) {
    return null;
  }
  await fs.mkdir(targetDir, { recursive: true });
  const metadataPath = path.join(targetDir, 'workspace-export-artifacts.json');
  const payload = {
    name: 'workspace-export-artifacts',
    artifact_type: 'complaint_export',
    url: routeUrl,
    title: 'Exported Complaint Artifacts',
    viewport: { width: 1440, height: 1200 },
    text_excerpt: String(markdownText || '').slice(0, 4000),
    screenshot_path: '',
    claim_type: claimType,
    draft_strategy: draftStrategy,
    filing_shape_score: filingShapeScore,
    claim_type_alignment_score: claimTypeAlignmentScore,
    markdown_filename: markdownFilename,
    markdown_excerpt: String(markdownText || '').slice(0, 2000),
    pdf_filename: pdfFilename,
    pdf_header: Buffer.from(pdfBuffer || []).subarray(0, 16).toString('latin1'),
    docx_filename: docxFilename,
    docx_header: Buffer.from(docxBuffer || []).subarray(0, 16).toString('latin1'),
    ui_suggestions_excerpt: String(uiSuggestionsExcerpt || '').slice(0, 1000),
  };
  await fs.writeFile(metadataPath, JSON.stringify(payload, null, 2));
  return metadataPath;
}

async function writeUiScreenshotArtifact(page, { name, title, locator = 'body', fullPage = false, maxHeight = 0 }) {
  const targetDir = String(process.env.COMPLAINT_UI_SCREENSHOT_DIR || '').trim();
  if (!targetDir) {
    return null;
  }
  await fs.mkdir(targetDir, { recursive: true });
  const screenshotPath = path.join(targetDir, `${name}.png`);
  const metadataPath = path.join(targetDir, `${name}.json`);
  const target = page.locator(locator).first();
  const budgetMetrics = await target.evaluate((node) => {
    const rect = node.getBoundingClientRect();
    return {
      rendered_height: Math.ceil(rect.height),
      scroll_height: Math.ceil(node.scrollHeight),
    };
  });
  if (maxHeight > 0) {
    expect(
      budgetMetrics.rendered_height,
      `${name} rendered screenshot height should stay under desktop audit budget`,
    ).toBeLessThanOrEqual(maxHeight);
  }
  try {
    if (locator === 'body' && fullPage) {
      await page.screenshot({ path: screenshotPath, fullPage: true });
    } else {
      await target.screenshot({ path: screenshotPath });
    }
  } catch (error) {
    if (locator === 'body') {
      await page.screenshot({ path: screenshotPath });
    } else {
      await target.screenshot({ path: screenshotPath });
    }
  }
  const viewport = page.viewportSize() || { width: 1440, height: 1200 };
  const textExcerpt = String(await target.innerText()).slice(0, 4000);
  const payload = {
    name,
    artifact_type: 'workspace_surface',
    url: page.url(),
    title,
    viewport,
    focus_locator: locator,
    text_excerpt: textExcerpt,
    screenshot_path: screenshotPath,
    screenshot_budget: maxHeight > 0
      ? {
        max_height: maxHeight,
        rendered_height: budgetMetrics.rendered_height,
        scroll_height: budgetMetrics.scroll_height,
      }
      : null,
  };
  await fs.writeFile(metadataPath, JSON.stringify(payload, null, 2));
  return metadataPath;
}

test.describe('complaint generation workflow', () => {
  test('document generation hands off into the review dashboard cohesively', async ({ page }) => {
    const recorder = {};
    await installCommonMocks(page, recorder);

    await page.goto('/document');

    await page.getByLabel('District').fill('Northern District of California');
    await page.getByLabel('Plaintiffs').fill('Jane Doe');
    await page.getByLabel('Defendants').fill('Acme Corporation');
    await page.getByLabel('Requested Relief').fill('Back pay\nReinstatement');
    await page.getByLabel('Signer Name').fill('Jane Doe');

    await page.getByRole('button', { name: 'Generate Formal Complaint' }).click();

    await expect(page.locator('#successBox')).toContainText(/generated successfully/i);
    await expect(page.locator('#previewRoot')).toContainText(/Pleading Text/i);
    await expect(page.locator('#previewRoot')).toContainText(/Title VII/i);
    await expect(page.locator('#artifactMetric')).toContainText(/2 ready/i);
    await expect(page.locator('#previewRoot a[href*="/claim-support-review"]').first()).toBeVisible();

    expect(recorder.documentRequest.district).toBe('Northern District of California');
    expect(recorder.documentRequest.plaintiff_names).toEqual(['Jane Doe']);
    expect(recorder.documentRequest.defendant_names).toEqual(['Acme Corporation']);

    await page.locator('#previewRoot a[href*="/claim-support-review"]').first().click();
    await expect(page).toHaveURL(/\/claim-support-review/);
    await expect(page.locator('#prefill-context-line')).toContainText(/Opened from document workflow/i);

    await page.getByRole('button', { name: 'Load Review' }).click();
    await expect(page.locator('#status-line')).toContainText(/Review payload loaded/i);
    await expect(page.locator('#hero-covered')).toContainText('1');
    await expect(page.locator('#hero-missing')).toContainText('1');
    await expect(page.locator('#element-list')).toContainText(/Protected activity/i);
    await expect(page.locator('#task-list')).toContainText(/Load Into Resolution Form/i);

    expect(recorder.reviewRequest.claim_type).toBe('retaliation');
    expect(recorder.reviewRequest.user_id).toBe('demo-user');
  });

  test('dashboard evidence actions stay wired into the complaint workflow', async ({ page }) => {
    const recorder = {};
    await installCommonMocks(page, recorder);

    await page.goto('/claim-support-review?claim_type=retaliation&user_id=demo-user&section=claims_for_relief');
    await page.getByRole('button', { name: 'Load Review' }).click();
    await expect(page.locator('#status-line')).toContainText(/Review payload loaded/i);
    await expect(page.locator('#question-list')).toContainText(/When were you terminated after complaining to HR\?/i);
    await expect(page.locator('#testimony-list')).toContainText(/I reported discrimination to HR/i);
    await expect(page.locator('#document-list')).toContainText(/HR complaint email/i);

    await page.locator('#testimony-element-id').fill('retaliation:2');
    await page.locator('#testimony-element-text').fill('Adverse action');
    await page.locator('#testimony-event-date').fill('2026-03-12');
    await page.locator('#testimony-actor').fill('Acme manager');
    await page.locator('#testimony-act').fill('Termination');
    await page.locator('#testimony-target').fill('Jane Doe');
    await page.locator('#testimony-harm').fill('Lost employment');
    await page.locator('#testimony-confidence').fill('0.9');
    await page.locator('#testimony-narrative').fill('My manager terminated me two days after I complained to HR.');
    await page.getByRole('button', { name: 'Save Testimony' }).click();

    await expect(page.locator('#testimony-list')).toContainText(/My manager terminated me two days after I complained to HR\./i);
    expect(recorder.saveTestimonyRequest.claim_type).toBe('retaliation');
    expect(recorder.saveTestimonyRequest.claim_element_id).toBe('retaliation:2');

    await page.locator('#document-element-id').fill('retaliation:2');
    await page.locator('#document-element-text').fill('Adverse action');
    await page.locator('#document-label').fill('Termination Email');
    await page.locator('#document-filename').fill('termination-email.txt');
    await page.locator('#document-text').fill('On March 10, 2026, Acme terminated Jane Doe after her HR complaint.');
    await page.getByRole('button', { name: 'Save Document' }).click();

    await expect(page.locator('#document-list')).toContainText(/termination-email\.txt/i);
    expect(recorder.saveDocumentRequest.claim_type).toBe('retaliation');
    expect(recorder.saveDocumentRequest.claim_element_id).toBe('retaliation:2');

    await page.getByRole('button', { name: 'Execute Follow-Up' }).click();
    await expect(page.locator('#status-line')).toContainText(/Follow-up execution completed/i);
    await expect(page.locator('#execution-result-card')).toBeVisible();
    expect(recorder.executeRequest.claim_type).toBe('retaliation');

    await expect(page.locator('#review-nav-builder')).toHaveAttribute('href', /\/document/);
    await page.locator('#review-nav-builder').click();
    await expect(page).toHaveURL(/\/document/);
    await expect(page.locator('body')).toContainText(/Formal Complaint Builder/i);
  });

  test('review dashboard can upload a document file and keep the attachment visible in the evidence flow', async ({ page }) => {
    const recorder = {};
    await installCommonMocks(page, recorder);

    await page.goto('/claim-support-review?claim_type=retaliation&user_id=demo-user&section=claims_for_relief');
    await page.getByRole('button', { name: 'Load Review' }).click();
    await expect(page.locator('#status-line')).toContainText(/Review payload loaded/i);

    await page.locator('#document-element-id').fill('retaliation:2');
    await page.locator('#document-element-text').fill('Adverse action');
    await page.locator('#document-label').fill('Uploaded termination notice');
    await page.locator('#document-filename').fill('review-upload-evidence.txt');
    await page.locator('#document-mime-type').fill('text/plain');
    await page.locator('#document-file-input').setInputFiles({
      name: 'review-upload-evidence.txt',
      mimeType: 'text/plain',
      buffer: Buffer.from('Termination notice uploaded through the review dashboard.'),
    });
    await page.getByRole('button', { name: 'Save Document' }).click();

    await expect(page.locator('#document-list')).toContainText(/Uploaded termination notice/i);
    await expect(page.locator('#document-list')).toContainText(/review-upload-evidence\.txt/i);
    await expect(page.locator('#document-list')).toContainText(/parse parsed/i);
    await expect(page.locator('#document-list')).toContainText(/graph:\s*ready/i);
    await expect(page.locator('#raw-output')).toContainText(/"recorded": true/i);

    expect(recorder.saveUploadedDocumentRequest.contentType).toMatch(/multipart\/form-data/i);
    expect(recorder.saveUploadedDocumentRequest.filename).toBe('review-upload-evidence.txt');
    expect(recorder.saveUploadedDocumentRequest.bodyText).toContain('retaliation:2');
    expect(recorder.saveUploadedDocumentRequest.bodyText).toContain('Uploaded termination notice');
  });

  test('review dashboard surfaces legal retrieval warnings in signals and execution feedback', async ({ page }) => {
    const recorder = {};
    await installCommonMocks(page, recorder);

    const warningEntries = [
      {
        family: 'state_statutes',
        warning_code: 'hf_dataset_files_missing',
        warning_message: 'Dataset missing Oregon parquet coverage.',
        state_code: 'OR',
        hf_dataset_id: 'justicedao/ipfs_state_laws',
      },
      {
        family: 'administrative_rules',
        warning_code: 'hf_state_rows_missing',
        warning_message: 'Dataset exposes no Oregon admin rows.',
        state_code: 'OR',
        hf_dataset_id: 'justicedao/ipfs_state_admin_rules',
      },
    ];
    const reviewWithWarnings = JSON.parse(JSON.stringify(reviewPayload));
    reviewWithWarnings.follow_up_plan_summary.retaliation = {
      ...reviewWithWarnings.follow_up_plan_summary.retaliation,
      search_warning_count: 2,
      warning_family_counts: {
        state_statutes: 1,
        administrative_rules: 1,
      },
      warning_code_counts: {
        hf_dataset_files_missing: 1,
        hf_state_rows_missing: 1,
      },
      hf_dataset_id_counts: {
        'justicedao/ipfs_state_laws': 1,
        'justicedao/ipfs_state_admin_rules': 1,
      },
      search_warning_summary: warningEntries,
    };
    reviewWithWarnings.follow_up_history_summary.retaliation = {
      ...reviewWithWarnings.follow_up_history_summary.retaliation,
      search_warning_count: 1,
      warning_family_counts: {
        state_statutes: 1,
      },
      warning_code_counts: {
        hf_dataset_files_missing: 1,
      },
      hf_dataset_id_counts: {
        'justicedao/ipfs_state_laws': 1,
      },
      search_warning_summary: [warningEntries[0]],
    };

    await page.route('**/api/claim-support/review', async (route) => {
      recorder.reviewRequest = route.request().postDataJSON();
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(JSON.parse(JSON.stringify(reviewWithWarnings))),
      });
    });

    await page.route('**/api/claim-support/execute-follow-up', async (route) => {
      recorder.executeRequest = route.request().postDataJSON();
      const postExecutionReview = JSON.parse(JSON.stringify(reviewWithWarnings));
      postExecutionReview.follow_up_history_summary.retaliation = {
        ...postExecutionReview.follow_up_history_summary.retaliation,
        search_warning_count: 1,
        warning_family_counts: {
          state_statutes: 1,
        },
        warning_code_counts: {
          hf_dataset_files_missing: 1,
        },
        hf_dataset_id_counts: {
          'justicedao/ipfs_state_laws': 1,
        },
        search_warning_summary: [warningEntries[0]],
      };
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          execution_id: 8,
          outcome_status: 'completed',
          notes: 'Follow-up execution completed.',
          follow_up_execution_summary: {
            retaliation: {
              executed_task_count: 1,
              skipped_task_count: 0,
              suppressed_task_count: 0,
              cooldown_skipped_task_count: 0,
              manual_review_task_count: 0,
              contradiction_task_count: 0,
              reasoning_gap_task_count: 0,
              temporal_gap_task_count: 0,
              fact_gap_task_count: 0,
              adverse_authority_task_count: 0,
              parse_quality_task_count: 0,
              quality_gap_targeted_task_count: 0,
              temporal_gap_targeted_task_count: 0,
              semantic_cluster_count: 0,
              semantic_duplicate_count: 0,
              support_by_kind: {},
              support_by_source: {},
              source_family_counts: {},
              record_scope_counts: {},
              artifact_family_counts: {},
              corpus_family_counts: {},
              content_origin_counts: {},
              primary_missing_fact_counts: {},
              missing_fact_bundle_counts: {},
              satisfied_fact_bundle_counts: {},
              follow_up_focus_counts: {},
              query_strategy_counts: {},
              proof_decision_source_counts: {},
              resolution_status_counts: {},
              temporal_resolution_status_counts: {},
              resolution_applied_counts: {},
              temporal_rule_status_counts: {},
              temporal_rule_blocking_reason_counts: {},
              adaptive_retry_task_count: 0,
              priority_penalized_task_count: 0,
              adaptive_query_strategy_counts: {},
              adaptive_retry_reason_counts: {},
              last_adaptive_retry: null,
              authority_search_program_task_count: 0,
              authority_search_program_count: 0,
              authority_search_program_type_counts: {},
              authority_search_intent_counts: {},
              primary_authority_program_type_counts: {},
              primary_authority_program_bias_counts: {},
              primary_authority_program_rule_bias_counts: {},
              rule_candidate_backed_task_count: 0,
              total_rule_candidate_count: 0,
              matched_claim_element_rule_count: 0,
              rule_candidate_type_counts: {},
              search_warning_count: 2,
              warning_family_counts: {
                state_statutes: 1,
                administrative_rules: 1,
              },
              warning_code_counts: {
                hf_dataset_files_missing: 1,
                hf_state_rows_missing: 1,
              },
              hf_dataset_id_counts: {
                'justicedao/ipfs_state_laws': 1,
                'justicedao/ipfs_state_admin_rules': 1,
              },
              search_warning_summary: warningEntries,
            },
          },
          post_execution_review: postExecutionReview,
        }),
      });
    });

    await page.goto('/claim-support-review?claim_type=retaliation&user_id=demo-user&section=claims_for_relief');
    await page.getByRole('button', { name: 'Load Review' }).click();

    await expect(page.locator('#signal-legal-retrieval-warnings')).toHaveText('3');
    await expect(page.locator('#signal-legal-retrieval-warning-chips')).toContainText(/Plan Hf Dataset Files Missing/i);
    await expect(page.locator('#signal-legal-retrieval-warning-chips')).toContainText(/History Hf Dataset Files Missing/i);
    await expect(page.locator('#signal-legal-retrieval-warning-note')).toContainText(/dataset justicedao\/ipfs_state_laws/i);
    await expect(page.locator('#signal-legal-retrieval-warning-note')).toContainText(/state OR/i);

    await page.getByRole('button', { name: 'Execute Follow-Up' }).click();

    await expect(page.locator('#execution-result-card')).toBeVisible();
    await expect(page.locator('#execution-result-chips')).toContainText(/legal warnings 2/i);
    await expect(page.locator('#execution-result-notes')).toContainText(/Latest legal retrieval warning:/i);
    await expect(page.locator('#execution-result-notes')).toContainText(/dataset justicedao\/ipfs_state_laws/i);
    expect(recorder.executeRequest.claim_type).toBe('retaliation');
  });

  test('user can go through intake questions and see them across chat, profile, and results surfaces', async ({ page }) => {
    await page.addInitScript(() => {
      window.alert = () => {};
      class MockWebSocket {
        constructor() {
          setTimeout(() => {
            if (this.onmessage) {
              this.onmessage({
                data: JSON.stringify({
                  sender: 'System:',
                  message: 'Please describe the retaliation you experienced.',
                  explanation: {
                    summary: 'This opens the intake question flow.',
                  },
                }),
              });
            }
          }, 10);
        }
        send(raw) {
          const payload = JSON.parse(raw);
          setTimeout(() => {
            if (this.onmessage) {
              this.onmessage({ data: JSON.stringify(payload) });
            }
          }, 10);
        }
        close() {}
      }
      window.WebSocket = MockWebSocket;
    });

    await page.goto('/chat');
    await expect(page.locator('#messages')).toContainText(/Welcome back to Lex Publicus/i);
    await expect(page.locator('#messages')).toContainText(/Please describe the retaliation you experienced\./i);

    await page.locator('#chat-form input').fill('I complained to HR and was fired two days later.');
    await page.getByRole('button', { name: 'Send' }).click();

    await page.goto('/profile');
    await expect(page.locator('#chat_history')).toContainText(/I need help drafting a retaliation complaint\./i);
    await expect(page.locator('#profile_data')).toContainText(/demo-user/i);
    await expect(page.locator('#profile_data')).not.toContainText(/demo-password/i);
    await expect(page.locator('#profile_data')).toContainText(/\[redacted\]/i);

    await page.goto('/results');
    await expect(page.locator('#profile_data')).toContainText(/retaliation/i);
    await expect(page.locator('#profile_data')).toContainText(/chat_history/i);
    await expect(page.locator('#profile_data')).not.toContainText(/demo-password/i);
  });

  test('user can review, modify, regenerate, and reset the final complaint draft', async ({ page }) => {
    const recorder = {};
    const revisedDocumentResponse = JSON.parse(JSON.stringify(documentGenerationResponse));
    revisedDocumentResponse.generated_at = '2026-03-22T12:30:00Z';
    revisedDocumentResponse.draft.requested_relief = ['Front pay', 'Injunctive relief'];
    revisedDocumentResponse.draft.draft_text = 'Plaintiff Jane Doe seeks injunctive and equitable relief for retaliation.';
    revisedDocumentResponse.draft.summary_of_facts = [
      'Jane Doe reported discrimination to human resources.',
      'Acme Corporation escalated retaliation after the complaint.',
    ];
    revisedDocumentResponse.draft.claims_for_relief[0].supporting_facts = [
      'Plaintiff complained internally about discrimination.',
      'Defendant escalated retaliatory acts after the complaint.',
    ];

    await page.addInitScript(() => {
      window.alert = () => {};
      window.__copiedText = null;
      Object.defineProperty(navigator, 'clipboard', {
        configurable: true,
        value: {
          writeText(value) {
            window.__copiedText = value;
            return Promise.resolve();
          },
        },
      });
    });

    await installCommonMocks(page, recorder, {
      documentResponses: [documentGenerationResponse, revisedDocumentResponse],
    });

    await page.goto('/document');

    await page.getByLabel('District').fill('Northern District of California');
    await page.getByLabel('Plaintiffs').fill('Jane Doe');
    await page.getByLabel('Defendants').fill('Acme Corporation');
    await page.getByLabel('Requested Relief').fill('Back pay\nReinstatement');
    await page.getByLabel('Signer Name').fill('Jane Doe');

    await page.getByRole('button', { name: 'Generate Formal Complaint' }).click();

    await expect(page.locator('#previewRoot')).toContainText(/Back pay/i);
    await expect(page.locator('#previewRoot')).toContainText(/Reinstatement/i);
    await expect(page.locator('#previewRoot')).toContainText(/violation of Title VII/i);

    await page.getByRole('button', { name: 'Copy Pleading Text' }).click();
    await expect(page.locator('#successBox')).toContainText(/copied to the clipboard/i);
    await expect.poll(async () => page.evaluate(() => window.__copiedText)).toContain('Title VII');

    await page.getByLabel('Requested Relief').fill('Front pay\nInjunctive relief');
    await page.getByRole('button', { name: 'Generate Formal Complaint' }).click();

    await expect.poll(() => (recorder.documentRequests || []).length).toBe(2);
    expect(recorder.documentRequests[1].requested_relief).toEqual(['Front pay', 'Injunctive relief']);

    await expect(page.locator('#previewRoot')).toContainText(/Front pay/i);
    await expect(page.locator('#previewRoot')).toContainText(/Injunctive relief/i);
    await expect(page.locator('#previewRoot')).toContainText(/injunctive and equitable relief/i);
    await expect(page.locator('#previewRoot')).not.toContainText(/Reinstatement/i);

    await page.reload();
    await expect(page.getByLabel('Requested Relief')).toHaveValue('Front pay\nInjunctive relief');
    await expect(page.locator('#previewRoot')).toContainText(/injunctive and equitable relief/i);

    await page.getByRole('button', { name: 'Reset' }).click();
    await expect(page.locator('#previewRoot')).toContainText(/Nothing rendered yet/i);
    await expect(page.locator('#artifactMetric')).toContainText(/None yet/i);
    await expect(page.getByLabel('Requested Relief')).toHaveValue('');
    await expect.poll(async () => page.evaluate(() => ({
      draft: window.localStorage.getItem('formalComplaintBuilderState'),
      preview: window.localStorage.getItem('formalComplaintBuilderPreview'),
    }))).toEqual({
      draft: null,
      preview: null,
    });
  });

  test('review dashboard can prefill testimony from targeted questions and expose evidence support details', async ({ page }) => {
    const recorder = {};
    await installCommonMocks(page, recorder);

    await page.goto('/claim-support-review?claim_type=retaliation&user_id=demo-user&section=claims_for_relief');
    await page.getByRole('button', { name: 'Load Review' }).click();

    await expect(page.locator('#element-list')).toContainText(/Protected activity/i);
    await expect(page.locator('#element-list')).toContainText(/Adverse action/i);
    await expect(page.locator('#question-list')).toContainText(/1 HR complaint email on file/i);
    await expect(page.locator('#document-list')).toContainText(/Email to HR reporting discrimination and requesting intervention\./i);
    await expect(page.locator('#document-list')).toContainText(/Jane Doe reported discrimination to HR before termination\./i);

    await page.getByRole('button', { name: 'Load Into Testimony Form' }).first().click();
    await expect(page.locator('#status-line')).toContainText(/Testimony form prefilled from selected question/i);
    await expect(page.locator('#testimony-element-id')).toHaveValue('retaliation:2');
    await expect(page.locator('#testimony-element-text')).toHaveValue('Adverse action');
    await expect(page.locator('#testimony-narrative')).toHaveValue(/When were you terminated after complaining to HR\?/i);
  });

  test('document, review, and trace surfaces stay connected through navigation shortcuts', async ({ page }) => {
    const recorder = {};
    await installCommonMocks(page, recorder);

    await page.goto('/document');
    await expect(page.locator('#builder-nav-trace')).toHaveAttribute('href', /\/document\/optimization-trace/);
    await page.locator('#builder-advanced-nav').evaluate((node) => { node.open = true; });
    await page.locator('#builder-nav-trace').click();
    await expect(page).toHaveURL(/\/document\/optimization-trace/);
    await expect(page.locator('body')).toContainText(/Optimization Trace Viewer/i);

    await page.goto('/claim-support-review');
    await expect(page.locator('#review-nav-trace')).toHaveAttribute('href', /\/document\/optimization-trace/);
    await expect(page.locator('#review-advanced-nav')).toContainText(/Advanced tools/i);
    await expect(page.locator('#review-nav-builder')).toHaveAttribute('href', /\/document/);
    await page.locator('#review-nav-builder').click();
    await expect(page).toHaveURL(/\/document/);

    await page.getByLabel('District').fill('Northern District of California');
    await page.getByLabel('Plaintiffs').fill('Jane Doe');
    await page.getByLabel('Defendants').fill('Acme Corporation');
    await page.getByLabel('Requested Relief').fill('Back pay\nReinstatement');
    await page.getByLabel('Signer Name').fill('Jane Doe');
    await page.getByRole('button', { name: 'Generate Formal Complaint' }).click();

    await expect(page.locator('#previewRoot')).toContainText(/Pleading Text/i);
    await expect(page.locator('#previewRoot a[href*="/claim-support-review"]').first()).toBeVisible();
    await page.locator('#previewRoot a[href*="/claim-support-review"]').first().click();
    await expect(page).toHaveURL(/\/claim-support-review/);
  });

  test('workspace unifies intake, evidence, support review, draft editing, actor/critic audit, and MCP tool visibility', async ({ page }) => {
    const did = `did:key:workspace-flow-${Date.now()}`;
    await page.addInitScript((did) => {
      window.localStorage.setItem('complaintGenerator.did', did);
    }, did);
    await page.goto('/workspace?shell_mode=operator');
    await waitForWorkspaceReady(page);
    await expect(page.locator('[data-surface-nav="primary"]')).toContainText(/Secure Intake/i);
    await expect(page.locator('[data-surface-nav="primary"]')).not.toContainText(/Profile|Trace|Dashboards/i);
    await expect(page.locator('#workspace-advanced-nav')).toContainText(/Developer tools and linked surfaces/i);
    await expect(page.locator('#queue-list')).toContainText(/Complete/i);
    await expect(page.locator('#queue-list')).toContainText(/Do next/i);
    await expect(page.locator('#queue-list')).toContainText(/Watch for/i);
    await expect(page.locator('#intake-question-grid')).toContainText(/What name should we use for the person harmed\?/i);
    await expect(page.locator('#intake-question-grid')).toContainText(/You can save and return anytime\. Share only what you can right now\./i);
    await expect(page.locator('#tool-list')).toContainText(/complaint\.generate_complaint/i);
    await expect(page.locator('#tool-list')).toContainText(/complaint\.get_complaint_readiness/i);
    await expect(page.locator('#tool-list')).toContainText(/complaint\.update_claim_type/i);
    await expect(page.locator('#tool-list')).toContainText(/complaint\.review_generated_exports/i);
    await expect(page.locator('#tool-list')).toContainText(/complaint\.optimize_ui/i);
    await expect(page.locator('#tool-list')).toContainText(/complaint\.get_tooling_contract/i);
    await expect(page.locator('#tool-list')).toContainText(/complaint\.get_filing_provenance/i);
    await expect(page.locator('#did-chip')).toContainText(/did:key:/i);
    await expect.poll(async () => page.evaluate(() => localStorage.getItem('complaintGenerator.did'))).toMatch(/^did:key:/);
    await expect(page.locator('#intake-caption-preview')).toContainText(/FOR THE APPROPRIATE JUDICIAL DISTRICT/i);
    await page.getByRole('button', { name: 'CLI + MCP', exact: true }).click();
    await page.locator('#refresh-capabilities-button').click();
    await expect(page.locator('#workspace-status')).toContainText(/Workflow capabilities refreshed\./i, { timeout: 15000 });
    await expect(page.locator('#workflow-capabilities-preview')).toContainText(/Shared Tooling Contract/i);
    await expect(page.locator('#workflow-capabilities-preview')).toContainText(/All core complaint-flow steps are exposed across package, CLI, MCP, and browser SDK surfaces\./i);
    await page.locator('#refresh-tooling-contract-button').click();
    await expect(page.locator('#workspace-status')).toContainText(/Tooling contract refreshed\./i);
    await expect(page.locator('#tooling-contract-preview')).toContainText(/"all_core_flow_steps_exposed":\s*true/i);
    await expect(page.locator('#tooling-contract-preview')).toContainText(/import_gmail_evidence/i);
    await expect(page.locator('#tooling-contract-preview')).toContainText(/importGmailEvidence/i);
    await expect(page.locator('#tooling-contract-preview')).toContainText(/complaint\.generate_complaint/i);
    await expect(page.locator('#tooling-contract-preview')).toContainText(/getToolingContract/i);
    await expect(page.locator('#tooling-contract-preview')).toContainText(/updateClaimType/i);
    await expect(page.locator('#tooling-contract-preview')).toContainText(/updateCaseSynopsis/i);
    await expect(page.locator('#tooling-contract-preview')).toContainText(/complaint\.get_formal_diagnostics/i);
    await expect(page.locator('#tooling-contract-preview')).toContainText(/getFormalDiagnostics/i);
    await expect(page.locator('#tooling-contract-preview')).toContainText(/complaint\.get_filing_provenance/i);
    await expect(page.locator('#tooling-contract-preview')).toContainText(/getFilingProvenance/i);
    await expect(page.locator('#session-tool-activity-ledger')).toContainText(/complaint\.get_tooling_contract/i);
    await page.locator('#refresh-formal-diagnostics-button').click();
    await expect(page.locator('#formal-diagnostics-preview')).toContainText(/Formal complaint posture summary/i, { timeout: 15000 });
    await expect(page.locator('#formal-diagnostics-preview')).toContainText(/Release gate verdict:/i, { timeout: 15000 });
    await page.getByRole('button', { name: 'Intake', exact: true }).click();
    await expect(page.locator('#focus-rail-stage')).toContainText(/You are in Intake\./i);
    await expect(page.locator('#focus-rail-title')).toContainText(/Intake stage:/i);
    await expect(page.locator('#action-sdk-chip')).toContainText(/complaint\.submit_intake/i);

    await revealAllIntakeFields(page);
    await page.locator('#intake-party_name').fill('Jane Doe');
    await page.locator('#intake-opposing_party').fill('Acme Corporation');
    await page.locator('#intake-protected_activity').fill('Reported discrimination to HR');
    await page.locator('#intake-adverse_action').fill('Was terminated two days later');
    await page.locator('#intake-timeline').fill('Complaint on March 8, termination on March 10');
    await page.locator('#intake-harm').fill('Lost wages and benefits');
    await page.locator('#intake-court_header').fill('FOR THE NORTHERN DISTRICT OF CALIFORNIA');
    await page.locator('#save-intake-button').click();

    await expect(page.locator('#next-question-label')).toContainText(/Intake complete/i);
    await expect(page.locator('#case-confidence-chip')).toContainText(/readiness:/i);
    await expect(page.locator('#progress-percent-chip')).toContainText(/workflow mapped/i);
    await page.locator('#case-synopsis').fill('Jane Doe alleges retaliation after reporting discrimination to HR, and the next priority is proving the timing and motive with corroborating evidence.');
    await page.locator('#save-synopsis-button').click();
    await expect(page.locator('#workspace-status')).toContainText(/Shared case synopsis saved/i);
    await expect(page.locator('#review-synopsis-preview')).toContainText(/Jane Doe alleges retaliation/i);
    await expect(page.locator('#draft-synopsis-preview')).toContainText(/next priority is proving the timing and motive/i);

    await expect(page.locator('#handoff-chat-button')).toHaveAttribute('href', /Jane%20Doe|Jane\+Doe|Jane Doe/i);
    await page.locator('#handoff-chat-button').click();
    await expect(page).toHaveURL(/\/chat\?/);
    await expect(page.locator('#chat-context-summary')).toContainText(/Jane Doe alleges retaliation/i);
    await expect(page.locator('#chat-form input')).toHaveValue(/Mediator, help turn this into testimony-ready narrative/i);
    await expect(page.locator('#chat-open-profile')).toHaveAttribute('href', /user_id=/);
    await page.goto(await page.locator('#chat-open-profile').getAttribute('href'));
    await expect(page).toHaveURL(/\/profile\?/);
    await expect(page.locator('#profile-context-card')).toBeVisible();
    await expect(page.locator('#profile-context-summary')).toContainText(/did:key:workspace-flow-/);
    await expect(page.locator('#profile-open-results')).toHaveAttribute('href', /user_id=/);
    await page.locator('#profile-open-results').click();
    await expect(page).toHaveURL(/\/results\?/);
    await expect(page.locator('#results-context-card')).toBeVisible();
    await expect(page.locator('#results-context-summary')).toContainText(/did:key:workspace-flow-/);
    await expect(page.locator('#results-open-workspace')).toHaveAttribute('href', /user_id=/);
    await page.locator('#results-open-workspace').click();
    await expect(page).toHaveURL(/\/workspace\?/);
    await expect(page).toHaveURL(/user_id=/);
    await waitForWorkspaceReady(page, { requireIntakeVisible: false });
    await expect(page.locator('#workspace-status')).toContainText(/Opened Workspace from the results surface\./i);
    await expect(page.locator('#case-synopsis')).toHaveValue(/Jane Doe alleges retaliation/i);
    await expect(page.locator('#blocker-list .evidence-shortcut-action')).toContainText([/Add testimony for/i, /Upload document for/i]);
    await page.locator('#blocker-list .evidence-shortcut-action[data-evidence-kind="document"]').first().click();
    await expect(page.locator('[data-tab-panel="evidence"]')).toHaveClass(/is-active/);
    await expect(page.locator('#evidence-kind')).toHaveValue('document');
    await expect(page.locator('#evidence-claim-element')).toHaveValue(/.+/);
    await expect(page.locator('label[for="evidence-kind"]')).toContainText(/Evidence Type/i);
    await expect(page.locator('label[for="evidence-claim-element"]')).toContainText(/Claim Element This Supports/i);
    await expect(page.locator('label[for="gmail-import-claim-element"]')).toContainText(/Imported Emails Support/i);
    await expect(page.locator('label[for="local-evidence-kind"]')).toContainText(/Imported Item Type/i);
    await expect(page.locator('#evidence-soft-note')).toContainText(/Map this item to one claim element/i);
    await expect(page.locator('#save-evidence-button')).toHaveClass(/primary/);
    await expect(page.locator('#import-local-evidence-button')).toHaveClass(/secondary/);
    await expect(page.locator('#evidence-add-testimony-button')).toContainText(/Add testimony for/i);
    await expect(page.locator('#evidence-add-document-button')).toContainText(/Attach document for/i);

    await page.getByRole('button', { name: 'Evidence', exact: true }).click();
    await expect(page.locator('#focus-rail-stage')).toContainText(/You are in Evidence\./i);
    await expect(page.locator('#focus-rail-title')).toContainText(/Evidence stage:/i);
    await expect(page.locator('#action-sdk-chip')).toContainText(/complaint\.save_evidence/i);
    await expect(page.locator('#workflow-stage-chip')).toContainText(/Current stage: evidence/i);
    await expect(page.locator('#progress-title')).toContainText(/Evidence is the active workspace stage/i);
    await expect(page.locator('#progress-phase-chip')).toContainText(/case phase:/i);
    await expect(page.locator('#workflow-stage-chip')).not.toContainText(/draft in progress/i);

    await page.locator('#evidence-kind').selectOption('testimony');
    await page.locator('#evidence-claim-element').selectOption('causation');
    await page.locator('#evidence-title').fill('Witness statement');
    await page.locator('#evidence-source').fill('Coworker interview');
    await page.locator('#evidence-content').fill('A coworker confirmed the termination happened immediately after the HR complaint.');
    await page.locator('#evidence-attachment').setInputFiles({
      name: 'termination-timeline.txt',
      mimeType: 'text/plain',
      buffer: Buffer.from('Complaint on March 8. Termination on March 10.'),
    });
    await page.locator('#save-evidence-button').click();

    await expect(page.locator('#evidence-list')).toContainText(/Witness statement/i);
    await expect(page.locator('#evidence-list')).toContainText(/termination-timeline\.txt/i);
    await page.getByRole('button', { name: 'Docket', exact: true }).click();
    await expect(page.locator('[data-tab-panel="docket"]')).toHaveClass(/is-active/);
    await expect(page.locator('#focus-rail-stage')).toContainText(/You are in Docket\./i);
    await expect(page.locator('#focus-rail-title')).toContainText(/Docket stage:/i);
    await expect(page.locator('#action-sdk-chip')).toContainText(/complaint\.view_docket_dataset/i);
    await expect(page.locator('#docket-document-list')).toContainText(/Witness statement/i);
    await expect(page.locator('#docket-document-list')).toContainText(/vectors:/i);
    await expect(page.locator('#docket-selected-preview')).toContainText(/Next action:/i);
    await expect(page.locator('#docket-selected-preview')).toContainText(/OCR:/i);
    await expect(page.locator('#docket-selected-preview')).toContainText(/Vectors created:/i);
    await expect(page.locator('#docket-selected-preview')).toContainText(/Bluebook citations:/i);
    await expect(page.locator('#docket-gate-presenter')).toBeVisible();
    await expect(page.locator('#docket-gate-heading')).toContainText(/Ask one document question first/i);
    await expect(page.locator('#docket-gate-primary-chat-link')).toContainText(/Open Chat/i);
    await expect(page.locator('#docket-gate-write-count')).toContainText(/Document updates captured: 0/i);
    await expect(page.locator('#docket-gate-note')).toContainText(/ready confirmation is the first selected-document write/i);
    await expect(page.locator('#docket-ask-chat-link')).toHaveAttribute('href', /chat_context=/i);
    await expect(page.locator('#docket-advanced-operations')).toContainText(/Advanced docket operations/i);
    await expect(page.locator('#docket-advanced-operations')).toBeVisible();
    await page.locator('#docket-use-in-draft-button').click();
    await expect(page.locator('[data-tab-panel="draft"]')).toHaveClass(/is-active/);
    await page.getByRole('button', { name: 'Review', exact: true }).click();
    await expect(page.locator('#focus-rail-stage')).toContainText(/You are in Review\./i);
    await expect(page.locator('#focus-rail-title')).toContainText(/Review stage:/i);
    await expect(page.locator('#action-sdk-chip')).toContainText(/complaint\.review_case/i);
    await expect(page.locator('#workflow-stage-chip')).toContainText(/Current stage: review/i);
    await expect(page.locator('#progress-title')).toContainText(/Review is the active workspace stage/i);
    await expect(page.locator('#progress-phase-chip')).toContainText(/case phase:/i);
    await expect(page.locator('#workflow-stage-chip')).not.toContainText(/draft in progress/i);
    await expect(page.locator('#support-strength-map')).toContainText(/Per-element proof map/i);
    await expect(page.locator('#support-strength-map')).toContainText(/thin|unsupported|grounded/i);
    await expect(page.locator('#support-grid')).toContainText(/Protected activity/i);
    await expect(page.locator('#recommended-actions')).toContainText(/Check timing/i);
    await expect(page.locator('#review-synopsis-preview')).toContainText(/Jane Doe alleges retaliation/i);

    await page.locator('#handoff-review-button').click();
    await expect(page).toHaveURL(/\/claim-support-review/);
    await page.goto('/workspace?shell_mode=operator');
    await waitForWorkspaceReady(page, { requireIntakeVisible: false });

    await page.getByRole('button', { name: 'Draft', exact: true }).click();
    await expect(page.locator('#focus-rail-stage')).toContainText(/You are in Draft\./i);
    await expect(page.locator('#focus-rail-title')).toContainText(/Draft stage:/i);
    await expect(page.locator('#action-sdk-chip')).toContainText(/complaint\.generate_complaint/i);
    await page.locator('#draft-mode').selectOption('llm_router');
    await page.locator('#requested-relief').fill('Back pay\nInjunctive relief');
    await page.locator('#generate-draft-button').click();
    await expect(page.locator('#workspace-status')).toContainText(/llm_router formal complaint path/i);
    await expect(page.locator('#draft-preview')).toContainText(/Jane Doe brings this retaliation complaint/i);
    await expect(page.locator('#draft-preview')).toContainText(/Civil Action No\./i);
    await expect(page.locator('#draft-preview')).toContainText(/JURISDICTION AND VENUE/i);
    await expect(page.locator('#draft-preview')).toContainText(/EVIDENTIARY SUPPORT AND NOTICE/i);
    await expect(page.locator('#draft-preview')).toContainText(/COUNT I - RETALIATION/i);
    await expect(page.locator('#draft-preview')).not.toContainText(/Working case synopsis:/i);
    await expect(page.locator('#draft-title')).toHaveValue(/Jane Doe v\. Acme Corporation Retaliation Complaint/i);
    await expect(page.locator('#draft-body')).toHaveValue(/Jane Doe brings this retaliation complaint against Acme Corporation\./i);
    await expect(page.locator('#draft-generation-meta')).toContainText(/Draft strategy: llm_router/i);
    await expect(page.locator('#draft-generation-meta')).toContainText(/Claim type: retaliation/i);
    await expect(page.locator('#draft-generation-meta')).toContainText(/codex_cli|copilot_cli|hf_inference_api|playwright-stub/i);
    await expect(page.locator('#draft-contract-preview')).toContainText(/Claim type: Retaliation/i);
    await expect(page.locator('#draft-contract-preview')).toContainText(/Expected count heading: COUNT I - RETALIATION/i);
    await expect(page.locator('#draft-readiness-preview')).toContainText(/Record support: |Release gate verdict:/i);
    await expect(page.locator('#draft-readiness-preview')).toContainText(/Evidence items: 1/i);
    await expect(page.locator('#draft-readiness-preview')).toContainText(/Canonical filing readiness/i);
    await expect(page.locator('#draft-readiness-preview')).toContainText(/Pleading form quality:/i);
    await expect(page.locator('#draft-readiness-preview')).toContainText(/Evidence support strength:/i);
    await expect(page.locator('#draft-readiness-preview')).toContainText(/Download complaint files:/i);
    await expect(page.locator('#draft-export-integrity-preview')).toContainText(/Claim type selected: Retaliation/i);
    await expect(page.locator('#draft-export-integrity-preview')).toContainText(/Draft strategy selected: llm_router/i);
    await expect(page.locator('#draft-export-integrity-preview')).toContainText(/\[ok\] Prayer for relief/i);
    await expect(page.locator('#draft-export-integrity-preview')).toContainText(/Civil Action No\. is still a placeholder\./i);
    await expect(page.locator('#draft-provenance-preview')).toContainText(/Generator backend:/i);
    await expect(page.locator('#draft-provenance-preview')).toContainText(/Generator fallback chain:/i);

    await page.getByRole('button', { name: 'CLI + MCP', exact: true }).click();
    await expect(page.locator('#focus-rail-stage')).toContainText(/You are in CLI \+ MCP\./i);
    await expect(page.locator('#focus-rail-title')).toContainText(/CLI \+ MCP stage:/i);
    await expect(page.locator('#action-sdk-chip')).toContainText(/complaint\.get_tooling_contract/i);
    await page.locator('#integrations-technical-reference summary').click();
    await expect(page.locator('#integrations-technical-reference')).toHaveAttribute('open', '');
    const packageCard = page.locator('.tool-card').filter({ has: page.getByRole('heading', { name: 'Python package imports' }) }).first();
    const cliCard = page.locator('.tool-card').filter({ has: page.getByRole('heading', { name: 'Python CLI' }) }).first();
    const mcpCard = page.locator('.tool-card').filter({ has: page.getByRole('heading', { name: 'MCP stdio server' }) }).first();
    const sdkCard = page.locator('.tool-card').filter({ has: page.getByRole('heading', { name: 'JavaScript MCP SDK' }) }).first();
    await expect(packageCard.locator('pre')).toContainText(/export_complaint_docx/i);
    await expect(cliCard.locator('pre')).toContainText(/export-docx/i);
    await expect(mcpCard.locator('pre')).toContainText(/complaint\.export_complaint_docx/i);
    await expect(sdkCard.locator('pre')).toContainText(/exportComplaintDocx/i);
    await page.locator('#refresh-complaint-readiness-button').click();
    await expect(page.locator('#workspace-status')).toContainText(/Complaint readiness refreshed/i);
    await expect(page.locator('#complaint-readiness-preview')).toContainText(/"verdict":\s*"Draft in progress"/i);
    await expect(page.locator('#complaint-readiness-preview')).toContainText(/"has_draft":\s*true/i);
    await expect(page.locator('#tooling-parity-preview')).toContainText(/Session-bound tooling handoff/i);
    await expect(page.locator('#tooling-parity-preview')).toContainText(/Inspect this session/i);
    await expect(page.locator('#tooling-parity-preview')).toContainText(/complaint-workspace session --user-id did:key:workspace-flow-/i);
    await expect(page.locator('#tooling-parity-preview')).toContainText(/complaint\.export_complaint_packet/i);
    await expect(page.locator('#integrations-start-attorney-handoff-button')).toBeVisible();
    await expect(page.locator('#integrations-start-attorney-handoff-button')).toContainText(/Build Handoff Packet/i);

    await page.getByRole('button', { name: 'Draft', exact: true }).click();

    await page.locator('#draft-body').fill('Edited final complaint body.');
    await page.locator('#save-draft-button').click();
    await expect(page.locator('#draft-preview')).toContainText(/Edited final complaint body\./i);
    await page.locator('#export-packet-button').click();
    await expect(page.locator('#packet-preview')).toContainText(/Title: Jane Doe v\. Acme Corporation Retaliation Complaint/i);
    await expect(page.locator('#packet-preview')).toContainText(/Edited final complaint body\./i);
    await page.getByRole('button', { name: 'CLI + MCP', exact: true }).click();
    await page.locator('#analyze-complaint-output-button').click();
    await expect(page.locator('#workspace-status')).toContainText(/Complaint output analysis refreshed\./i);
    await page.getByRole('button', { name: 'Draft', exact: true }).click();
    await expect(page.locator('#draft-readiness-preview')).toContainText(/Release gate verdict:/i);
    await expect(page.locator('#draft-readiness-preview')).toContainText(/Top defect:/i);
    await expect(page.locator('#draft-export-safety-preview')).toContainText(/Canonical filing readiness/i);
    await expect(page.locator('#draft-canonical-release-gate')).toHaveAttribute('data-gate-role', 'primary-summary');
    await expect(page.locator('#draft-release-gate-card')).toBeVisible();
    await expect(page.locator('#draft-release-gate-card')).toHaveAttribute('data-canonical-gate', 'action-boundary');
    await expect(page.locator('#draft-release-gate-card')).toHaveAttribute('data-download-state', /(blocked|ready)/);
    await expect(page.locator('#draft-release-gate-summary')).toContainText(/Action boundary mirrors the pinned filing-readiness gate above/i);
    await expect(page.locator('#draft-release-gate-summary')).toContainText(/Release gate verdict:/i);
    await expect(page.locator('#draft-release-gate-next-step')).toContainText(/Next safest move:/i);
    await expect(page.locator('#draft-download-boundary')).toHaveAttribute('data-download-state', /(blocked|ready)/);
    await expect(page.locator('#draft-download-blocker-note')).toContainText(/Download is blocked until|Downloads are cleared/i);
    await expect(page.locator('#download-packet-markdown-button')).toHaveAttribute('aria-disabled', /(true|false)/);
    await expect(page.locator('#draft-release-open-review-button')).toBeVisible();
    await expect(page.locator('#draft-release-open-integrations-button')).toBeVisible();
    await expect(page.locator('#attorney-handoff-card')).toBeVisible();
    await expect(page.locator('#attorney-handoff-checklist')).toContainText(/Complaint draft/i);
    await expect(page.locator('#attorney-handoff-checklist')).toContainText(/Release gate/i);
    await expect(page.locator('#attorney-handoff-ipfs-chip')).toContainText(/ipfs_datasets_py/i);
    await expect(page.locator('#attorney-handoff-send-button')).toBeDisabled();
    await page.locator('#attorney-handoff-build-button').click();
    await expect(page.locator('#attorney-handoff-preview')).toContainText(/Attorney Handoff Packet/i);
    await expect(page.locator('#attorney-handoff-preview')).toContainText(/Neurosymbolic trace/i);
    await expect(page.locator('#attorney-handoff-preview')).toContainText(/Dataset refs:/i);
    await expect(page.locator('#attorney-handoff-preview')).toContainText(/complaint_packet_json/i);
    await expect(page.locator('#attorney-handoff-preview')).toContainText(/Reasoning summary:/i);
    await expect(page.locator('#attorney-handoff-preview')).toContainText(/Rule hits:/i);
    await expect(page.locator('#attorney-handoff-preview')).toContainText(/release_gate\.verdict/i);
    await expect(page.locator('#attorney-handoff-preview')).toContainText(/ipfs_datasets_py/i);
    await expect(page.locator('#attorney-handoff-preview')).toContainText(/fallback: git submodule update|ipfs_datasets_py: ready/i);
    await expect(page.locator('#attorney-handoff-status')).toContainText(/blocked|ready/i);
    await page.locator('#attorney-handoff-override-reason').fill('Attorney requested early review while evidence and trace blockers remain visible.');
    await expect(page.locator('#attorney-handoff-send-button')).toBeEnabled();
    await page.locator('#attorney-handoff-send-button').click();
    await expect(page.locator('#attorney-handoff-preview')).toContainText(/Attorney review packet staged/i);
    await expect(page.locator('#workspace-status')).toContainText(/Attorney review packet staged/i);
    await writeUiScreenshotArtifact(page, { name: 'workspace-attorney-handoff', title: 'Workspace Attorney Handoff', locator: '#attorney-handoff-card', maxHeight: 2200 });

    await page.getByRole('button', { name: 'UX Audit', exact: true }).click();
    await expect(page.locator('#focus-rail-stage')).toContainText(/You are in UX Audit\./i);
    await expect(page.locator('#focus-rail-title')).toContainText(/UX Audit stage:/i);
    await expect(page.locator('#action-sdk-chip')).toContainText(/complaint\.review_ui/i);
    await page.locator('#ux-review-provider').fill('llm_router');
    await page.locator('#ux-review-model').fill('multimodal_router');
    await page.locator('#run-ux-review-button').click();
    await expect(page.locator('#workspace-status')).toContainText(/Iterative UI\/UX review completed\./i, { timeout: 15000 });
    await expect(page.locator('#ux-review-runtime')).toContainText(/Review runtime/i);
    await expect(page.locator('#ux-review-runtime')).toContainText(/strategy:\s*(deterministic_fallback|llm_router|multimodal_router)/i);
    await expect(page.locator('#ux-review-runtime')).toContainText(/completed through|fell back|deterministic fallback/i);
    await expect(page.locator('#ux-review-runtime')).toContainText(/Workflow state/i);
    await expect(page.locator('#ux-review-runtime')).toContainText(/status:\s*(completed|unavailable)/i);
    await expect(page.locator('#ux-review-runtime')).toContainText(/Open Latest JSON|Open Latest Markdown/i);
    await expect(page.locator('#ux-review-metadata')).toContainText(/updated/i);
    await expect(page.locator('#ux-review-metadata')).toContainText(/latest artifact:/i);
    const latestJsonButton = page.getByRole('button', { name: 'Open Latest JSON' });
    const latestMarkdownButton = page.getByRole('button', { name: 'Open Latest Markdown' });
    if (await latestJsonButton.count()) {
      await latestJsonButton.click();
      await expect(page.locator('#workspace-status')).toContainText(/Opened latest json artifact reference:/i);
      await expect(page.locator('#workspace-status')).toContainText(/iteration-01-review\.json/i);
    } else {
      await latestMarkdownButton.click();
      await expect(page.locator('#workspace-status')).toContainText(/Opened latest markdown artifact reference:/i);
      await expect(page.locator('#workspace-status')).toContainText(/iteration-01-review\.md/i);
    }
    await expect(page.locator('#ux-review-summary')).toContainText(/llm_router/i);
    await expect(page.locator('#ux-review-summary')).toContainText(/multimodal_router/i);
    await expect(page.locator('#ux-review-summary')).toContainText(/Tighten review-to-draft gatekeeping/i);
    await expect(page.locator('#ux-review-scorecard')).toContainText(/7\/7 tools|7\/7 stages|7 stages/i);
    await expect(page.locator('#ux-review-scorecard')).toContainText(/complaint\.import_gmail_evidence/i);
    await expect(page.locator('#ux-review-scorecard')).toContainText(/Complaint output posture/i);
    await expect(page.locator('#ux-review-scorecard')).toContainText(/release gate: (warning|blocked)/i);
    await expect(page.locator('#ux-review-scorecard')).toContainText(/filing shape/i);
    await expect(page.locator('#ux-review-actor-critic')).toContainText(/actor/i);
    await expect(page.locator('#ux-review-actor-critic')).toContainText(/critic/i);
    await expect(page.locator('#ux-review-actor-critic')).toContainText(/complaint\.import_gmail_evidence/i);
    await expect(page.locator('#ux-review-issues')).toContainText(/Export controls can still visually outrank the release gate/i);
    await expect(page.locator('#ux-review-stage-findings')).toContainText(/Complaint-output suggestion carried into router review/i);
    await expect(page.locator('#ux-review-stage-findings')).toContainText(/Gmail import affordance/i);
    await expect(page.locator('#ux-review-scorecard')).toContainText(/Formal section gaps:/i);
    await expect(page.locator('#ux-review-followups')).toContainText(/Gmail import/i);

    await page.locator('#run-ux-closed-loop-button').click();
    await expect(page.locator('#workspace-status')).toContainText(/Closed-loop UI\/UX optimization completed\./i);
    await expect(page.locator('#ux-review-summary')).toContainText(/Tighten review-to-draft gatekeeping/i);
    await expect(page.locator('#ux-review-stage-findings')).toContainText(/Complaint-output suggestion carried into optimization/i);
    await expect(page.locator('#ux-review-scorecard')).toContainText(/Optimizer repair coverage|selected repairs|no repair batch/i);
    await expect(page.locator('#ux-review-runs')).toContainText(/UX repair 1|Round 1|Single review response/i);
    await expect(page.locator('#ux-review-artifacts')).toContainText(/Patch artifact for round 1|round-01\.patch|templates\/workspace\.html/i);

    const browserAuditButton = page.locator('#run-browser-audit-button');
    await expect(browserAuditButton).toBeVisible();
    await expect(browserAuditButton).toBeEnabled();
    await browserAuditButton.scrollIntoViewIfNeeded();
    await browserAuditButton.evaluate((node) => node.click());
    await expect(page.locator('#workspace-status')).toContainText(/End-to-end complaint browser audit completed\./i);
    await expect(page.locator('#ux-review-runtime')).toContainText(/Browser audit runtime/i);
    await expect(page.locator('#ux-review-runtime')).toContainText(/strategy: browser_audit/i);
    await expect(page.locator('#ux-review-runtime')).toContainText(/status:\s*browser_audit_completed/i);
    await expect(page.locator('#ux-review-metadata')).toContainText(/updated/i);
    await expect(page.locator('#ux-review-summary')).toContainText(/End-to-end complaint browser audit completed with 6 screenshot artifacts\./i);
    await expect(page.locator('#ux-review-stage-findings')).toContainText(/Lawsuit-generation browser audit/i);

    await page.getByRole('button', { name: 'CLI + MCP', exact: true }).click();
    await page.locator('#refresh-ui-readiness-button').click();
    await expect(page.locator('#workspace-status')).toContainText(/UI readiness refreshed\./i);
    await expect(page.locator('#ui-readiness-preview')).toContainText(/"status":\s*"cached"/i);
    await expect(page.locator('#ui-readiness-preview')).toContainText(/"verdict":\s*"Needs repair"/i);
    await expect(page.locator('#ui-readiness-preview')).toContainText(/"score":\s*81/i);
    await expect(page.locator('#ui-readiness-preview')).toContainText(/"actor_path_breaks":/i);

    const cachedDid = await page.evaluate(() => localStorage.getItem('complaintGenerator.did'));
    await page.reload();
    await expect.poll(async () => page.evaluate(() => localStorage.getItem('complaintGenerator.did'))).toBe(cachedDid);
    await expect(page.locator('#did-chip')).toContainText(cachedDid);
    await expect(page.locator('#draft-preview')).toContainText(/Edited final complaint body\./i);
    await page.getByRole('button', { name: 'Draft', exact: true }).click();
    await expect(page.locator('#download-packet-tool-markdown-button')).toBeDisabled();
    await expect(page.locator('#download-packet-tool-markdown-button')).toHaveAttribute('title', /Download is blocked until/i);
    await expect(page.locator('#download-packet-tool-markdown-button')).toHaveAttribute('data-download-url', /output_format=markdown/);
    await expect(page.locator('#draft-release-gate-summary')).toContainText(/Download blockers:/i);
  });

  test('ux audit exposes latest review artifact launchers inside the workspace', async ({ page }) => {
    const recorder = {};
    const did = `did:key:workspace-ux-artifacts-${Date.now()}`;
    await installCommonMocks(page, recorder);
    await page.addInitScript((value) => {
      window.localStorage.setItem('complaintGenerator.did', value);
    }, did);

    await page.goto('/workspace?shell_mode=operator');
    await waitForWorkspaceReady(page);

    await page.getByRole('button', { name: 'UX Audit', exact: true }).click();
    await expect(page.locator('#focus-rail-stage')).toContainText(/You are in UX Audit\./i);
    await page.locator('#ux-review-provider').fill('llm_router');
    await page.locator('#ux-review-model').fill('multimodal_router');
    await page.locator('#run-ux-review-button').click();

    await expect(page.locator('#workspace-status')).toContainText(/Iterative UI\/UX review completed\./i, { timeout: 15000 });
    await expect(page.locator('#ux-review-runtime')).toContainText(/Latest review artifacts/i);
    await expect(page.getByRole('button', { name: 'Open Latest JSON' })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Open Latest Markdown' })).toBeVisible();

    await page.getByRole('button', { name: 'Open Latest JSON' }).click();
    await expect(page.locator('#workspace-status')).toContainText(/Opened latest json artifact reference:/i);
    await expect(page.locator('#workspace-status')).toContainText(/iteration-01-review\.json/i);
    await expect(page.locator('#ux-review-artifacts')).toContainText(/Latest review JSON artifact/i);

    await page.getByRole('button', { name: 'Open Latest Markdown' }).click();
    await expect(page.locator('#workspace-status')).toContainText(/Opened latest markdown artifact reference:/i);
    await expect(page.locator('#workspace-status')).toContainText(/iteration-01-review\.md/i);
    await expect(page.locator('#ux-review-artifacts')).toContainText(/Latest review markdown artifact/i);
  });

  test('workspace Gmail DuckDB controls run through the browser MCP flow and surface searchable evidence results', async ({ page }) => {
    const recorder = {};
    const did = `did:key:workspace-gmail-duckdb-${Date.now()}`;
    await installCommonMocks(page, recorder);
    await page.addInitScript((value) => {
      window.localStorage.setItem('complaintGenerator.did', value);
    }, did);
    await page.goto('/workspace?shell_mode=operator');
    await waitForWorkspaceReady(page);

    await page.getByRole('button', { name: 'Evidence', exact: true }).click();
    await expect(page.locator('[data-tab-panel="evidence"]')).toHaveClass(/is-active/);
    await page.locator('#evidence-advanced-imports summary').click();
    await expect(page.locator('#run-gmail-duckdb-pipeline-button')).toBeVisible();
    await expect(page.locator('#search-email-duckdb-button')).toBeVisible();
    await expect(page.locator('#gmail-import-cli-command')).toContainText(/import-gmail-evidence/i);
    await expect(page.locator('#gmail-pipeline-summary-preview')).toContainText(/No Gmail DuckDB pipeline has been run/i);
    await expect(page.locator('#email-duckdb-search-preview')).toContainText(/No DuckDB email search has been run/i);

    await page.locator('#gmail-import-addresses').fill('hr@acme.example\nlegal@acme.example');
    await page.locator('#gmail-import-user').fill('workspace-user@acme.example');
    await page.locator('#gmail-import-password').fill('app-password-for-playwright');
    await page.locator('#gmail-import-complaint-query').fill('subject:(termination OR retaliation)');
    await page.locator('#gmail-pipeline-bm25-query').fill('termination retaliation timeline');
    await page.locator('#run-gmail-duckdb-pipeline-button').click();

    await expect(page.locator('#workspace-status')).toContainText(/Gmail DuckDB pipeline completed with 2 imported message\(s\)\./i);
    await expect(page.locator('#gmail-pipeline-summary-preview')).toContainText(/Pipeline: gmail_duckdb_pipeline/i);
    await expect(page.locator('#gmail-pipeline-summary-preview')).toContainText(/Imported count: 2/i);
    await expect(page.locator('#gmail-pipeline-summary-preview')).toContainText(/BM25 query: termination retaliation timeline/i);
    await expect(page.locator('#gmail-pipeline-summary-preview')).toContainText(/DuckDB path: \/tmp\/playwright-email-corpus\.duckdb/i);
    await expect(page.locator('#gmail-pipeline-summary-chips')).toContainText(/duckdb ready/i);
    await expect(page.locator('#email-duckdb-index-path')).toHaveValue('/tmp/playwright-email-corpus.duckdb');

    await page.locator('#email-duckdb-query').fill('retaliation follow-up');
    await page.locator('#search-email-duckdb-button').click();

    await expect(page.locator('#workspace-status')).toContainText(/DuckDB email search completed with 2 hit\(s\)\./i);
    await expect(page.locator('#email-duckdb-search-preview')).toContainText(/Query: retaliation follow-up/i);
    await expect(page.locator('#email-duckdb-search-preview')).toContainText(/Index path: \/tmp\/playwright-email-corpus\.duckdb/i);
    await expect(page.locator('#email-duckdb-search-preview')).toContainText(/Top results:/i);
    await expect(page.locator('#email-duckdb-search-preview')).toContainText(/Termination email/i);
    await expect(page.locator('#email-duckdb-search-preview')).toContainText(/HR retaliation follow-up/i);

    await page.goto('/workspace?shell_mode=operator');
    await waitForWorkspaceReady(page, { requireIntakeVisible: false });
    await page.getByRole('button', { name: 'CLI + MCP', exact: true }).click();
    await page.locator('#refresh-tooling-contract-button').click();
    await expect(page.locator('#workspace-status')).toContainText(/Tooling contract refreshed\./i);
    await expect(page.locator('#tool-list')).toContainText(/complaint\.run_gmail_duckdb_pipeline/i);
    await expect(page.locator('#tool-list')).toContainText(/complaint\.search_email_duckdb_corpus/i);
    await expect(page.locator('#tooling-contract-preview')).toContainText(/run_gmail_duckdb_pipeline/i);
    await expect(page.locator('#tooling-contract-preview')).toContainText(/search_email_duckdb_corpus/i);
    await expect(page.locator('#tooling-contract-preview')).toContainText(/runGmailDuckdbPipeline/i);
    await expect(page.locator('#tooling-contract-preview')).toContainText(/searchEmailDuckdb/i);
    await expect(page.locator('#tooling-contract-preview')).toContainText(/gmail_duckdb_pipeline/i);
    await expect(page.locator('#tooling-contract-preview')).toContainText(/email_duckdb_search/i);
  });

  test('homepage to workspace journey ends with an actual generated complaint, downloadable markdown/pdf exports, and packet analysis', async ({ page }, testInfo) => {
    const did = `did:key:workspace-homepage-flow-${Date.now()}`;
    await page.addInitScript((did) => {
      window.localStorage.setItem('complaintGenerator.did', did);
    }, did);
    await page.goto('/');

    await expect(page.locator('#homepage-open-intake')).toBeVisible();
    await expect(page.locator('#homepage-open-workspace')).toBeVisible();
    await expect(page.getByRole('link', { name: 'Start Secure Intake', exact: true })).toHaveCount(1);
    await expect(page.locator('#homepage-nav-builder')).toHaveAttribute('aria-disabled', 'true');
    await expect(page.locator('#homepage-resume-builder')).toHaveAttribute('aria-disabled', 'true');
    await expect(page.locator('#homepage-complaint-readiness-summary')).toContainText(/Not ready to draft|Still building the record|Ready for first draft|Draft in progress/i);
    await expect(page.locator('#homepage-open-workspace')).toHaveAttribute('href', /\/workspace/);
    await writeUiScreenshotArtifact(page, { name: 'workspace-homepage', title: 'Homepage Entry', locator: '.hero', maxHeight: 1000 });

    await page.goto('/workspace?shell_mode=operator');
    await expect(page).toHaveURL(/\/workspace/);
    await waitForWorkspaceReady(page);
    await expect(page.locator('#save-intake-button')).toBeVisible();
    await expect.poll(async () => page.locator('#intake-question-grid textarea').count()).toBeGreaterThan(0);
    await expect(page.locator('#intake-party_name')).toBeVisible();

    await fillIntakeWizardField(page, 'party_name', 'Taylor Smith');
    await fillIntakeWizardField(page, 'opposing_party', 'Acme Logistics');
    await fillIntakeWizardField(page, 'protected_activity', 'Reported wage-and-hour violations to HR');
    await fillIntakeWizardField(page, 'adverse_action', 'Was terminated three days later');
    await fillIntakeWizardField(page, 'timeline', 'Report on April 2, termination on April 5');
    await fillIntakeWizardField(page, 'harm', 'Lost wages, benefits, and housing stability');
    await expect(page.locator('[data-tab-panel="intake"]')).toContainText(/Court details are optional and can wait until the story is clear/i);
    await expect(page.locator('#intake-court-details')).toContainText(/Court details \(optional\)/i);
    await fillIntakeWizardField(page, 'court_header', 'FOR THE NORTHERN DISTRICT OF CALIFORNIA');
    await expect(page.locator('#intake-caption-preview')).toContainText(/Taylor Smith, Plaintiff,/i);
    await expect(page.locator('#intake-caption-preview')).toContainText(/Acme Logistics, Defendant\./i);
    await expect(page.locator('#intake-caption-preview')).toContainText(/FOR THE NORTHERN DISTRICT OF CALIFORNIA/i);
    await expect(page.locator('#intake-caption-preview')).toContainText(/COMPLAINT FOR RETALIATION/i);
    await expect(page.locator('#intake-caption-preview')).toContainText(/JURY TRIAL DEMANDED/i);
    await expect(page.locator('#intake-caption-preview')).toContainText(/COUNT I - RETALIATION/i);
    await expect(page.locator('#intake-caption-preview')).toContainText(/Requested relief will appear here once it is entered in the draft panel/i);
    await writeUiScreenshotArtifact(page, { name: 'workspace-intake', title: 'Workspace Intake', locator: '[data-tab-panel="intake"]', maxHeight: 2600 });
    await page.locator('#save-intake-button').click();
    await expect(page.locator('#workspace-status')).toContainText(/Intake answers saved\./i, { timeout: 15000 });
    await expect(page.locator('#next-question-label')).toContainText(/Intake complete/i, { timeout: 15000 });

    await page.locator('#case-synopsis').fill('Taylor Smith alleges retaliation after reporting wage-and-hour violations, and the central question is whether the timing and employer motive can be corroborated well enough for filing.');
    await page.locator('#save-synopsis-button').click();
    await expect(page.locator('#review-synopsis-preview')).toContainText(/Taylor Smith alleges retaliation/i);

    await expect(page.locator('#handoff-chat-button')).toHaveAttribute('href', /Taylor%20Smith|Taylor\+Smith|Taylor Smith/i);
    await page.locator('#handoff-chat-button').click();
    await expect(page).toHaveURL(/\/chat\?/);
    await expect(page.locator('#chat-context-summary')).toContainText(/Taylor Smith alleges retaliation/i);
    await expect(page.locator('#chat-form input')).toHaveValue(/Mediator, help turn this into testimony-ready narrative/i);

    await page.goto('/workspace?shell_mode=operator');
    await waitForWorkspaceReady(page);
    await page.getByRole('button', { name: 'Evidence', exact: true }).click();
    await page.locator('#evidence-kind').selectOption('testimony');
    await page.locator('#evidence-claim-element').selectOption('causation');
    await page.locator('#evidence-title').fill('Mediator follow-up statement');
    await page.locator('#evidence-source').fill('Chat mediator summary');
    await page.locator('#evidence-content').fill('I reported wage-and-hour violations to HR, and the termination followed three days later without any other explanation.');
    await page.locator('#save-evidence-button').click();
    await expect(page.locator('#evidence-list')).toContainText(/Mediator follow-up statement/i);

    await page.locator('#evidence-kind').selectOption('document');
    await page.locator('#evidence-claim-element').selectOption('causation');
    await page.locator('#evidence-title').fill('Termination timeline email');
    await page.locator('#evidence-source').fill('Email archive');
    await page.locator('#evidence-content').fill('Email records show Taylor Smith was terminated immediately after reporting wage-and-hour violations.');
    await page.locator('#evidence-attachment').setInputFiles({
      name: 'termination-email.txt',
      mimeType: 'text/plain',
      buffer: Buffer.from('April 2: HR report. April 5: termination notice.'),
    });
    await page.locator('#save-evidence-button').click();
    await expect(page.locator('#evidence-list')).toContainText(/Termination timeline email/i);
    await expect(page.locator('#evidence-list')).toContainText(/termination-email\.txt/i);
    await expect(page.locator('#evidence-advanced-imports summary')).toContainText(/Advanced imports and operator tools/i);
    await writeUiScreenshotArtifact(page, { name: 'workspace-evidence', title: 'Workspace Evidence', locator: '[data-tab-panel="evidence"]', maxHeight: 4500 });
    await page.locator('#evidence-advanced-imports summary').click();
    await expect(page.locator('#gmail-import-cli-command')).toContainText(/import-gmail-evidence/i);
    await expect(page.locator('#gmail-import-mcp-command')).toContainText(/complaint\.import_gmail_evidence/i);
    await expect(page.locator('#import-gmail-evidence-button')).toBeVisible();
    await expect(page.locator('#gmail-import-cli-help')).toContainText(/keyring-backed Gmail app password reuse/i);

    await page.getByRole('button', { name: 'Review', exact: true }).click();
    await expect(page.locator('#support-grid')).toContainText(/Protected activity/i);
    await expect(page.locator('#review-synopsis-preview')).toContainText(/Taylor Smith alleges retaliation/i);
    await writeUiScreenshotArtifact(page, { name: 'workspace-review', title: 'Workspace Review', locator: '[data-tab-panel="review"]', maxHeight: 4600 });

    await page.getByRole('button', { name: 'Draft', exact: true }).click();
    await expect(page.locator('.draft-section-nav')).toContainText(/Caption/i);
    await expect(page.locator('#draft-placeholder-resolver')).toContainText(/Resolve filing placeholders/i);
    await page.locator('#requested-relief').fill('Back pay\nFront pay\nAttorney fees');
    await page.locator('#draft-civil-action-number').fill('25-cv-1234');
    await expect(page.locator('#draft-caption-preview')).toContainText(/Civil Action No\. 25-cv-1234/i);
    await page.locator('#draft-clear-civil-action-button').click();
    await expect(page.locator('#draft-caption-preview')).toContainText(/PRAYER FOR RELIEF/i);
    await expect(page.locator('#draft-caption-preview')).toContainText(/1\. Back pay/i);
    await expect(page.locator('#draft-caption-preview')).toContainText(/2\. Front pay/i);
    await expect(page.locator('#draft-caption-preview')).toContainText(/3\. Attorney fees/i);
    await page.locator('#generate-draft-button').click();

    await expect(page.locator('#draft-preview')).toContainText(/Taylor Smith brings this retaliation complaint/i);
    await expect(page.locator('#draft-preview')).toContainText(/Civil Action No\./i);
    await expect(page.locator('#draft-preview')).toContainText(/EVIDENTIARY SUPPORT AND NOTICE/i);
    await expect(page.locator('#draft-preview')).toContainText(/COUNT I - RETALIATION/i);
    await expect(page.locator('#draft-preview')).not.toContainText(/Working case synopsis:/i);
    await expect(page.locator('#draft-title')).toHaveValue(/Taylor Smith v\. Acme Logistics Retaliation Complaint/i);
    await expect(page.locator('#draft-contract-preview')).toContainText(/Claim type: Retaliation/i);
    await expect(page.locator('#draft-contract-preview')).toContainText(/Drafting mode: llm_router formal complaint path/i);
    await expect(page.locator('#draft-readiness-preview')).toContainText(/Evidence items: 2/i);
    await writeUiScreenshotArtifact(page, { name: 'workspace-draft', title: 'Workspace Draft', locator: '[data-tab-panel="draft"]', maxHeight: 7500 });

    await page.getByRole('button', { name: 'Evidence', exact: true }).click();
    await expect(page.locator('#draft-status')).toContainText(/Draft in progress|Draft updated/i);
    await expect(page.locator('#progress-step-draft')).toContainText(/complaint draft exists|draft exists/i);
    await expect(page.locator('[data-tab-panel="evidence"]')).not.toContainText(/No draft generated yet\./i);
    await writeUiScreenshotArtifact(page, { name: 'workspace-evidence', title: 'Workspace Evidence', locator: '[data-tab-panel="evidence"]', maxHeight: 4500 });

    await page.getByRole('button', { name: 'Review', exact: true }).click();
    await expect(page.locator('#draft-status')).toContainText(/Draft in progress|Draft updated/i);
    await expect(page.locator('#progress-step-draft')).toContainText(/complaint draft exists|draft exists/i);
    await expect(page.locator('[data-tab-panel="review"]')).not.toContainText(/No draft generated yet\./i);
    await writeUiScreenshotArtifact(page, { name: 'workspace-review', title: 'Workspace Review', locator: '[data-tab-panel="review"]', maxHeight: 4600 });

    await page.getByRole('button', { name: 'CLI + MCP', exact: true }).click();
    await page.locator('#refresh-complaint-readiness-button').click();
    await expect(page.locator('#workspace-status')).toContainText(/Complaint readiness refreshed/i);
    await expect(page.locator('#complaint-readiness-preview')).toContainText(/"verdict":\s*"Draft in progress"/i);
    await expect(page.locator('#complaint-readiness-preview')).toContainText(/"has_draft":\s*true/i);
    await page.locator('#refresh-client-release-gate-button').click();
    await expect(page.locator('#workspace-status')).toContainText(/Client release gate refreshed/i);
    await expect(page.locator('#client-release-gate-preview')).toContainText(/"verdict":\s*"(client_safe|warning|blocked)"/i);
    await expect(page.locator('#client-release-gate-preview')).toContainText(/"complaint_output_release_gate":/i);
    await page.locator('#refresh-formal-diagnostics-button').click();
    await expect(page.locator('#formal-diagnostics-preview')).toContainText(/Formal complaint posture summary/i, { timeout: 15000 });
    await expect(page.locator('#formal-diagnostics-preview')).toContainText(/Filing shape score:/i, { timeout: 15000 });
    await expect(page.locator('#formal-diagnostics-preview')).toContainText(/Formal critic route:/i, { timeout: 15000 });
    await expect(page.locator('#formal-diagnostics-preview')).toContainText(/formal_complaint_reviewer/i, { timeout: 15000 });
    await expect(page.locator('#formal-diagnostics-preview')).toContainText(/"complaint_output_router_backend":/i, { timeout: 15000 });
    await expect(page.locator('#formal-diagnostics-preview')).toContainText(/Top UI repair suggestions:/i, { timeout: 15000 });
    await page.locator('#refresh-provider-diagnostics-button').click();
    await expect(page.locator('#workspace-status')).toContainText(/Provider diagnostics refreshed\./i);
    await expect(page.locator('#provider-diagnostics-preview')).toContainText(/Router provider diagnostics/i);
    await expect(page.locator('#provider-diagnostics-preview')).toContainText(/Complaint draft default: codex_cli/i);
    await expect(page.locator('#provider-diagnostics-preview')).toContainText(/Complaint draft fallback chain: codex_cli -> copilot_cli -> hf_inference_api/i);
    await expect(page.locator('#provider-diagnostics-preview')).toContainText(/Preference order: codex_cli -> copilot_cli -> openai -> hf_inference_api/i);
    await expect(page.locator('#provider-diagnostics-preview')).toContainText(/copilot_cli:/i);

    await page.locator('#export-packet-tool-button').click();
    await expect(page.locator('#packet-export-summary')).toContainText(/"has_draft": true/i);
    await expect(page.locator('#packet-export-summary')).toContainText(/"complaint_readiness":/i);
    await expect(page.locator('#packet-export-summary')).toContainText(/"artifact_formats":/i);
    await expect(page.locator('#packet-export-summary')).toContainText(/"draft_strategy":\s*"llm_router"/i);
    await expect(page.locator('#packet-export-summary')).toContainText(/docx/i);
    await expect(page.locator('#packet-preview')).toContainText(/Title: Taylor Smith v\. Acme Logistics Retaliation Complaint/i);
    await expect(page.locator('#packet-preview')).toContainText(/Taylor Smith brings this retaliation complaint against Acme Logistics\./i);
    await expect(page.locator('#packet-preview')).toContainText(/Civil Action No\./i);
    await expect(page.locator('#packet-preview')).toContainText(/COUNT I - RETALIATION/i);

    await page.locator('#analyze-complaint-output-button').click();
    await expect(page.locator('#workspace-status')).toContainText(/Complaint output analysis refreshed\./i);
    await page.getByRole('button', { name: 'Draft', exact: true }).click();
    await expect(page.locator('#draft-readiness-preview')).toContainText(/Release gate verdict:/i);
    await expect(page.locator('#draft-release-gate-summary')).toContainText(/Release gate verdict:/i);
    await expect(page.locator('#draft-release-gate-summary')).toContainText(/Top defect:/i);
    await expect(page.locator('#draft-release-gate-next-step')).toContainText(/Next safest move:/i);
    await page.locator('#draft-release-open-integrations-button').click();
    await expect(page.locator('[data-tab-panel="integrations"]')).toHaveClass(/is-active/);
    await expect(page.locator('#workspace-status')).toContainText(/Opened CLI \+ MCP from the draft release gate/i);
    await page.getByRole('button', { name: 'Draft', exact: true }).click();
    await page.getByRole('button', { name: 'CLI + MCP', exact: true }).click();
    await expect(page.locator('#complaint-output-analysis-preview')).toContainText(/"ui_feedback":/i);
    await expect(page.locator('#complaint-output-analysis-preview')).toContainText(/Release gate: (PASS|WARNING)/i);
    await expect(page.locator('#complaint-output-analysis-preview')).toContainText(/Complaint-output critic route:/i);
    await expect(page.locator('#complaint-output-analysis-preview')).toContainText(/formal_complaint_reviewer/i);
    await expect(page.locator('#complaint-output-analysis-preview')).toContainText(/"filing_shape_score":\s*[7-9]\d|"filing_shape_score":\s*100/i);
    await expect(page.locator('#complaint-output-analysis-preview')).toContainText(/"formal_sections_present":/i);
    await expect(page.locator('#complaint-output-analysis-preview')).toContainText(/"router_review":/i);
    await expect(page.locator('#complaint-output-analysis-preview')).toContainText(/"strategy":\s*"llm_router"/i);
    await expect(page.locator('#complaint-output-analysis-preview')).toContainText(/Tighten review-to-draft gatekeeping/i);
    await expect(page.locator('#complaint-output-analysis-preview')).toContainText(/"artifact_analysis":/i);
    await expect(page.locator('#claim-alignment-preview')).toContainText(/"release_gate_verdict":\s*"(pass|warning)"/i);

    await page.locator('#review-generated-exports-button').click();
    await expect(page.locator('#workspace-status')).toContainText(/export critic/i);
    await expect(page.locator('#complaint-output-analysis-preview')).toContainText(/"export_critic":/i);
    await expect(page.locator('#complaint-output-analysis-preview')).toContainText(/"average_filing_shape_score":\s*[7-9]\d|"average_filing_shape_score":\s*100/i);
    await expect(page.locator('#complaint-output-analysis-preview')).toContainText(/"average_claim_type_alignment_score":\s*[7-9]\d|"average_claim_type_alignment_score":\s*100/i);
    await expect(page.locator('#complaint-output-analysis-preview')).toContainText(/"router_backends":/i);
    await expect(page.locator('#complaint-output-analysis-preview')).toContainText(/formal_complaint_reviewer/i);
    await page.getByRole('button', { name: 'UX Audit', exact: true }).click();
    await expect(page.locator('#ux-review-repair-brief')).toContainText(/Complaint-output optimizer repair brief/i);
    await expect(page.locator('#ux-review-repair-brief')).toContainText(/critic gate:/i);
    await expect(page.locator('#ux-review-repair-brief')).toContainText(/critic route: llm_router \/ formal_complaint_reviewer/i);
    await expect(page.locator('#ux-review-repair-brief')).toContainText(/Recommended UI surfaces:/i);
    await expect(page.locator('#ux-review-repair-brief')).toContainText(/draft, review, integrations/i);
    await page.locator('#ux-review-repair-brief').getByRole('button', { name: 'Open Draft' }).click();
    await expect(page.locator('[data-tab-panel="draft"]')).toHaveClass(/is-active/);
    await expect(page.locator('#workspace-status')).toContainText(/Opened Draft from the optimizer repair brief/i);
    await page.getByRole('button', { name: 'UX Audit', exact: true }).click();
    await page.locator('#ux-review-repair-brief').getByRole('button', { name: 'Open CLI + MCP' }).click();
    await expect(page.locator('[data-tab-panel="integrations"]')).toHaveClass(/is-active/);
    await expect(page.locator('#workspace-status')).toContainText(/Opened CLI \+ MCP from the optimizer repair brief/i);
    await page.locator('#refresh-filing-provenance-button').click();
    await expect(page.locator('#workspace-status')).toContainText(/Filing provenance refreshed\./i);
    await expect(page.locator('#filing-provenance-preview')).toContainText(/Filing provenance summary/i);
    await expect(page.locator('#filing-provenance-preview')).toContainText(/Draft generation route: llm_router/i);
    await expect(page.locator('#filing-provenance-preview')).toContainText(/Complaint-output critic route:.*formal_complaint_reviewer/i);
    await expect(page.locator('#filing-provenance-preview')).toContainText(/UI review route:.*multimodal_router/i);
    await writeUiScreenshotArtifact(page, { name: 'workspace-integrations', title: 'Workspace Integrations', locator: '[data-tab-panel="integrations"]', maxHeight: 4200 });
    await page.getByRole('button', { name: 'CLI + MCP', exact: true }).click();

    const [markdownDownload] = await Promise.all([
      page.waitForEvent('download'),
      page.locator('#download-packet-tool-markdown-button').click(),
    ]);
    const markdownPath = testInfo.outputPath(markdownDownload.suggestedFilename());
    await markdownDownload.saveAs(markdownPath);
    const markdownBody = await fs.readFile(markdownPath, 'utf-8');
    expect(markdownDownload.suggestedFilename()).toMatch(/taylor-smith-v\.?-acme-logistics-retaliation-complaint\.md$/i);
    expect(markdownBody.startsWith('IN THE UNITED STATES DISTRICT COURT')).toBeTruthy();
    expect(markdownBody).toContain('FOR THE NORTHERN DISTRICT OF CALIFORNIA');
    expect(markdownBody).toContain('Taylor Smith brings this retaliation complaint against Acme Logistics.');
    expect(markdownBody).toContain('Plaintiff Taylor Smith, proceeding pro se, alleges upon personal knowledge');
    expect(markdownBody).toContain('engaged in protected activity by reporting wage-and-hour violations to HR.');
    expect(markdownBody).toContain('The relevant chronology is as follows: Plaintiff made the report on April 2, and the termination occurred on April 5.');
    expect(markdownBody).toContain("The witness proof currently identified includes: testimony presently identified as 'Mediator follow-up statement' on the causal link element.");
    expect(markdownBody).toContain("Plaintiff presently identifies the following documents, exhibits, or records in support of this pleading: documentary exhibit presently identified as 'Termination timeline email' on the causal link element.");
    expect(markdownBody).toContain("Plaintiff expects to offer testimony presently identified as 'Mediator follow-up statement' in support of the causal link element.");
    expect(markdownBody).toContain("Plaintiff expects to offer documentary exhibit 'Termination timeline email' in support of the causal link element.");
    expect(markdownBody).toContain('That protected activity constituted protected opposition, reporting, or participation activity under the governing anti-retaliation framework.');
    expect(markdownBody).toContain('Within days of that protected activity, Defendant took materially adverse action against Plaintiff by terminating Plaintiff three days later.');
    expect(markdownBody).toContain('Defendant thereafter subjected Plaintiff to materially adverse action by terminating Plaintiff three days later, under circumstances supporting a causal inference of retaliation.');
    expect(markdownBody).toContain('The close temporal proximity, Defendant\'s knowledge of the protected activity, the evidentiary record, and the resulting harm plausibly support a retaliation claim and entitle Plaintiff to relief.');
    expect(markdownBody).toContain("As a direct and proximate result of Defendant's retaliatory conduct, Plaintiff is entitled to recover damages, equitable relief, fees and costs where available, and such further relief as the Court deems just and proper.");
    expect(markdownBody).toContain('17. Plaintiff repeats and realleges the preceding paragraphs as if fully set forth herein.');
    expect(markdownBody).toContain('21. Plaintiff has sustained damages and losses including lost wages, benefits, and housing stability.');
    expect(markdownBody).toContain('Wherefore, Plaintiff respectfully requests judgment against Defendant on the retaliation claim alleged herein and seeks the following relief:');
    expect(markdownBody).toContain("3. Reasonable attorney's fees and costs.");
    expect(markdownBody).toContain('Civil Action No. ________________');
    expect(markdownBody).toContain('EVIDENTIARY SUPPORT AND NOTICE');
    expect(markdownBody).toContain('COUNT I - RETALIATION');
    expect(markdownBody).toContain('SIGNATURE BLOCK');
    expect(markdownBody).toContain('Plaintiff, Pro Se');
    expect(markdownBody).toContain('Address: ____________________');
    expect(markdownBody).not.toContain('APPENDIX A - CASE SYNOPSIS');
    expect(markdownBody).not.toContain('APPENDIX B - REQUESTED RELIEF CHECKLIST');
    expect(markdownBody).not.toContain('WORKING CASE SYNOPSIS');

    const [pdfDownload] = await Promise.all([
      page.waitForEvent('download'),
      page.locator('#download-packet-tool-pdf-button').click(),
    ]);
    const pdfPath = testInfo.outputPath(pdfDownload.suggestedFilename());
    await pdfDownload.saveAs(pdfPath);
    const pdfBody = await fs.readFile(pdfPath);
    expect(pdfDownload.suggestedFilename()).toMatch(/taylor-smith-v\.?-acme-logistics-retaliation-complaint\.pdf$/i);
    expect(pdfBody.subarray(0, 8).toString('utf-8')).toContain('%PDF-1.4');
    expect(pdfBody.toString('utf-8')).toContain('COMPLAINT FOR RETALIATION');
    expect(pdfBody.toString('utf-8')).toContain('SIGNATURE BLOCK');

    const [docxDownload] = await Promise.all([
      page.waitForEvent('download'),
      page.locator('#download-packet-tool-docx-button').click(),
    ]);
    const docxPath = testInfo.outputPath(docxDownload.suggestedFilename());
    await docxDownload.saveAs(docxPath);
    const docxBody = await fs.readFile(docxPath);
    expect(docxDownload.suggestedFilename()).toMatch(/taylor-smith-v\.?-acme-logistics-retaliation-complaint\.docx$/i);
    expect(docxBody.subarray(0, 2).toString('utf-8')).toBe('PK');

    await writeComplaintExportArtifact({
      routeUrl: page.url(),
      markdownFilename: markdownDownload.suggestedFilename(),
      markdownText: markdownBody,
      pdfFilename: pdfDownload.suggestedFilename(),
      pdfBuffer: pdfBody,
      docxFilename: docxDownload.suggestedFilename(),
      docxBuffer: docxBody,
      uiSuggestionsExcerpt: await page.locator('#complaint-output-analysis-preview').textContent(),
      claimType: 'retaliation',
      draftStrategy: 'llm_router',
      filingShapeScore: 100,
      claimTypeAlignmentScore: 100,
    });

    await page.goto('/');
    await expect(page.locator('#homepage-complaint-readiness-summary')).toContainText(/Ready for first draft|Draft in progress/i);
    await expect(page.locator('#homepage-next-step')).toContainText(/draft|builder|revis/i);
  });

  test('workspace can switch complaint type and use the llm_router drafting path for a formal housing complaint', async ({ page }, testInfo) => {
    const did = `did:key:workspace-housing-flow-${Date.now()}`;
    await page.addInitScript((did) => {
      window.localStorage.setItem('complaintGenerator.did', did);
    }, did);
    await page.goto('/workspace?shell_mode=operator');
    await waitForWorkspaceReady(page);

    await revealAllIntakeFields(page);
    await page.locator('#intake-party_name').fill('Morgan Lee');
    await page.locator('#intake-opposing_party').fill('Acme Housing Authority');
    await page.locator('#intake-protected_activity').fill('Requested a disability accommodation and complained about discriminatory housing treatment');
    await page.locator('#intake-adverse_action').fill('Was denied continued housing assistance and threatened with eviction');
    await page.locator('#intake-timeline').fill('Accommodation request on May 2, denial notice on May 5, eviction threat on May 7');
    await page.locator('#intake-harm').fill('Risked losing housing stability and incurred out-of-pocket relocation costs');
    await page.locator('#intake-court_header').fill('FOR THE NORTHERN DISTRICT OF CALIFORNIA');
    await page.locator('#save-intake-button').click();
    await expect(page.locator('#workspace-status')).toContainText(/Intake answers saved\./i, { timeout: 15000 });
    await expect(page.locator('#next-question-label')).toContainText(/Intake complete/i, { timeout: 15000 });

    await page.getByRole('button', { name: 'Evidence', exact: true }).click();
    await page.locator('#evidence-kind').selectOption('document');
    await page.locator('#evidence-claim-element').selectOption('causation');
    await page.locator('#evidence-title').fill('Accommodation denial notice');
    await page.locator('#evidence-source').fill('Housing portal download');
    await page.locator('#evidence-content').fill('The denial notice and eviction warning followed immediately after the accommodation request and complaint.');
    await page.locator('#save-evidence-button').click();
    await expect(page.locator('#evidence-list')).toContainText(/Accommodation denial notice/i);

    await page.getByRole('button', { name: 'Draft', exact: true }).click();
    await page.locator('#draft-claim-type').selectOption('housing_discrimination');
    await expect(page.locator('#draft-mode')).toHaveValue('llm_router');
    await page.locator('#requested-relief').fill('Injunctive relief\nCompensatory damages\nDeclaratory relief');
    await page.locator('#generate-draft-button').click();

    await expect(page.locator('#workspace-status')).toContainText(/llm_router formal complaint path/i);
    await expect(page.locator('#draft-generation-meta')).toContainText(/Draft strategy: llm_router/i);
    await expect(page.locator('#draft-generation-meta')).toContainText(/Claim type: housing discrimination/i);
    await expect(page.locator('#draft-contract-preview')).toContainText(/Claim type: Housing Discrimination/i);
    await expect(page.locator('#draft-contract-preview')).toContainText(/Expected count heading: COUNT I - HOUSING DISCRIMINATION/i);
    await expect(page.locator('#draft-preview')).toContainText(/COMPLAINT FOR HOUSING DISCRIMINATION/i);
    await expect(page.locator('#draft-preview')).toContainText(/Morgan Lee brings this housing discrimination complaint against Acme Housing Authority\./i);
    await expect(page.locator('#draft-preview')).toContainText(/COUNT I - HOUSING DISCRIMINATION/i);
    await expect(page.locator('#draft-title')).toHaveValue(/Morgan Lee v\. Acme Housing Authority Housing Discrimination Complaint/i);

    await page.getByRole('button', { name: 'CLI + MCP', exact: true }).click();
    await page.locator('#refresh-capabilities-button').click();
    await expect(page.locator('#workflow-capabilities-preview')).toContainText(/Claim-type drafting alignment/i);
    await expect(page.locator('#workflow-capabilities-preview')).toContainText(/Formal complaint generation/i);
    await expect(page.locator('#workflow-capabilities-preview')).toContainText(/housing discrimination/i);
    await expect(page.locator('#workflow-capabilities-preview')).toContainText(/llm_router-backed formal complaint generation/i);
    await page.locator('#export-packet-tool-button').click();
    await expect(page.locator('#packet-preview')).toContainText(/COMPLAINT FOR HOUSING DISCRIMINATION/i);
    await expect(page.locator('#packet-export-summary')).toContainText(/"draft_strategy":\s*"llm_router"/i);

    await page.locator('#analyze-complaint-output-button').click();
    await expect(page.locator('#complaint-output-analysis-preview')).toContainText(/Release gate: (PASS|WARNING)/i);
    await expect(page.locator('#complaint-output-analysis-preview')).toContainText(/Complaint-output critic route:/i);
    await expect(page.locator('#complaint-output-analysis-preview')).toContainText(/formal_complaint_reviewer/i);
    await expect(page.locator('#complaint-output-analysis-preview')).toContainText(/"filing_shape_score":\s*[7-9]\d|"filing_shape_score":\s*100/i);
    await expect(page.locator('#complaint-output-analysis-preview')).toContainText(/"formal_sections_present":/i);
    await expect(page.locator('#complaint-output-analysis-preview')).toContainText(/"router_review":/i);
    await page.getByRole('button', { name: 'Draft', exact: true }).click();
    await expect(page.locator('#draft-readiness-preview')).toContainText(/Release gate verdict:/i);
    await page.getByRole('button', { name: 'CLI + MCP', exact: true }).click();
    await page.locator('#review-generated-exports-button').click();
    await expect(page.locator('#complaint-output-analysis-preview')).toContainText(/"export_critic":/i);
    await expect(page.locator('#complaint-output-analysis-preview')).toContainText(/"router_backends":/i);
    await expect(page.locator('#claim-alignment-preview')).toContainText(/"release_gate_verdict":\s*"(pass|warning)"/i);
    const housingAnalysisText = await page.locator('#complaint-output-analysis-preview').textContent();
    expect(housingAnalysisText).toMatch(/Housing Discrimination/i);

    const [housingMarkdownDownload] = await Promise.all([
      page.waitForEvent('download'),
      page.locator('#download-packet-tool-markdown-button').click(),
    ]);
    const housingMarkdownPath = testInfo.outputPath(housingMarkdownDownload.suggestedFilename());
    await housingMarkdownDownload.saveAs(housingMarkdownPath);
    const housingMarkdownBody = await fs.readFile(housingMarkdownPath, 'utf-8');
    expect(housingMarkdownDownload.suggestedFilename()).toMatch(/morgan-lee-v\.?-acme-housing-authority-housing-discrimination-complaint\.md$/i);
    expect(housingMarkdownBody.startsWith('IN THE UNITED STATES DISTRICT COURT')).toBeTruthy();
    expect(housingMarkdownBody).toContain('FOR THE NORTHERN DISTRICT OF CALIFORNIA');
    expect(housingMarkdownBody).toContain('COMPLAINT FOR HOUSING DISCRIMINATION');
    expect(housingMarkdownBody).toContain('COUNT I - HOUSING DISCRIMINATION');
    expect(housingMarkdownBody).toContain('Morgan Lee brings this housing discrimination complaint against Acme Housing Authority.');
    expect(housingMarkdownBody).toContain('JURY TRIAL DEMANDED');
    expect(housingMarkdownBody).toContain('SIGNATURE BLOCK');
    expect(housingMarkdownBody).not.toContain('APPENDIX A - CASE SYNOPSIS');

    const [housingPdfDownload] = await Promise.all([
      page.waitForEvent('download'),
      page.locator('#download-packet-tool-pdf-button').click(),
    ]);
    const housingPdfPath = testInfo.outputPath(housingPdfDownload.suggestedFilename());
    await housingPdfDownload.saveAs(housingPdfPath);
    const housingPdfBody = await fs.readFile(housingPdfPath);
    expect(housingPdfDownload.suggestedFilename()).toMatch(/morgan-lee-v\.?-acme-housing-authority-housing-discrimination-complaint\.pdf$/i);
    expect(housingPdfBody.subarray(0, 8).toString('utf-8')).toContain('%PDF-1.4');
    expect(housingPdfBody.toString('utf-8')).toContain('COMPLAINT FOR HOUSING DISCRIMINATION');

    const [housingDocxDownload] = await Promise.all([
      page.waitForEvent('download'),
      page.locator('#download-packet-tool-docx-button').click(),
    ]);
    const housingDocxPath = testInfo.outputPath(housingDocxDownload.suggestedFilename());
    await housingDocxDownload.saveAs(housingDocxPath);
    const housingDocxBody = await fs.readFile(housingDocxPath);
    expect(housingDocxDownload.suggestedFilename()).toMatch(/morgan-lee-v\.?-acme-housing-authority-housing-discrimination-complaint\.docx$/i);
    expect(housingDocxBody.subarray(0, 2).toString('utf-8')).toBe('PK');
  });
});
