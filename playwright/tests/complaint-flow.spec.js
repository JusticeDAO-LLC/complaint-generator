const { test, expect } = require('@playwright/test');
const { installCommonMocks, documentGenerationResponse } = require('./helpers/fixtures');

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

    await page.locator('a[href="/document"]').first().click();
    await expect(page).toHaveURL(/\/document/);
    await expect(page.locator('body')).toContainText(/Formal Complaint Builder/i);
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

    await page.goto('/results');
    await expect(page.locator('#profile_data')).toContainText(/retaliation/i);
    await expect(page.locator('#profile_data')).toContainText(/chat_history/i);
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

    expect(recorder.documentRequests).toHaveLength(2);
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
    await expect(page.locator('a[href="/document/optimization-trace"]').first()).toBeVisible();
    await page.locator('a[href="/document/optimization-trace"]').first().click();
    await expect(page).toHaveURL(/\/document\/optimization-trace/);
    await expect(page.locator('body')).toContainText(/Optimization Trace Viewer/i);

    await page.goto('/claim-support-review');
    await expect(page.locator('a[href="/document/optimization-trace"]').first()).toBeVisible();
    await page.locator('a[href="/document"]').first().click();
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

  test('workspace unifies intake, evidence, support review, draft editing, and MCP tool visibility', async ({ page }) => {
    await page.goto('/workspace');

    await expect(page.locator('#workspace-status')).toContainText(/synchronized/i);
    await expect(page.locator('#tool-list')).toContainText(/complaint\.generate_complaint/i);
    await expect(page.locator('#did-chip')).toContainText(/did:key:/i);
    await expect.poll(async () => page.evaluate(() => localStorage.getItem('complaintGenerator.did'))).toMatch(/^did:key:/);

    await page.locator('#intake-party_name').fill('Jane Doe');
    await page.locator('#intake-opposing_party').fill('Acme Corporation');
    await page.locator('#intake-protected_activity').fill('Reported discrimination to HR');
    await page.locator('#intake-adverse_action').fill('Was terminated two days later');
    await page.locator('#intake-timeline').fill('Complaint on March 8, termination on March 10');
    await page.locator('#intake-harm').fill('Lost wages and benefits');
    await page.locator('#save-intake-button').click();

    await expect(page.locator('#next-question-label')).toContainText(/Intake complete/i);
    await page.locator('#case-synopsis').fill('Jane Doe alleges retaliation after reporting discrimination to HR, and the next priority is proving the timing and motive with corroborating evidence.');
    await page.locator('#save-synopsis-button').click();
    await expect(page.locator('#review-synopsis-preview')).toContainText(/Jane Doe alleges retaliation/i);
    await expect(page.locator('#draft-synopsis-preview')).toContainText(/next priority is proving the timing and motive/i);

    await page.locator('#handoff-chat-button').click();
    await expect(page).toHaveURL(/\/chat\?/);
    await expect(page.locator('#chat-context-summary')).toContainText(/Jane Doe alleges retaliation/i);
    await expect(page.locator('#chat-form input')).toHaveValue(/Mediator, help turn this into testimony-ready narrative/i);
    await page.goto('/workspace');

    await page.getByRole('button', { name: 'Evidence', exact: true }).click();

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
    await page.getByRole('button', { name: 'Review', exact: true }).click();
    await expect(page.locator('#support-grid')).toContainText(/Protected activity/i);
    await expect(page.locator('#recommended-actions')).toContainText(/Check timing/i);
    await expect(page.locator('#review-synopsis-preview')).toContainText(/Jane Doe alleges retaliation/i);

    await page.locator('#handoff-review-button').click();
    await expect(page).toHaveURL(/\/claim-support-review/);
    await page.goto('/workspace');

    await page.getByRole('button', { name: 'Draft', exact: true }).click();
    await page.locator('#requested-relief').fill('Back pay\nInjunctive relief');
    await page.locator('#generate-draft-button').click();
    await expect(page.locator('#draft-preview')).toContainText(/Jane Doe brings this retaliation complaint/i);
    await expect(page.locator('#draft-preview')).toContainText(/Working case synopsis: Jane Doe alleges retaliation/i);

    await page.locator('#draft-body').fill('Edited final complaint body.');
    await page.locator('#save-draft-button').click();
    await expect(page.locator('#draft-preview')).toContainText(/Edited final complaint body\./i);
    await page.locator('#export-packet-button').click();
    await expect(page.locator('#packet-preview')).toContainText(/"has_draft": true/i);

    const cachedDid = await page.evaluate(() => localStorage.getItem('complaintGenerator.did'));
    await page.reload();
    await expect.poll(async () => page.evaluate(() => localStorage.getItem('complaintGenerator.did'))).toBe(cachedDid);
    await expect(page.locator('#did-chip')).toContainText(cachedDid);
    await expect(page.locator('#draft-preview')).toContainText(/Edited final complaint body\./i);
  });
});
