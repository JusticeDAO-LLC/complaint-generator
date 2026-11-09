const { test, expect } = require('@playwright/test');

const dashboardRoutes = [
  ['/dashboards/ipfs-datasets/mcp', /IPFS Datasets MCP Dashboard/i],
  ['/dashboards/ipfs-datasets/mcp-clean', /IPFS Datasets MCP Dashboard Clean/i],
  ['/dashboards/ipfs-datasets/mcp-final', /IPFS Datasets MCP Dashboard Final/i],
  ['/dashboards/ipfs-datasets/software-mcp', /Software Engineering Dashboard/i],
  ['/dashboards/ipfs-datasets/investigation', /Unified Investigation Dashboard/i],
  ['/dashboards/ipfs-datasets/investigation-mcp', /Unified Investigation Dashboard MCP/i],
  ['/dashboards/ipfs-datasets/news-analysis', /News Analysis Dashboard/i],
  ['/dashboards/ipfs-datasets/news-analysis-improved', /News Analysis Dashboard Improved/i],
  ['/dashboards/ipfs-datasets/admin-index', /Admin Dashboard Home/i],
  ['/dashboards/ipfs-datasets/admin-login', /Admin Dashboard Login/i],
  ['/dashboards/ipfs-datasets/admin-error', /Admin Dashboard Error/i],
  ['/dashboards/ipfs-datasets/admin-analytics', /Analytics Dashboard/i],
  ['/dashboards/ipfs-datasets/admin-rag-query', /RAG Query Dashboard/i],
  ['/dashboards/ipfs-datasets/admin-investigation', /Admin Investigation Dashboard/i],
  ['/dashboards/ipfs-datasets/admin-caselaw', /Caselaw Dashboard/i],
  ['/dashboards/ipfs-datasets/admin-caselaw-mcp', /Caselaw MCP Dashboard/i],
  ['/dashboards/ipfs-datasets/admin-finance-mcp', /Finance MCP Dashboard/i],
  ['/dashboards/ipfs-datasets/admin-finance-workflow', /Finance Workflow Dashboard/i],
  ['/dashboards/ipfs-datasets/admin-medicine-mcp', /Medicine MCP Dashboard/i],
  ['/dashboards/ipfs-datasets/admin-patent', /Patent Dashboard/i],
  ['/dashboards/ipfs-datasets/admin-discord', /Discord Dashboard/i],
  ['/dashboards/ipfs-datasets/admin-graphrag', /GraphRAG Dashboard/i],
  ['/dashboards/ipfs-datasets/admin-mcp', /Admin MCP Dashboard/i],
];

async function waitForWorkspaceReady(page) {
  await expect(page.locator('body')).toContainText(/Unified Complaint Workspace/i, { timeout: 30000 });

  for (let attempt = 0; attempt < 2; attempt += 1) {
    try {
      await expect(page.locator('#sdk-server-info')).toContainText(/complaint-workspace-mcp/i, { timeout: 20000 });
      await expect(page.locator('#workspace-status')).toContainText(/synchronized|workspace ready|opened workspace|returned from|draft generated|intake answers saved|reset to a clean state/i, { timeout: 20000 });
      await expect(page.locator('[data-tab-target="intake"]')).toBeVisible({ timeout: 10000 });
      await page.locator('[data-tab-target="intake"]').click();
      await expect(page.locator('#intake-party_name')).toBeVisible({ timeout: 10000 });
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

async function expectScreenshotBudget(locator, { label, maxRenderedHeight, maxScrollHeight = maxRenderedHeight }) {
  const metrics = await locator.evaluate((node) => {
    const rect = node.getBoundingClientRect();
    return {
      renderedHeight: Math.ceil(rect.height),
      scrollHeight: Math.ceil(node.scrollHeight),
    };
  });
  expect(metrics.renderedHeight, `${label} rendered height should stay within screenshot budget`).toBeLessThanOrEqual(maxRenderedHeight);
  expect(metrics.scrollHeight, `${label} scroll height should stay within screenshot budget`).toBeLessThanOrEqual(maxScrollHeight);
  return metrics;
}

test.describe('website surface navigation', () => {
  test.beforeEach(async ({ page }) => {
    await page.addInitScript(() => {
      window.alert = () => {};
    });
  });

  test('homepage presents a client-safe intake entry point and captures a screenshot', async ({ page }, testInfo) => {
    await page.goto('/');

    await expect(page.locator('h1').first()).toContainText(/Lex Publicus Complaint Generator/i);
    await expect(page.locator('body')).toContainText(/Build your complaint one step at a time/i);
    await expect(page.locator('body')).toContainText(/Your next safest step/i);
    await expect(page.locator('body')).toContainText(/Three Simple Steps/i);
    await expect(page.locator('body')).toContainText(/Choose Your Next Step/i);
    await expect(page.locator('#homepage-nav-workspace')).toBeVisible();
    await expect(page.locator('#homepage-nav-review')).toBeVisible();
    await expect(page.locator('#homepage-nav-builder')).toBeVisible();
    await expect(page.locator('#homepage-session-badge')).toContainText(/Connected|Offline/i);
    await expect(page.locator('#homepage-did')).toContainText(/did:key:|Unavailable/i);
    await expect(page.locator('#cg-app-shell')).toHaveCount(0);
    await expect(page.locator('[data-surface-nav="primary"]')).toContainText(/Secure Intake/i);
    await expect(page.locator('[data-surface-nav="primary"]')).toContainText(/Builder/i);
    await expect(page.getByRole('link', { name: 'Start Secure Intake', exact: true })).toHaveCount(1);
    await expect(page.locator('#homepage-nav-builder')).toHaveAttribute('aria-disabled', 'true');
    await expect(page.locator('#homepage-resume-builder')).toHaveAttribute('aria-disabled', 'true');

    const screenshotPath = testInfo.outputPath('homepage-overview.png');
    await page.locator('.hero').screenshot({ path: screenshotPath });
    await testInfo.attach('homepage-overview', {
      path: screenshotPath,
      contentType: 'image/png',
    });
  });

  test('homepage remains usable on a narrow mobile viewport', async ({ page }, testInfo) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto('/');

    await expect(page.locator('h1').first()).toContainText(/Lex Publicus Complaint Generator|Prepare your complaint in the order a real case should be built/i);
    await expect(page.locator('[data-surface-nav="primary"]')).toBeVisible();
      await expect(page.locator('[data-surface-nav="primary"]')).toContainText(/Secure Intake/i);
      await expect(page.locator('[data-surface-nav="primary"]')).toContainText(/Builder/i);
      await expect(page.locator('[data-surface-nav="primary"]')).toContainText(/Chat|Editor/i);
    await expect(page.locator('#resume-panel')).toBeVisible();
    await expect(page.locator('#homepage-session-status')).toContainText(/Connecting to the complaint workspace|Shared complaint session loaded/i);
    await expect(page.locator('#homepage-next-step')).toBeVisible();
    await expect(page.locator('#homepage-nav-workspace')).toBeVisible();
    await expect(page.locator('#homepage-nav-review')).toBeVisible();

    const screenshotPath = testInfo.outputPath('homepage-mobile-overview.png');
    await page.locator('#resume-panel').screenshot({ path: screenshotPath });
    await testInfo.attach('homepage-mobile-overview', {
      path: screenshotPath,
      contentType: 'image/png',
    });
  });

  test('all routed complaint surfaces load and expose expected navigation affordances', async ({ page }) => {
    const routes = [
      ['/', /Lex Publicus Complaint Generator/i],
      ['/home', /Lex Publicus Chat App/i],
      ['/chat', /Lex Publicus Chat App/i],
      ['/profile', /Profile Data/i],
        ['/results', /Complaint Output Snapshot|Results/i],
      ['/workspace', /Unified Complaint Workspace/i],
      ['/wysiwyg', /Complaint Editor Workshop/i],
      ['/mlwysiwyg', /Complaint Editor Workshop/i],
      ['/MLWYSIWYG', /Complaint Editor Workshop/i],
      ['/document', /Formal Complaint Builder/i],
      ['/claim-support-review', /Operator Review Surface/i],
      ['/document/optimization-trace', /Optimization Trace Viewer/i],
      ['/ipfs-datasets/sdk-playground', /SDK Playground Preview|SDK Playground/i],
      ['/mcp', /IPFS Datasets MCP Dashboard/i],
      ['/dashboards', /Unified Dashboard Hub/i],
      ...dashboardRoutes,
    ];

    for (const [path, heading] of routes) {
      await page.goto(path);
      await expect(page.locator('body')).toContainText(heading);
    }

    await page.goto('/');
    await expect(page.locator('h1').first()).toContainText(/Lex Publicus Complaint Generator/i);
    await expect(page.locator('#homepage-session-badge')).toContainText(/Connected|Offline/i);
    await expect(page.locator('#homepage-did')).toContainText(/did:key:/i);
    await expect(page.locator('#homepage-nav-workspace')).toBeVisible();
    await expect(page.locator('#homepage-nav-review')).toBeVisible();
    await expect(page.locator('#homepage-nav-builder')).toBeVisible();
    await expect(page.locator('body')).toContainText(/Three Simple Steps/i);
    await expect(page.locator('body')).toContainText(/Choose Your Next Step/i);
    await expect(page.locator('#homepage-next-step')).toBeVisible();
    await expect(page.locator('#cg-app-shell')).toHaveCount(0);

    await page.goto('/chat');
    await expect(page.locator('#chat-nav-builder')).toBeVisible();
    await expect(page.locator('#chat-nav-review')).toBeVisible();
    await expect(page.locator('#chat-nav-workspace')).toBeVisible();
    await expect(page.locator('[data-surface-nav="primary"]')).not.toContainText(/Trace|SDK|Dashboards/i);
    await expect(page.locator('#chat-advanced-nav')).toContainText(/Advanced tools/i);

    await page.goto('/results');
    await expect(page.locator('#results-nav-builder')).toBeVisible();
    await expect(page.locator('#results-nav-review')).toBeVisible();

    await page.goto('/document');
    await expect(page.locator('#builder-nav-review')).toBeVisible();
    await expect(page.locator('#builder-nav-workspace')).toBeVisible();
    await expect(page.locator('[data-surface-nav="primary"]')).not.toContainText(/Profile|Trace|SDK|Dashboards/i);
    await expect(page.locator('#builder-advanced-nav')).toContainText(/Advanced tools/i);
    await expect(page.locator('#builder-nav-trace')).toHaveAttribute('href', /\/document\/optimization-trace/);

    await page.goto('/claim-support-review');
    await expect(page.locator('#review-nav-builder')).toBeVisible();
    await expect(page.locator('#review-nav-workspace')).toBeVisible();
    await expect(page.locator('[data-surface-nav="primary"]')).not.toContainText(/Profile|Trace|SDK|Dashboards/i);
    await expect(page.locator('#review-advanced-nav')).toContainText(/Advanced tools/i);
    await expect(page.locator('#review-nav-trace')).toHaveAttribute('href', /\/document\/optimization-trace/);
  });

  test('client and operator personas gate advanced controls consistently', async ({ page }) => {
    await page.addInitScript(() => {
      window.localStorage.setItem('complaintGenerator.did', 'did:key:nav-persona-gates');
      window.localStorage.removeItem('complaintGenerator.shellMode');
    });

    await page.goto('/chat?shell_mode=client');
    await expect(page.locator('#cg-app-shell')).toBeVisible({ timeout: 10000 });
    await expect(page.locator('#cg-app-shell')).toContainText(/Client mode/i);
    await expect(page.locator('#cg-app-shell')).toContainText(/Technical tools hidden in client mode/i);
    await expect(page.locator('#cg-app-shell-advanced-nav')).toHaveCount(0);

    await page.goto('/chat?shell_mode=operator');
    await expect(page.locator('#cg-app-shell')).toBeVisible({ timeout: 10000 });
    await expect(page.locator('#cg-app-shell')).toContainText(/Operator mode/i);
    await expect(page.locator('#cg-app-shell-advanced-nav')).toBeVisible();
    await expect(page.locator('#cg-app-shell')).toContainText(/MCP tools/i);

    await page.goto('/workspace?shell_mode=client');
    await waitForWorkspaceReady(page);
    await expect(page.locator('body')).toHaveAttribute('data-workspace-shell-mode', 'client');
    await page.locator('[data-tab-target="docket"]').click();
    await expect(page.locator('#docket-advanced-operations')).toBeHidden();
    await page.getByRole('button', { name: 'CLI + MCP', exact: true }).click();
    await expect(page.locator('#integrations-technical-reference')).toBeHidden();
    await expect(page.locator('#integrations-operator-workbench-card')).toBeHidden();
    await expect(page.locator('#integrations-operator-panels')).toBeHidden();

    await page.goto('/workspace?shell_mode=operator');
    await waitForWorkspaceReady(page);
    await expect(page.locator('body')).toHaveAttribute('data-workspace-shell-mode', 'operator');
    await page.locator('[data-tab-target="docket"]').click();
    await expect(page.locator('#docket-advanced-operations')).toBeVisible();
    await page.getByRole('button', { name: 'CLI + MCP', exact: true }).click();
    await expect(page.locator('#integrations-technical-reference')).toBeVisible();
    await expect(page.locator('#integrations-operator-workbench-card')).toBeVisible();
    await expect(page.locator('#integrations-operator-panels')).toBeVisible();
  });

  test('profile and results surfaces explain stored complaint state clearly', async ({ page }, testInfo) => {
    await page.goto('/profile');
    await expect(page).toHaveTitle(/Profile Data/i);
    await expect(page.locator('h1').first()).toContainText(/Profile data without the clutter/i);
    await expect(page.locator('body')).toContainText(/A readable snapshot of the complaint account, stored facts, and recent guided intake history/i);
    await expect(page.locator('body')).toContainText(/Connected workflow/i);
    await expect(page.locator('#profile_data')).toBeVisible();
    await expect(page.locator('#chat_history')).toBeVisible();
    await expect(page.locator('#profile_data')).not.toContainText(/demo-password|playwright-token/i);
    await expect(page.locator('#profile_data')).toContainText(/\[redacted\]/i);
    await expect(page.locator('[data-surface-nav="primary"]')).toContainText(/Profile/i);
    await expect(page.locator('[data-surface-nav="primary"]')).toContainText(/Results/i);
    await expect(page.locator('#profile-open-chat')).toHaveAttribute('href', '/chat');
    await expect(page.locator('#profile-open-trace')).toHaveAttribute('href', '/document/optimization-trace');

    const profileScreenshotPath = testInfo.outputPath('profile-overview.png');
    await page.locator('.page-shell').screenshot({ path: profileScreenshotPath });
    await testInfo.attach('profile-overview', {
      path: profileScreenshotPath,
      contentType: 'image/png',
    });

    await page.goto('/results');
    await expect(page).toHaveTitle(/Complaint Results/i);
    await expect(page.locator('h1').first()).toContainText(/Results without the raw-demo feel/i);
    await expect(page.locator('body')).toContainText(/stored complaint data/i);
    await expect(page.locator('body')).toContainText(/Stored complaint results/i);
    await expect(page.locator('#profile_data')).toBeVisible();
    await expect(page.locator('#profile_data')).not.toContainText(/demo-password|playwright-token/i);
    await expect(page.locator('#profile_data')).toContainText(/\[redacted\]/i);
    await expect(page.locator('[data-surface-nav="primary"]')).toContainText(/Review/i);
    await expect(page.locator('[data-surface-nav="primary"]')).toContainText(/Builder/i);
    await expect(page.locator('#results-open-chat')).toHaveAttribute('href', '/chat');
    await expect(page.locator('#results-open-trace')).toHaveAttribute('href', '/document/optimization-trace');

    const resultsScreenshotPath = testInfo.outputPath('results-overview.png');
    await page.locator('.page-shell').screenshot({ path: resultsScreenshotPath });
    await testInfo.attach('results-overview', {
      path: resultsScreenshotPath,
      contentType: 'image/png',
    });
  });

  test('chat surface preserves workspace handoff context and captures a screenshot', async ({ page }, testInfo) => {
    const handoffUrl = '/chat?source=workspace'
      + '&user_id=did:key:handoff-demo'
      + '&case_synopsis=Jordan%20Example%20alleges%20retaliation%20after%20reporting%20discrimination%20to%20HR.'
      + '&prefill_message=Mediator%2C%20help%20turn%20this%20into%20testimony-ready%20narrative%20for%20the%20complaint%20record.'
      + '&return_to=%2Fworkspace%3Ftarget_tab%3Dreview';

    await page.goto(handoffUrl);

    await expect(page).toHaveTitle(/Lex Publicus Chat App/i);
    await expect(page.locator('.hero h1')).toContainText(/Tell the story before the pleading/i);
    await expect(page.locator('body')).toContainText(/What to focus on in the interview|Complaint narrative chat/i);
    await expect(page.locator('#chat-context-card')).toBeVisible();
    await expect(page.locator('#chat-context-summary')).toContainText(/did:key:handoff-demo/i);
    await expect(page.locator('#chat-context-summary')).toContainText(/Jordan Example alleges retaliation/i);
    await expect(page.locator('#chat-context-prefill')).toContainText(/Prepared question/i);
    await expect(page.locator('#chat-context-return-link')).toHaveAttribute('href', /\/workspace\?target_tab=review/);
    await expect(page.locator('#chat-form input')).toHaveValue(/Mediator, help turn this into testimony-ready narrative/i);
    const chatLayoutOrder = await page.evaluate(() => {
      const form = document.querySelector('#chat-form');
      const guidance = document.querySelector('.hero');
      return {
        formTop: form ? form.getBoundingClientRect().top : 0,
        guidanceTop: guidance ? guidance.getBoundingClientRect().top : 0,
      };
    });
    expect(chatLayoutOrder.formTop).toBeLessThan(chatLayoutOrder.guidanceTop);
    await expect(page.locator('[aria-label="Additional chat destinations"]')).toBeVisible();
    await expect(page.locator('#chat-meta-workspace')).toHaveAttribute('href', /user_id=did%3Akey%3Ahandoff-demo/);
    await expect(page.locator('#chat-nav-profile')).toHaveAttribute('href', /user_id=did%3Akey%3Ahandoff-demo/);
    await expect(page.locator('#chat-nav-results')).toHaveAttribute('href', /user_id=did%3Akey%3Ahandoff-demo/);
    await expect(page.locator('#chat-hero-workspace')).toHaveAttribute('href', /user_id=did%3Akey%3Ahandoff-demo/);
    await expect(page.locator('#chat-hero-review')).toHaveAttribute('href', /user_id=did%3Akey%3Ahandoff-demo/);
    await expect(page.locator('#chat-open-workspace')).toHaveAttribute('href', /user_id=did%3Akey%3Ahandoff-demo/);
    await expect(page.locator('#chat-open-profile')).toHaveAttribute('href', /user_id=did%3Akey%3Ahandoff-demo/);
    await expect(page.locator('#chat-open-results')).toHaveAttribute('href', /user_id=did%3Akey%3Ahandoff-demo/);
    await expect(page.locator('#chat-open-review')).toHaveAttribute('href', /user_id=did%3Akey%3Ahandoff-demo/);
    await expect(page.locator('#chat-open-builder')).toHaveAttribute('href', /case_synopsis=Jordan\+Example/);
    await expect(page.locator('#chat-open-review')).toBeVisible();
    await expect(page.locator('#chat-open-builder')).toBeVisible();

    const screenshotPath = testInfo.outputPath('chat-handoff-overview.png');
    await page.locator('.page-shell').screenshot({ path: screenshotPath });
    await testInfo.attach('chat-handoff-overview', {
      path: screenshotPath,
      contentType: 'image/png',
    });
  });

  test('document-scoped chat puts the selected filing context first', async ({ page }) => {
    const context = {
      scope: 'selected_document',
      docket_item_id: 'doc-termination-notice',
      title: 'Termination notice filed March 10',
      document_type: 'order',
      source: 'Docket import',
      labels: ['Adverse action', 'Deadline'],
      router_mode: 'llm_router / multimodal_router',
    };
    const params = new URLSearchParams({
      source: 'workspace-docket',
      user_id: 'did:key:docket-chat-demo',
      prefill_message: 'What deadline or response does this order create?',
      chat_context: JSON.stringify(context),
      return_to: '/workspace?target_tab=docket',
    });

    await page.goto(`/chat?${params.toString()}`);

    await expect(page.locator('#cg-app-shell')).toHaveCount(0);
    await expect(page.locator('[data-surface-nav="primary"]')).toBeHidden();
    await expect(page.locator('#chat-selected-filing-hero')).toBeVisible();
    await expect(page.locator('#chat-selected-filing-badge')).toContainText(/Selected filing attached/i);
    await expect(page.locator('#chat-selected-filing-title')).toContainText(/Termination notice filed March 10/i);
    await expect(page.locator('#chat-selected-filing-source')).toContainText(/Docket import/i);
    await expect(page.locator('#chat-selected-filing-type')).toContainText(/order/i);
    await expect(page.locator('#chat-selected-filing-scope')).toContainText(/llm_router \/ multimodal_router/i);
    await expect(page.locator('#chat-selected-filing-question')).toContainText(/What deadline or response does this order create/i);
    await expect(page.locator('#chat-selected-filing-persistence')).toContainText(/nothing is saved as a label, annotation, deadline, or answer/i);
    await expect(page.locator('#chat-selected-filing-return-link')).toHaveAttribute('href', /\/workspace\?target_tab=docket/);
    await expect(page.locator('.hero')).toBeHidden();
    await expect(page.locator('#chat-active-context-title')).toContainText(/Termination notice filed March 10/i);
    await expect(page.locator('#chat-grounding-preview')).toBeVisible();
    await expect(page.locator('#chat-grounding-document')).toContainText(/Termination notice filed March 10/i);
    await expect(page.locator('#chat-form input')).toHaveValue(/What deadline or response does this order create/i);
  });

  test('chat next-step actions preserve complaint context across workflow handoffs', async ({ page }) => {
    const handoffUrl = '/chat?source=workspace'
      + '&user_id=did:key:chat-step-demo'
      + '&case_synopsis=Jordan%20Example%20needs%20causation%20support%20before%20drafting.'
      + '&prefill_message=Help%20organize%20the%20timeline%20and%20missing%20proof.'
      + '&return_to=%2Fworkspace%3Ftarget_tab%3Dreview';

    await page.goto(handoffUrl);
    await expect(page.locator('[aria-label="Additional chat destinations"]')).toBeVisible();
    await page.locator('#chat-open-profile').click();
    await expect(page).toHaveURL(/\/profile\?/);
    await expect(page.locator('#profile-context-card')).toBeVisible();
    await expect(page.locator('#profile-context-summary')).toContainText(/did:key:chat-step-demo/);
    await expect(page.locator('#profile-nav-results')).toHaveAttribute('href', /user_id=did%3Akey%3Achat-step-demo/);
    await expect(page.locator('#profile-nav-trace')).toHaveAttribute('href', /user_id=did%3Akey%3Achat-step-demo/);
    await expect(page.locator('#profile-open-results')).toHaveAttribute('href', /user_id=did%3Akey%3Achat-step-demo/);
    await expect(page.locator('#profile-open-trace')).toHaveAttribute('href', /user_id=did%3Akey%3Achat-step-demo/);
    await page.locator('#profile-nav-results').click();
    await expect(page).toHaveURL(/\/results\?/);
    await expect(page.locator('#results-context-card')).toBeVisible();
    await expect(page.locator('#results-context-summary')).toContainText(/did:key:chat-step-demo/);
    await expect(page.locator('#results-nav-review')).toHaveAttribute('href', /user_id=did%3Akey%3Achat-step-demo/);
    await expect(page.locator('#results-nav-trace')).toHaveAttribute('href', /user_id=did%3Akey%3Achat-step-demo/);
    await expect(page.locator('#results-open-workspace')).toHaveAttribute('href', /user_id=did%3Akey%3Achat-step-demo/);
    await expect(page.locator('#results-open-trace')).toHaveAttribute('href', /user_id=did%3Akey%3Achat-step-demo/);

    await page.goto(handoffUrl);
    await page.locator('#chat-open-results').click();
    await expect(page).toHaveURL(/\/results\?/);
    await expect(page.locator('#results-context-card')).toBeVisible();
    await expect(page.locator('#results-context-summary')).toContainText(/did:key:chat-step-demo/);

    await page.goto(handoffUrl);
    await page.locator('#chat-open-profile').click();
    await page.locator('#profile-open-trace').click();
    await expect(page).toHaveURL(/\/document\/optimization-trace\?/);
    await expect(page).toHaveURL(/user_id=did%3Akey%3Achat-step-demo/);

    await page.goto(handoffUrl);
    await page.locator('#chat-open-results').click();
    await page.locator('#results-open-trace').click();
    await expect(page).toHaveURL(/\/document\/optimization-trace\?/);
    await expect(page).toHaveURL(/user_id=did%3Akey%3Achat-step-demo/);

    await page.goto(handoffUrl);
    await page.locator('#chat-hero-review').click();
    await expect(page).toHaveURL(/\/claim-support-review\?/);
    await expect(page).toHaveURL(/user_id=did%3Akey%3Achat-step-demo/);

    await page.goto(handoffUrl);
    await page.locator('#chat-open-review').click();
    await expect(page).toHaveURL(/\/claim-support-review\?/);
    await expect(page).toHaveURL(/user_id=did%3Akey%3Achat-step-demo/);

    await page.goto(handoffUrl);
    await page.locator('#chat-open-builder').click();
    await expect(page).toHaveURL(/\/document\?/);
    await expect(page).toHaveURL(/user_id=did%3Akey%3Achat-step-demo/);
    await expect(page).toHaveURL(/case_synopsis=Jordan\+Example/);
  });

  test('workspace handoff cards keep the complaint context visible and capture a screenshot', async ({ page }, testInfo) => {
    test.slow();
    await page.addInitScript(() => {
      window.localStorage.setItem('complaintGenerator.did', 'did:key:workspace-handoff-demo');
    });

    await page.goto('/workspace');
    await waitForWorkspaceReady(page);

    await revealAllIntakeFields(page);
    await page.locator('#intake-party_name').fill('Jordan Example');
    await page.locator('#intake-opposing_party').fill('Acme Corporation');
    await page.locator('#intake-protected_activity').fill('Reported discrimination to HR');
    await page.locator('#intake-adverse_action').fill('Termination two days later');
    await page.locator('#intake-timeline').fill('Complaint on March 8, termination on March 10');
    await page.locator('#intake-harm').fill('Lost wages and emotional distress');
    await page.locator('#intake-court_header').fill('FOR THE NORTHERN DISTRICT OF CALIFORNIA');
    await page.locator('#save-intake-button').click();
    await expect(page.locator('#workspace-status')).toContainText(/Intake answers saved/i);

    await page.locator('#case-synopsis').fill(
      'Jordan Example alleges retaliation after reporting discrimination to HR, with the clearest current support on timeline and the main remaining need being corroboration.',
    );
    await page.locator('#save-synopsis-button').click();
    await expect(page.locator('#workspace-status')).toContainText(/Shared case synopsis saved/i);

    await expect(page.locator('#handoff-chat-summary')).toContainText(/Open Chat/i);
    await expect(page.locator('#handoff-review-summary')).toContainText(/Open the review dashboard/i);
    await expect(page.locator('#handoff-builder-summary')).toContainText(/Open the formal builder|held back until the complaint record can support a real filing draft/i);
    await expect(page.locator('#handoff-chat-button')).toHaveAttribute('href', /\/chat\?/);
    await expect(page.locator('#handoff-chat-button')).toHaveAttribute('href', /source=workspace/);
    await expect(page.locator('#handoff-chat-button')).toHaveAttribute('href', /user_id=did%3Akey%3Aworkspace-handoff-demo/);
    await expect(page.locator('#handoff-chat-button')).toHaveAttribute('href', /prefill_message=/);
    await expect(page.locator('#handoff-chat-button')).toHaveAttribute('href', /return_to=%2Fworkspace/);
    await expect(page.locator('#workspace-nav-chat')).toHaveAttribute('href', /user_id=did%3Akey%3Aworkspace-handoff-demo/);
    await expect(page.locator('#workspace-nav-profile')).toHaveAttribute('href', /user_id=did%3Akey%3Aworkspace-handoff-demo/);
    await expect(page.locator('#workspace-nav-results')).toHaveAttribute('href', /user_id=did%3Akey%3Aworkspace-handoff-demo/);
    await expect(page.locator('#handoff-review-button')).toHaveAttribute('href', /\/claim-support-review\?/);
    await expect(page.locator('#handoff-review-button')).toHaveAttribute('href', /workspace_user_id=did%3Akey%3Aworkspace-handoff-demo/);
    await expect(page.locator('#workspace-nav-review')).toHaveAttribute('href', /workspace_user_id=did%3Akey%3Aworkspace-handoff-demo/);
    await expect(page.locator('#handoff-builder-button')).toHaveAttribute('href', /\/document\?/);
    await expect(page.locator('#handoff-builder-button')).toHaveAttribute('href', /user_id=did%3Akey%3Aworkspace-handoff-demo/);
    await expect(page.locator('#workspace-nav-builder')).toHaveAttribute('href', /user_id=did%3Akey%3Aworkspace-handoff-demo/);
    await expect(page.locator('#workspace-nav-trace')).toHaveAttribute('href', /user_id=did%3Akey%3Aworkspace-handoff-demo/);

    const screenshotPath = testInfo.outputPath('workspace-handoffs-overview.png');
    await page.locator('[aria-label="Connected surface handoffs"]').screenshot({ path: screenshotPath });
    await testInfo.attach('workspace-handoffs-overview', {
      path: screenshotPath,
      contentType: 'image/png',
    });
  });

  test('document and dashboard remain mutually navigable as one website', async ({ page }) => {
    await page.goto('/document?user_id=did:key:builder-nav-demo&claim_type=retaliation');
    await expect(page.locator('#builder-nav-chat')).toHaveAttribute('href', /user_id=did%3Akey%3Abuilder-nav-demo/);
    await expect(page.locator('#builder-nav-profile')).toHaveAttribute('href', /user_id=did%3Akey%3Abuilder-nav-demo/);
    await expect(page.locator('#builder-nav-results')).toHaveAttribute('href', /user_id=did%3Akey%3Abuilder-nav-demo/);
    await expect(page.locator('#builder-nav-workspace')).toHaveAttribute('href', /user_id=did%3Akey%3Abuilder-nav-demo/);
    await expect(page.locator('#builder-nav-review')).toHaveAttribute('href', /user_id=did%3Akey%3Abuilder-nav-demo/);
    await expect(page.locator('#builder-nav-builder')).toHaveAttribute('href', /user_id=did%3Akey%3Abuilder-nav-demo/);
    await expect(page.locator('#builder-nav-trace')).toHaveAttribute('href', /user_id=did%3Akey%3Abuilder-nav-demo/);
    await page.locator('#builder-nav-review').click();
    await expect(page).toHaveURL(/\/claim-support-review/);
    await expect(page.locator('body')).toContainText(/Operator Review Surface/i);

    await page.goto('/document?user_id=did:key:builder-nav-demo&claim_type=retaliation');
    await page.locator('#builder-advanced-nav > summary').click();
    await page.locator('#builder-nav-trace').click();
    await expect(page).toHaveURL(/\/document\/optimization-trace\?/);
    await expect(page).toHaveURL(/user_id=did%3Akey%3Abuilder-nav-demo/);

    await page.goto('/document?user_id=did:key:builder-nav-demo&claim_type=retaliation');
    await page.locator('#builder-nav-review').click();
    await expect(page).toHaveURL(/\/claim-support-review\?/);
    await expect(page).toHaveURL(/user_id=did%3Akey%3Abuilder-nav-demo/);

    await page.goto('/document?user_id=did:key:builder-nav-demo&claim_type=retaliation');
    await page.locator('#builder-nav-builder').click();
    await expect(page).toHaveURL(/\/document/);
    await expect(page.locator('body')).toContainText(/Formal Complaint Builder/i);
  });

  test('editor and sdk dashboards are part of the same unified navigation experience', async ({ page }) => {
    await page.goto('/mlwysiwyg?user_id=did:key:editor-nav-demo&case_synopsis=Jordan%20Example%20needs%20corroboration.&claim_type=retaliation');
    await expect(page.locator('[data-surface-nav="primary"]')).toBeVisible();
    await expect(page.locator('#draft-preview')).toContainText(/Retaliation Complaint Draft/i);
    await expect(page.locator('#editor-nav-chat')).toHaveAttribute('href', /user_id=did%3Akey%3Aeditor-nav-demo/);
    await expect(page.locator('#editor-nav-profile')).toHaveAttribute('href', /user_id=did%3Akey%3Aeditor-nav-demo/);
    await expect(page.locator('#editor-nav-results')).toHaveAttribute('href', /user_id=did%3Akey%3Aeditor-nav-demo/);
    await expect(page.locator('#editor-nav-workspace')).toHaveAttribute('href', /user_id=did%3Akey%3Aeditor-nav-demo/);
    await expect(page.locator('#editor-nav-review')).toHaveAttribute('href', /user_id=did%3Akey%3Aeditor-nav-demo/);
    await expect(page.locator('#editor-nav-builder')).toHaveAttribute('href', /user_id=did%3Akey%3Aeditor-nav-demo/);
    await expect(page.locator('#editor-nav-trace')).toHaveAttribute('href', /user_id=did%3Akey%3Aeditor-nav-demo/);
    await expect(page.locator('#editor-open-workspace')).toHaveAttribute('href', /user_id=did%3Akey%3Aeditor-nav-demo/);
    await expect(page.locator('#editor-open-workspace')).toHaveAttribute('href', /target_tab=draft/);
    await expect(page.locator('#editor-open-tools')).toHaveAttribute('href', /user_id=did%3Akey%3Aeditor-nav-demo/);
    await expect(page.locator('#editor-open-tools')).toHaveAttribute('href', /target_tab=integrations/);
    await expect(page.locator('#editor-open-review')).toHaveAttribute('href', /user_id=did%3Akey%3Aeditor-nav-demo/);
    await expect(page.locator('#editor-open-review')).toHaveAttribute('href', /claim_type=retaliation/);
    await expect(page.locator('#editor-open-builder')).toHaveAttribute('href', /user_id=did%3Akey%3Aeditor-nav-demo/);
    await expect(page.locator('#editor-open-builder')).toHaveAttribute('href', /claim_type=retaliation/);
    await expect(page.locator('#editor-open-trace')).toHaveAttribute('href', /user_id=did%3Akey%3Aeditor-nav-demo/);
    await expect(page.locator('#editor-open-trace')).toHaveAttribute('href', /claim_type=retaliation/);
    await page.locator('#editor-nav-workspace').click();

    await expect(page).toHaveURL(/\/workspace/);
    await expect(page.locator('body')).toContainText(/Unified Complaint Workspace/i);
    await page.locator('a[href="/ipfs-datasets/sdk-playground"]').first().click();

    await expect(page).toHaveURL(/\/ipfs-datasets\/sdk-playground/);
    await expect(page.locator('[data-surface-nav="primary"]')).toBeVisible();
    await expect(page.locator('body')).toContainText(/SDK Playground/i);

    await page.locator('a[href="/document"]').first().click();
    await expect(page).toHaveURL(/\/document/);
    await expect(page.locator('body')).toContainText(/Formal Complaint Builder/i);
  });

  test('profile, results, and editor expose direct next-step actions instead of nav-only handoffs', async ({ page }) => {
    await page.goto('/profile');
    await expect(page.locator('[aria-label="Profile next steps"]')).toBeVisible();
    await expect(page.locator('#profile-open-chat')).toBeVisible();
    await expect(page.locator('#profile-open-results')).toBeVisible();
    await expect(page.locator('#profile-open-review')).toBeVisible();
    await expect(page.locator('#profile-open-builder')).toBeVisible();
    await expect(page.locator('#profile-open-workspace')).toBeVisible();
    await expect(page.locator('#profile-open-trace')).toBeVisible();
    await page.locator('#profile-open-results').click();
    await expect(page).toHaveURL(/\/results/);

    await expect(page.locator('[aria-label="Results next steps"]')).toBeVisible();
    await expect(page.locator('#results-open-chat')).toBeVisible();
    await expect(page.locator('#results-open-workspace')).toBeVisible();
    await expect(page.locator('#results-open-review')).toBeVisible();
    await expect(page.locator('#results-open-builder')).toBeVisible();
    await expect(page.locator('#results-open-editor')).toBeVisible();
    await expect(page.locator('#results-open-trace')).toBeVisible();
    await page.locator('#results-open-editor').click();
    await expect(page).toHaveURL(/\/mlwysiwyg/);

    await expect(page.locator('[aria-label="Editor next steps"]')).toBeVisible();
    await expect(page.locator('body')).toContainText(/Return to the workspace for packet export, release-gate review, actor\/critic analysis/i);
    await expect(page.locator('#editor-open-workspace')).toBeVisible();
    await expect(page.locator('#editor-open-tools')).toBeVisible();
    await expect(page.locator('#editor-open-review')).toBeVisible();
    await expect(page.locator('#editor-open-builder')).toBeVisible();
    await expect(page.locator('#editor-open-trace')).toBeVisible();
    await page.locator('#editor-open-trace').click();
    await expect(page).toHaveURL(/\/document\/optimization-trace/);
  });

  test('review surface exposes explicit next-step workflow actions', async ({ page }) => {
    await page.goto('/claim-support-review?claim_type=retaliation&user_id=did:key:review-nav-demo&workspace_user_id=did:key:review-nav-demo');
    await expect(page.locator('[aria-label="Review next steps"]')).toBeVisible();
    await expect(page.locator('#review-open-workspace-link')).toBeVisible();
    await expect(page.locator('#review-open-chat-link')).toBeVisible();
    await expect(page.locator('#review-open-builder-link')).toBeVisible();
    await expect(page.locator('#review-open-trace-link')).toBeVisible();
    await expect(page.locator('#review-nav-chat')).toHaveAttribute('href', /user_id=did%3Akey%3Areview-nav-demo/);
    await expect(page.locator('#review-nav-profile')).toHaveAttribute('href', /user_id=did%3Akey%3Areview-nav-demo/);
    await expect(page.locator('#review-nav-results')).toHaveAttribute('href', /user_id=did%3Akey%3Areview-nav-demo/);
    await expect(page.locator('#review-nav-workspace')).toHaveAttribute('href', /user_id=did%3Akey%3Areview-nav-demo/);
    await expect(page.locator('#review-nav-review')).toHaveAttribute('href', /user_id=did%3Akey%3Areview-nav-demo/);
    await expect(page.locator('#review-nav-builder')).toHaveAttribute('href', /user_id=did%3Akey%3Areview-nav-demo/);
    await expect(page.locator('#review-nav-trace')).toHaveAttribute('href', /user_id=did%3Akey%3Areview-nav-demo/);
    await page.locator('#review-advanced-nav > summary').click();
    await expect(page.locator('#review-nav-profile')).toBeVisible();
    await page.locator('#review-nav-profile').click();
    await expect(page).toHaveURL(/\/profile\?/);
    await expect(page).toHaveURL(/user_id=did%3Akey%3Areview-nav-demo/);
    await page.goto('/claim-support-review?claim_type=retaliation&user_id=did:key:review-nav-demo&workspace_user_id=did:key:review-nav-demo');
    await page.locator('#review-open-workspace-link').click();
    await expect(page).toHaveURL(/\/workspace\?/);
    await expect(page).toHaveURL(/user_id=did%3Akey%3Areview-nav-demo/);
    await expect(page).toHaveURL(/target_tab=review/);
    await expect(page.locator('body')).toContainText(/Unified Complaint Workspace/i, { timeout: 30000 });
    await expect(page.locator('#sdk-server-info')).toContainText(/complaint-workspace-mcp/i, { timeout: 20000 });
    await expect(page.locator('#did-chip')).toContainText(/did:key:review-nav-demo/i);
    await expect(page.locator('[data-tab-target="review"]')).toHaveClass(/is-active/);
    await expect(page.locator('#workspace-status')).toContainText(/Returned from review to the workspace/i, { timeout: 20000 });
    await page.goto('/claim-support-review?claim_type=retaliation&user_id=did:key:review-nav-demo&workspace_user_id=did:key:review-nav-demo');
    await page.locator('#review-open-builder-link').click();
    await expect(page).toHaveURL(/\/document/);
  });

  test('review handoff back to workspace preserves exported packet context after reload', async ({ page }) => {
    const did = `did:key:review-return-${Date.now()}`;
    await page.addInitScript((value) => {
      window.localStorage.setItem('complaintGenerator.did', value);
    }, did);

    await page.goto('/workspace');
    await waitForWorkspaceReady(page);

    await revealAllIntakeFields(page);
    await page.locator('#intake-party_name').fill('Jane Doe');
    await page.locator('#intake-opposing_party').fill('Acme Corporation');
    await page.locator('#intake-protected_activity').fill('Reported discrimination to HR');
    await page.locator('#intake-adverse_action').fill('Termination two days later');
    await page.locator('#intake-timeline').fill('Complaint on March 8, termination on March 10');
    await page.locator('#intake-harm').fill('Lost wages and benefits');
    await page.locator('#intake-court_header').fill('FOR THE NORTHERN DISTRICT OF CALIFORNIA');
    await page.locator('#save-intake-button').click();
    await expect(page.locator('#workspace-status')).toContainText(/Intake answers saved/i);

    await page.getByRole('button', { name: 'Evidence', exact: true }).click();
    await page.locator('#evidence-kind').selectOption('document');
    await page.locator('#evidence-claim-element').selectOption('causation');
    await page.locator('#evidence-title').fill('Termination email');
    await page.locator('#evidence-source').fill('Inbox export');
    await page.locator('#evidence-content').fill('The termination followed the HR complaint within two days.');
    await page.locator('#save-evidence-button').click();
    await expect(page.locator('#workspace-status')).toContainText(/Evidence saved and support review refreshed/i);

    await page.getByRole('button', { name: 'Draft', exact: true }).click();
    await page.locator('#draft-title').fill('Jane Doe v. Acme Corporation Complaint');
    await page.locator('#requested-relief').fill('Back pay\nInjunctive relief');
    await page.locator('#generate-draft-button').click();
    await expect(page.locator('#workspace-status')).toContainText(/Complaint draft generated through the llm_router formal complaint path/i);
    await expect(page.locator('#draft-preview')).toContainText(/Jane Doe brings this retaliation complaint against Acme Corporation/i);

    await page.locator('#export-packet-button').click();
    await expect(page.locator('#workspace-status')).toContainText(/Complaint packet exported/i);
    await expect(page.locator('#packet-preview')).toContainText(/Title: Jane Doe v\. Acme Corporation Complaint/i);

    await page.goto(`/claim-support-review?claim_type=retaliation&user_id=${encodeURIComponent(did)}&workspace_user_id=${encodeURIComponent(did)}`);
    await expect(page.locator('#review-open-workspace-link')).toBeVisible();
    await page.locator('#review-open-workspace-link').click();
    await expect(page).toHaveURL(/\/workspace\?/);
    await expect(page).toHaveURL(new RegExp(`user_id=${encodeURIComponent(did).replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}`));
    await expect(page).toHaveURL(/target_tab=review/);
    await expect(page.locator('#workspace-status')).toContainText(/Returned from review to the workspace/i, { timeout: 20000 });
    await expect(page.locator('#did-chip')).toContainText(did);
    await expect(page.locator('[data-tab-target="review"]')).toHaveClass(/is-active/);

    await page.reload({ waitUntil: 'networkidle' });
    await expect(page.locator('#did-chip')).toContainText(did);
    await expect(page.locator('[data-tab-target="review"]')).toHaveClass(/is-active/);
    await page.getByRole('button', { name: 'Draft', exact: true }).click();
    await expect(page.locator('#packet-preview')).toContainText(/Title: Jane Doe v\. Acme Corporation Complaint/i);
    await expect(page.locator('#packet-preview')).toContainText(/Jane Doe brings this retaliation complaint against Acme Corporation/i);
    await expect(page.locator('#download-packet-tool-markdown-button')).toHaveAttribute('data-download-url', /output_format=markdown/);
  });

  test('dashboard hub and every mounted shell route are reachable in the JS stub surface', async ({ page }) => {
    await page.goto('/dashboards?user_id=did:key:nav-dashboard-user');
    await expect(page.locator('body')).toContainText(/Unified Dashboard Hub/i);
    await expect(page.getByRole('heading', { name: 'Start your complaint' })).toBeVisible();
    await expect(page.locator('#dashboard-entry-paths')).toContainText(/Step 2: Evidence/);
    await expect(page.locator('#dashboard-entry-paths')).toContainText(/Step 3: Review/);
    await expect(page.getByRole('heading', { name: 'Manage your profile' })).toBeVisible();
    await expect(page.locator('#dashboard-recommended-action-panel')).toBeVisible();
    await expect(page.locator('#dashboard-recommended-action-panel')).toContainText(/Step 1: Intake/i);
    await expect(page.locator('#dashboard-recommended-action-link')).toHaveText(/Start Intake Questions/i);
    await expect(page.locator('.progress-rule-strip')).toHaveCount(0);
    await expect(page.locator('.hero-stepper .stepper-step')).toHaveCount(0);
    await expect(page.locator('#dashboard-stage-progress')).toHaveCount(0);
    await expect(page.locator('#dashboard-entry-paths .stage-control')).toHaveCount(3);
    await expect(page.locator('#dashboard-utility-paths .entry-card')).toHaveCount(1);
    await expect(page.locator('#dashboard-entry-paths .stage-control').first()).toHaveAttribute('data-path-state', 'current');
    await expect(page.locator('#dashboard-entry-paths .stage-control').first()).toContainText(/Step 1: Intake/);
    await expect(page.locator('#dashboard-entry-paths .stage-control').first()).toContainText(/Start Intake Questions/);
    await expect(page.locator('#dashboard-entry-paths .stage-control').nth(1)).toHaveAttribute('data-path-state', 'locked');
    await expect(page.locator('#dashboard-entry-paths .stage-control').nth(1)).toContainText(/Step 2: Evidence/);
    await expect(page.locator('#dashboard-entry-paths .stage-control').nth(1)).toContainText(/To unlock/);
    await expect(page.locator('#dashboard-entry-paths .stage-control').nth(1)).toContainText(/Complete Step 1: Intake to unlock Evidence/);
    await expect(page.locator('#dashboard-entry-paths .stage-control').nth(1).locator('button.stage-control-action')).toBeDisabled();
    await expect(page.locator('#dashboard-entry-paths .stage-control').nth(1).locator('button.stage-control-action')).toHaveText(/Disabled: complete Step 1 first/);
    await expect(page.locator('#dashboard-entry-paths .stage-control').nth(2)).toHaveAttribute('data-path-state', 'locked');
    await expect(page.locator('#dashboard-entry-paths .stage-control').nth(2)).toContainText(/Step 3: Review/);
    await expect(page.locator('#dashboard-entry-paths .stage-control').nth(2)).toContainText(/To unlock/);
    await expect(page.locator('#dashboard-entry-paths .stage-control').nth(2)).toContainText(/Add a docket file to unlock Review/);
    await expect(page.locator('#dashboard-entry-paths .stage-control').nth(2).locator('button.stage-control-action')).toBeDisabled();
    await expect(page.locator('#dashboard-entry-paths .stage-control').nth(2).locator('button.stage-control-action')).toHaveText(/Disabled: add a docket file/);
    await expect(page.locator('#dashboard-utility-paths .entry-card').first()).toHaveAttribute('data-path-state', 'utility');
    await expect(page.locator('#dashboard-utility-paths .entry-card').first()).toContainText(/Optional/);
    await expect(page.locator('.entry-card .primary-action')).toHaveCount(0);
    await expect(page.locator('#dashboard-entry-paths .jump-link')).toHaveCount(0);
    await expect(page.locator('#dashboard-entry-paths summary')).toHaveCount(0);
    await expect(page.locator('#dashboard-subsection-index')).toContainText(/Saved complaint/i);
    await expect(page.locator('#dashboard-subsection-index')).toContainText(/Ask document question/i);
    await expect(page.getByText('4 tool groups', { exact: true })).toBeVisible();
    await expect(page.getByText('5 admin consoles', { exact: true })).toBeVisible();
    await expect(page.locator('#dashboard-recommended-action-link')).toHaveAttribute('href', /user_id=did%3Akey%3Anav-dashboard-user/);
    await expect(page.locator('body')).not.toContainText(/Admin Dashboard Error|IPFS Datasets MCP Dashboard Clean|IPFS Datasets MCP Dashboard Final/i);
    await expect(page.locator('body')).not.toContainText(/31 MCP tools|did:key:nav-dashboard-user/i);
    await expect(page.locator('#dashboard-advanced-tools > summary')).toContainText(/Advanced Operations/);

    for (const [route, heading] of dashboardRoutes) {
      await page.goto(route);
      await expect(page).toHaveURL(new RegExp(route.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')));
      await expect(page.locator('body')).toContainText(heading);
      await expect(page.locator('iframe')).toBeVisible();
    }
  });

  test('every mounted raw dashboard route is reachable in the JS stub surface', async ({ page }) => {
    for (const [route, heading] of dashboardRoutes) {
      const rawRoute = route.replace('/dashboards/ipfs-datasets/', '/dashboards/raw/ipfs-datasets/');
      const response = await page.goto(rawRoute);

      expect(response).not.toBeNull();
      expect(response.ok()).toBeTruthy();
      expect((await page.content()).length).toBeGreaterThan(200);
      await expect(page.locator('body')).not.toBeEmpty();
      await expect(page).toHaveTitle(/Dashboard|Admin|Investigation|News|Software|Analytics|GraphRAG|Patent|Discord|Finance|Medicine|Caselaw|RAG/i);
      await expect(page.locator('body')).toContainText(/Dashboard|Admin|Investigation|News|Software|Analytics|GraphRAG|Patent|Discord|Finance|Medicine|Caselaw|RAG/i);
    }
  });

  test('workspace page uses the browser MCP SDK to drive intake, evidence, draft, and tool discovery', async ({ page }) => {
    test.slow();
    await page.addInitScript(() => {
      window.localStorage.setItem('complaintGenerator.did', 'did:key:nav-workspace-flow');
    });
    await page.goto('/workspace');
    await waitForWorkspaceReady(page);
    await expect(page.locator('[data-tab-target="draft"]')).toBeVisible({ timeout: 30000 });
    await page.locator('[data-tab-target="draft"]').click();
    await expect(page.locator('#draft-title')).toBeVisible({ timeout: 10000 });
    await expect(page.locator('#reset-session-button')).toBeVisible({ timeout: 10000 });
    await page.locator('#reset-session-button').click();
    await expect(page.locator('#workspace-status')).toContainText(/resetting the workspace|reset to a clean state/i);
    await page.locator('[data-tab-target="intake"]').click();
    await expect(page.locator('#sdk-server-info')).toContainText(/complaint-workspace-mcp/i);
    await expect(page.locator('#tool-list')).toContainText(/complaint.generate_complaint/i);
    await expect(page.locator('#tool-list')).toContainText(/complaint.build_mediator_prompt/i);
    await expect(page.locator('#tool-list')).toContainText(/complaint.export_complaint_packet/i);
    await expect(page.locator('#tool-list')).toContainText(/complaint.export_complaint_markdown/i);
    await expect(page.locator('#tool-list')).toContainText(/complaint.export_complaint_pdf/i);
    await expect(page.locator('#feature-coverage-list')).toContainText(/Intake workflow/i);
    await expect(page.locator('#feature-coverage-list')).toContainText(/Mediator testimony handoff/i);
    await expect(page.locator('#feature-coverage-list')).toContainText(/Actor\/Critic UI optimizer/i);
    await expect(page.locator('#feature-coverage-list')).toContainText(/available/i);
    await expect(page.locator('#feature-walkthrough-list')).toContainText(/1\. Finish intake/i);
    await expect(page.locator('#feature-walkthrough-list')).toContainText(/2\. Save the mediator brief/i);
    await expect(page.locator('#feature-walkthrough-list')).toContainText(/5\. Coach testimony with the mediator/i);
    await expect(page.locator('#feature-walkthrough-list')).toContainText(/7\. Improve the UI with the optimizer/i);
    await expect(page.locator('#quick-action-grid')).toContainText(/Finish intake/i);
    await expect(page.locator('#quick-action-grid')).toContainText(/Update the mediator brief|Inspect shared tool access/i);
    await expect(page.locator('#quick-action-grid')).toContainText(/Run the actor\/critic optimizer/i);
    await page.locator('#shortcut-optimizer-button').click();
    await expect(page.locator('#workspace-status')).toContainText(/Opened UX Audit/i);
    await expect(page.locator('#ux-review-notes')).toBeFocused();
    await page.locator('#shortcut-tools-button').click();
    await expect(page.locator('#workspace-status')).toContainText(/Opened CLI \+ MCP/i);
    await expect(page.locator('#tool-list')).toBeVisible();
    await page.locator('#shortcut-intake-button').click();
    await expect(page.locator('#workspace-status')).toContainText(/Opened Intake/i);
    await expect(page.locator('#intake-party_name')).toBeFocused();
    await expect(page.locator('#shortcut-review-button')).toBeDisabled();
    await expect(page.locator('#shortcut-review-button')).toHaveAttribute('title', /Finish more intake and save at least one targeted evidence item/i);

    await revealAllIntakeFields(page);
    await page.locator('#intake-party_name').fill('Jane Doe');
    await page.locator('#intake-opposing_party').fill('Acme Corporation');
    await page.locator('#intake-protected_activity').fill('Reported discrimination to HR');
    await page.locator('#intake-adverse_action').fill('Termination two days later');
    await page.locator('#intake-timeline').fill('Complaint on March 8, termination on March 10');
    await page.locator('#intake-harm').fill('Lost wages and benefits');
    await page.locator('#intake-court_header').fill('FOR THE NORTHERN DISTRICT OF CALIFORNIA');
    await page.locator('#save-intake-button').click();

    await expect(page.locator('#workspace-status')).toContainText(/Intake answers saved/i);
    await expect(page.locator('#next-question-label')).toContainText(/Intake complete/i);
    await expect(page.locator('#feature-walkthrough-list')).toContainText(/The core story has been captured/i);
    await page.locator('#case-synopsis').fill('Jane Doe alleges retaliation after reporting discrimination to HR, with the timeline already captured and the main remaining need being corroboration.');
    await page.locator('#save-synopsis-button').click();
    await expect(page.locator('#workspace-status')).toContainText(/Shared case synopsis saved/i);
    await page.locator('#handoff-chat-button').click();
    await expect(page).toHaveURL(/\/chat\?/);
    await expect(page.locator('#chat-context-card')).toBeVisible();
    await expect(page.locator('#chat-context-summary')).toContainText(/Jane Doe alleges retaliation/i);
    await expect(page.locator('#chat-context-prefill')).toContainText(/Prepared question/i);
    await expect(page.locator('#chat-form input')).toHaveValue(/Mediator, help turn this into testimony-ready narrative/i);
    await page.goto('/workspace');
    await expect(page.locator('#case-synopsis')).toHaveValue(/Jane Doe alleges retaliation/i);
    await page.locator('#shortcut-evidence-button').click();
    await expect(page.locator('#workspace-status')).toContainText(/Opened Evidence so support can be attached to the case theory/i);
    await expect(page.locator('#evidence-title')).toBeFocused();

    await page.getByRole('button', { name: 'Evidence', exact: true }).click();
    await page.locator('#evidence-kind').selectOption('document');
    await page.locator('#evidence-claim-element').selectOption('causation');
    await page.locator('#evidence-title').fill('Termination email');
    await page.locator('#evidence-source').fill('Inbox export');
    await page.locator('#evidence-content').fill('The termination followed the HR complaint within two days.');
    await page.locator('#evidence-attachment').setInputFiles({
      name: 'termination-email.txt',
      mimeType: 'text/plain',
      buffer: Buffer.from('Termination email attachment'),
    });
    await page.locator('#save-evidence-button').click();

    await expect(page.locator('#workspace-status')).toContainText(/Evidence saved and support review refreshed/i);
    await expect(page.locator('#evidence-list')).toContainText(/Termination email/i);
    await expect(page.locator('#evidence-list')).toContainText(/termination-email\.txt/i);
    await expect(page.locator('#shortcut-review-button')).toBeEnabled();
    await page.locator('#shortcut-review-button').click();
    await expect(page.locator('#workspace-status')).toContainText(/Opened Review/i);
    await expect(page.locator('#support-grid')).toBeVisible();

    await page.getByRole('button', { name: 'Draft', exact: true }).click();
    await page.locator('#draft-title').fill('Jane Doe v. Acme Corporation Complaint');
    await page.locator('#requested-relief').fill('Back pay\nInjunctive relief');
    await page.locator('#generate-draft-button').click();

    await expect(page.locator('#workspace-status')).toContainText(/Complaint draft generated through the llm_router formal complaint path/i);
    await expect(page.locator('#draft-preview')).toContainText(/Jane Doe brings this retaliation complaint against Acme Corporation/i);
    await expect(page.locator('#feature-walkthrough-list')).toContainText(/A complaint draft exists and can be refined/i);
    await page.locator('#export-packet-button').click();
    await expect(page.locator('#workspace-status')).toContainText(/Complaint packet exported/i);
    await expect(page.locator('#packet-preview')).toContainText(/Title: Jane Doe v\. Acme Corporation Complaint/i);
    await expect(page.locator('#packet-preview')).toContainText(/Jane Doe brings this retaliation complaint against Acme Corporation/i);

    await page.getByRole('button', { name: 'CLI + MCP', exact: true }).click();
    await expect(page.locator('body')).toContainText(/complaint-workspace session/i);
    await expect(page.locator('body')).toContainText(/complaint-mcp-server/i);
    await expect(page.locator('#tool-list')).toContainText(/complaint.review_case/i);
    await expect(page.locator('#tool-list')).toContainText(/complaint.optimize_ui/i);

    await page.locator('#quick-action-grid').getByRole('button', { name: 'Open UX Audit' }).click();
    await expect(page.locator('#workspace-status')).toContainText(/Opened UX Audit so the actor\/critic optimizer workflow can be used/i);
    await expect(page.locator('#ux-review-goals')).toContainText(/JavaScript SDK paths visibly connected/i);
    await expect(page.locator('#ux-review-notes')).toContainText(/complaint workflow/i);

    await page.getByRole('button', { name: 'UX Audit', exact: true }).click();
    await page.locator('#ux-review-screenshot-dir').fill('artifacts/ui-audit/screenshots');
    await page.locator('#ux-review-output-path').fill('artifacts/ui-audit/reviews');
    await page.locator('#ux-review-iterations').fill('2');
    await page.locator('#ux-review-max-rounds').fill('3');
    await expect(page.locator('#ux-review-method')).toHaveValue('actor_critic');
    await page.locator('#ux-review-priority').fill('91');
    await page.locator('#ux-review-goals').fill('Make the complaint workspace easier for first-time users.\nKeep every feature reachable through the shared MCP SDK.');
    await page.locator('#run-ux-review-button').click();

    await expect(page.locator('#workspace-status')).toContainText(/Iterative UI\/UX review completed/i);
    await expect(page.locator('#ux-review-summary')).toContainText(/Top Risks/i);
    await expect(page.locator('#ux-review-scorecard')).toContainText(/Client readiness gate/i);
    await expect(page.locator('#ux-review-scorecard')).toContainText(/Do not send to clients yet|Needs repair|Client-safe/i);
    await expect(page.locator('#ux-review-scorecard')).toContainText(/Workflow coverage/i);
    await expect(page.locator('#ux-review-scorecard')).toContainText(/Shared contract exposure/i);
    await expect(page.locator('#ux-review-actor-critic')).toContainText(/Actor journey/i);
    await expect(page.locator('#ux-review-actor-critic')).toContainText(/Critic obligations/i);
    await expect(page.locator('#ux-review-runs')).toContainText(/Iteration 1/i);
    await expect(page.locator('#ux-review-stage-findings')).toContainText(/First-time complainants need clearer reassurance that incomplete dates and imperfect wording can still be saved/i);
    await expect(page.locator('#ux-review-stage-findings')).toContainText(/The Gmail import affordance keeps evidence ingestion inside the browser workspace and the shared MCP SDK path|The evidence step should explain which documents help prove causation before users are asked to upload or summarize proof/i);
    await expect(page.locator('#ux-review-stage-findings')).not.toContainText(/Markdown fallback should not replace the structured intake guidance/i);
    await expect(page.locator('#ux-review-stage-findings')).not.toContainText(/Markdown fallback should not replace the structured evidence guidance/i);

    await page.locator('#run-ux-closed-loop-button').click();

    await expect(page.locator('#workspace-status')).toContainText(/Closed-loop UI\/UX optimization completed/i);
    await expect(page.locator('#ux-review-metadata')).toContainText(/rounds:/i);
    await expect(page.locator('#ux-review-scorecard')).toContainText(/Critic release gate/i);
    await expect(page.locator('#ux-review-scorecard')).toContainText(/Broken control pressure/i);
    await expect(page.locator('#ux-review-scorecard')).toContainText(/complaint\.review_ui|complaint\.optimize_ui/i);
    await expect(page.locator('#ux-review-actor-critic')).toContainText(/Verify the actor can save the mediator synopsis, upload evidence, review support, generate the complaint, and revise the draft/i);
    await expect(page.locator('#ux-review-stage-findings')).toContainText(/Intake/i);
    await expect(page.locator('#ux-review-stage-findings')).toContainText(/The evidence panel still needs stronger claim-element guidance after optimization/i);
    await expect(page.locator('#ux-review-metadata')).toContainText(/stop:/i);
    await expect(page.locator('#ux-review-metadata')).toContainText(/output:/i);
    await expect(page.locator('#ux-review-runs')).toContainText(/Round 1/i);
    await expect(page.locator('#ux-review-runs')).toContainText(/templates\/workspace\.html/i);
    await expect(page.locator('#ux-review-stage-findings')).toContainText(/The optimizer path itself should stay discoverable from the shared dashboard shortcuts and tool panels/i);
    await expect(page.locator('#ux-review-stage-findings')).not.toContainText(/Markdown fallback should not replace the structured integration-discovery guidance/i);
    await expect(page.locator('#ux-review-artifacts')).toContainText(/round-01\.patch/i);
    await expect(page.locator('#ux-review-artifacts')).toContainText(/bafyuiuxround01/i);
    await expect(page.locator('#ux-review-artifacts')).toContainText(/static\/complaint_mcp_sdk\.js/i);

    await page.goto('/');
    await expect(page.locator('#homepage-ui-readiness-summary')).toContainText(/Do not send to clients yet|Needs repair|Client-safe/i);
    await expect(page.locator('#homepage-ui-readiness-summary')).toContainText(/100|release blocker|No release blocker/i);
  });

  test('workspace integrations stay usable on a narrow viewport', async ({ page }, testInfo) => {
    test.slow();
    await page.addInitScript(() => {
      window.localStorage.setItem('complaintGenerator.did', 'did:key:nav-workspace-mobile');
    });
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto('/workspace?shell_mode=operator');
    await waitForWorkspaceReady(page, { requireIntakeVisible: false });
    await expect(page.locator('body')).toHaveAttribute('data-workspace-shell-mode', 'operator');

    await page.getByRole('button', { name: 'CLI + MCP', exact: true }).click();
    await expect(page.locator('#integrations-start-readiness-button')).toBeVisible({ timeout: 10000 });
    await expect(page.locator('#integrations-start-export-button')).toBeVisible();
    await expect(page.locator('#integrations-technical-reference summary')).toContainText(/Advanced package, CLI, MCP, and browser SDK reference/i);
    await expect(page.locator('#integrations-technical-reference')).not.toHaveAttribute('open', '');
    await expect(page.locator('#integrations-operator-panels')).not.toHaveAttribute('open', '');
    await expect(page.locator('#feature-coverage-list')).toContainText(/Actor\/Critic UI optimizer/i);
    await expect(page.locator('#tool-list')).toContainText(/complaint\.optimize_ui/i);

    const panelMetrics = await page.locator('[data-tab-panel="integrations"]').evaluate((node) => ({
      clientWidth: node.clientWidth,
      scrollWidth: node.scrollWidth,
    }));
    expect(panelMetrics.scrollWidth).toBeLessThanOrEqual(panelMetrics.clientWidth + 2);
    await expectScreenshotBudget(page.locator('[data-tab-panel="integrations"]'), {
      label: 'mobile integrations panel',
      maxRenderedHeight: 7200,
      maxScrollHeight: 7200,
    });

    const screenshotPath = testInfo.outputPath('workspace-integrations-mobile.png');
    await page.locator('[data-tab-panel="integrations"]').screenshot({ path: screenshotPath });
    await testInfo.attach('workspace-integrations-mobile', {
      path: screenshotPath,
      contentType: 'image/png',
    });
  });

  test('workspace Docket shell stays full-width and actionable on mobile', async ({ page }, testInfo) => {
    await page.addInitScript(() => {
      window.localStorage.setItem('complaintGenerator.did', 'did:key:nav-docket-mobile');
    });
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto('/workspace');
    await waitForWorkspaceReady(page);

    await page.locator('[data-tab-target="docket"]').click();
    const docketPanel = page.locator('[data-tab-panel="docket"]');
    await expect(docketPanel).toHaveClass(/is-active/);
    await expect(docketPanel).toHaveClass(/mobile-docket-view-documents/);
    await expect(page.locator('#docket-current-task-title')).toBeVisible();
    await expect(page.locator('#docket-mobile-show-documents')).toBeVisible();
    await expect(page.locator('#docket-mobile-show-documents')).toHaveAttribute('aria-pressed', 'true');
    await expect(page.locator('#docket-mobile-show-selected')).toBeDisabled();
    await expect(page.locator('#docket-selected-rail')).toBeHidden();
    await expect(page.locator('#docket-document-list')).toBeVisible();
    await expect(page.locator('#docket-mobile-ask-chat-link')).toBeHidden();
    await expect(page.locator('#docket-mobile-action-note')).toBeHidden();
    await expect(page.locator('.docket-selected-card')).toBeHidden();
    await expect(page.locator('.docket-action-bar.is-empty')).toBeHidden();
    await expect(page.locator('.docket-loader-card .readiness-list')).toBeHidden();
    await expect(page.locator('.docket-loader-card #docket-summary-chips')).toBeHidden();
    await expect(page.locator('.docket-status-card')).toBeHidden();

    const panelMetrics = await docketPanel.evaluate((node) => {
      const rect = node.getBoundingClientRect();
      return {
        clientWidth: node.clientWidth,
        scrollWidth: node.scrollWidth,
        rectWidth: rect.width,
        viewportWidth: window.innerWidth,
      };
    });
    expect(panelMetrics.scrollWidth).toBeLessThanOrEqual(panelMetrics.clientWidth + 2);
    expect(panelMetrics.rectWidth).toBeGreaterThanOrEqual(panelMetrics.viewportWidth - 56);
    await expectScreenshotBudget(docketPanel, {
      label: 'mobile docket empty panel',
      maxRenderedHeight: 3600,
      maxScrollHeight: 3600,
    });

    const screenshotPath = testInfo.outputPath('workspace-docket-mobile.png');
    await docketPanel.screenshot({ path: screenshotPath });
    await testInfo.attach('workspace-docket-mobile', {
      path: screenshotPath,
      contentType: 'image/png',
    });
  });

  test('workspace Docket loaded document stays concise and actionable on mobile', async ({ page }, testInfo) => {
    await page.addInitScript(() => {
      window.localStorage.setItem('complaintGenerator.did', 'did:key:nav-docket-mobile-loaded');
    });
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto('/workspace');
    await waitForWorkspaceReady(page);

    await page.locator('[data-tab-target="evidence"]').click();
    await page.locator('#evidence-kind').selectOption('document');
    await page.locator('#evidence-claim-element').selectOption('causation');
    await page.locator('#evidence-title').fill('Termination timeline email');
    await page.locator('#evidence-source').fill('Inbox export');
    await page.locator('#evidence-content').fill('Email records show the termination followed immediately after the HR complaint.');
    await page.locator('#save-evidence-button').click();
    await expect(page.locator('#workspace-status')).toContainText(/Evidence saved and support review refreshed/i, { timeout: 15000 });

    await page.locator('[data-tab-target="docket"]').click();
    const docketPanel = page.locator('[data-tab-panel="docket"]');
    await expect(docketPanel).toHaveClass(/is-active/);
    await expect(docketPanel).toHaveClass(/has-docket-items/);
    await expect(docketPanel).toHaveClass(/mobile-docket-view-selected/);
    await expect(page.locator('#docket-mobile-show-documents')).toBeVisible();
    await expect(page.locator('#docket-mobile-show-documents')).toContainText(/^Back to Documents$/i);
    await expect(page.locator('#docket-mobile-show-selected')).toHaveAttribute('aria-pressed', 'true');
    await expect(page.locator('#docket-mobile-show-selected')).toBeDisabled();
    await expect(page.locator('#docket-mobile-show-selected')).toBeHidden();
    await expect(page.locator('#docket-mobile-context-status')).toBeVisible();
    await expect(page.locator('#docket-mobile-context-status')).toContainText(/Working on: Termination timeline email/i);
    await expect(page.locator('#docket-mobile-context-status')).toContainText(/1 document in this list/i);
    await expect(page.locator('.docket-documents-card')).toBeHidden();
    await expect(page.locator('[data-tab-panel="docket"] .stage-banner')).toBeHidden();
    await expect(page.locator('#docket-current-task-title')).toBeHidden();
    await expect(page.locator('#docket-selected-rail')).toBeVisible();
    await expect(page.locator('#docket-selected-rail-label')).toContainText(/Selected document/i);
    await expect(page.locator('#docket-selected-rail-title')).toContainText(/Termination timeline email/i);
    await expect(page.locator('#docket-selected-rail-meta')).toContainText(/Source: Inbox export/i);
    await expect(page.locator('#docket-selected-rail-meta')).toContainText(/Type: Document/i);
    await expect(page.locator('#docket-selected-rail-badges')).toContainText(/Step 1: Current/i);
    await expect(page.locator('#docket-selected-rail-badges')).toContainText(/Step 2: Locked/i);
    await expect(page.locator('#docket-selected-rail-badges')).toContainText(/Step 3: Locked/i);
    await expect(page.locator('#docket-selected-rail-badges')).toContainText(/Step 4: Locked/i);
    await expect(page.locator('#docket-selected-rail-badges')).toBeHidden();
    await expect(page.locator('#docket-mobile-ask-chat-link')).toBeVisible();
    await expect(page.locator('#docket-mobile-step-ask')).toHaveClass(/is-current/);
    await expect(page.locator('#docket-mobile-step-ask')).toHaveCount(1);
    await expect(page.locator('#docket-mobile-step-ask')).toHaveAttribute('aria-current', 'step');
    await expect(page.locator('#docket-mobile-step-ask')).toHaveAttribute('data-step-state', 'active');
    await expect(page.locator('#docket-mobile-step-label')).toHaveAttribute('data-step-state', 'waiting');
    await expect(page.locator('#docket-mobile-step-annotation')).toHaveAttribute('data-step-state', 'waiting');
    await expect(page.locator('#docket-mobile-step-deadline')).toHaveAttribute('data-step-state', 'blocked');
    await expect(page.locator('#docket-mobile-step-label')).toHaveClass(/is-locked-accordion/);
    await expect(page.locator('#docket-mobile-step-annotation')).toHaveClass(/is-locked-accordion/);
    await expect(page.locator('#docket-mobile-step-deadline')).toHaveClass(/is-locked-accordion/);
    await expect(page.locator('#docket-mobile-step-deadline')).toHaveClass(/is-blocked/);
    await expect(page.locator('#docket-mobile-step-ask .docket-mobile-step-heading')).toContainText(/Step 1: Start document chat/i);
    await expect(page.locator('#docket-mobile-ask-chat-link')).toContainText(/^Open Chat$/i);
    await expect(page.locator('#docket-mobile-ask-chat-link')).not.toHaveAttribute('aria-disabled', 'true');
    await expect(page.locator('#docket-mobile-ask-chat-link')).toHaveClass(/docket-mobile-primary-action/);
    await expect(page.locator('#docket-mobile-label-button')).toHaveClass(/docket-mobile-secondary-action/);
    await expect(page.locator('#docket-mobile-annotation-button')).toHaveClass(/docket-mobile-secondary-action/);
    await expect(page.locator('#docket-mobile-deadline-button')).toHaveClass(/docket-mobile-deadline-action/);
    await expect(page.locator('#docket-mobile-ask-scope')).toContainText(/Chatting about: Termination timeline email/i);
    await expect(page.locator('#docket-mobile-ask-scope')).toContainText(/Questions will apply only to this document/i);
    await expect(page.locator('#docket-mobile-ask-state')).toContainText(/Not started Next: ask at least one document-specific question/i);
    await expect(page.locator('#docket-mobile-step1-state-contract')).toBeVisible();
    await expect(page.locator('#docket-mobile-step1-current-state')).toContainText(/^not_started$/i);
    await expect(page.locator('#docket-mobile-step1-first-unmet')).toContainText(/^ask one document-specific question first$/i);
    await expect(page.locator('#docket-mobile-step1-persistence-mode')).toContainText(/^local_until_ready$/i);
    await expect(page.locator('#docket-mobile-next-unlock')).toContainText(/Ask your first document-specific question to show Confirm this document is ready to label/i);
    await expect(page.locator('#docket-mobile-step1-write-count')).toContainText(/Document updates captured: 0/i);
    await expect(page.locator('#docket-mobile-step1-checklist')).toContainText(/Question asked: No/i);
    await expect(page.locator('#docket-mobile-step1-checklist')).toContainText(/Create impact summary after the first chat question/i);
    await expect(page.locator('#docket-mobile-step1-checklist')).toContainText(/Confirm ready to label/i);
    await expect(page.locator('#docket-mobile-gate-summary')).toBeHidden();
    await expect(page.locator('#docket-mobile-gate-summary')).toContainText(/0 of 3 complete: ask one document-specific question first/i);
    await expect(page.locator('#docket-mobile-check-question')).toContainText(/Question asked: No/i);
    await expect(page.locator('#docket-mobile-check-question')).toHaveAttribute('data-check-state', 'missing');
    await expect(page.locator('#docket-mobile-check-impact')).toContainText(/Create impact summary after the first chat question/i);
    await expect(page.locator('#docket-mobile-check-impact')).toBeHidden();
    await expect(page.locator('#docket-mobile-check-impact')).toHaveAttribute('data-check-state', 'blocked');
    await expect(page.locator('#docket-mobile-check-ready')).toBeDisabled();
    await expect(page.locator('#docket-mobile-check-ready')).toBeHidden();
    await expect(page.locator('#docket-mobile-check-ready')).toHaveAttribute('data-check-state', 'blocked');
    await expect(page.locator('#docket-mobile-ask-feedback')).toBeHidden();
    await expect(page.locator('#docket-mobile-ask-feedback')).toContainText(/The ready-to-label confirmation is disabled until the first unmet checklist item is complete/i);
    await expect(page.locator('#docket-mobile-ask-persistence')).toBeHidden();
    await expect(page.locator('#docket-mobile-ask-persistence')).toContainText(/Persistence mode: local draft only until ready confirmation/i);
    await expect(page.locator('#docket-mobile-ready-label-button')).toBeHidden();
    await expect(page.locator('#docket-mobile-ready-label-button')).toBeDisabled();
    await expect(page.locator('#docket-mobile-ready-label-button')).toHaveAttribute('aria-describedby', 'docket-mobile-ready-disabled-reason');
    await expect(page.locator('#docket-mobile-ready-label-button')).toContainText(/Next after chat: Confirm this document is ready to label/i);
    await expect(page.locator('#docket-mobile-ready-disabled-reason')).toContainText(/After you use Open Chat and ask one document question, the ready-to-label confirmation appears here/i);
    await expect(page.locator('#docket-mobile-save-status')).toContainText(/Persistence: local draft only until ready confirmation/i);
    await expect(page.locator('#docket-mobile-save-status')).toHaveAttribute('data-save-state', 'idle');
    await expect(page.locator('#docket-mobile-save-status')).toHaveAttribute('data-persistence-mode', 'local_until_ready');
    await expect(page.locator('#docket-mobile-label-button')).toBeDisabled();
    await expect(page.locator('#docket-mobile-label-button')).toBeHidden();
    await expect(page.locator('#docket-mobile-label-button')).toContainText(/^Label Document$/i);
    await expect(page.locator('#docket-mobile-label-summary')).toBeHidden();
    await expect(page.locator('#docket-mobile-label-summary')).toContainText(/Locked: complete Step 1 first/i);
    await expect(page.locator('#docket-mobile-label-state')).toContainText(/Locked Unlocks when Step 1 has an impact summary and ready-to-label confirmation/i);
    await expect(page.locator('#docket-mobile-annotation-button')).toBeDisabled();
    await expect(page.locator('#docket-mobile-annotation-button')).toBeHidden();
    await expect(page.locator('#docket-mobile-annotation-button')).toContainText(/^Add Note or Date$/i);
    await expect(page.locator('#docket-mobile-annotation-summary')).toBeHidden();
    await expect(page.locator('#docket-mobile-annotation-summary')).toContainText(/Locked: complete Step 1 first/i);
    await expect(page.locator('#docket-mobile-annotation-state')).toContainText(/Locked Unlocks when Step 1 has an impact summary and ready-to-label confirmation/i);
    await expect(page.locator('#docket-mobile-deadline-button')).toBeDisabled();
    await expect(page.locator('#docket-mobile-deadline-button')).toBeHidden();
    await expect(page.locator('#docket-mobile-deadline-button')).toContainText(/^Deadline Needs Date$/i);
    await expect(page.locator('#docket-mobile-deadline-button')).toHaveAttribute('aria-describedby', 'docket-mobile-deadline-state');
    await expect(page.locator('#docket-mobile-deadline-summary')).toBeHidden();
    await expect(page.locator('#docket-mobile-deadline-summary')).toContainText(/Locked: add a response date in Step 3 first/i);
    await expect(page.locator('#docket-mobile-deadline-state')).toContainText(/Locked Unlocks when Step 3 saves a response date/i);
    await expect(page.locator('#docket-mobile-action-note')).toBeHidden();
    await expect(page.locator('.docket-loader-card')).toBeHidden();
    await expect(page.locator('.docket-action-bar')).toBeHidden();
    await expect(page.locator('.docket-selected-card')).toBeHidden();
    await expect(page.locator('#docket-source-summary')).toBeHidden();
    await expect(page.locator('#docket-mobile-technical-details')).toBeHidden();

    const metrics = await docketPanel.evaluate((node) => {
      const rail = document.querySelector('#docket-selected-rail');
      const actions = document.querySelector('.docket-mobile-action-strip');
      const rect = node.getBoundingClientRect();
      const railRect = rail.getBoundingClientRect();
      const actionsRect = actions.getBoundingClientRect();
      const askStyle = getComputedStyle(document.querySelector('#docket-mobile-ask-chat-link'));
      const selectedCardDisplay = getComputedStyle(document.querySelector('.docket-selected-card')).display;
      const labelButtonDisplay = getComputedStyle(document.querySelector('#docket-mobile-label-button')).display;
      const labelSummaryAfter = getComputedStyle(document.querySelector('#docket-mobile-step-label summary'), '::after').content;
      const labelSummaryPointerEvents = getComputedStyle(document.querySelector('#docket-mobile-step-label summary')).pointerEvents;
      const lockedAccordionCount = document.querySelectorAll('.docket-mobile-step.is-locked-accordion:not([open])').length;
      const visibleStep1PanelCount = [...document.querySelectorAll('#docket-mobile-step-ask')]
        .filter((node) => getComputedStyle(node).display !== 'none').length;
      const selectedWriteRequestCount = performance.getEntriesByType('resource')
        .filter((entry) => /ready_to_label|selected_document|docket.*write/i.test(entry.name)).length;
      const visibleHeaderButtons = [...document.querySelectorAll('.docket-mobile-view-switch button')]
        .filter((button) => getComputedStyle(button).display !== 'none');
      return {
        clientWidth: node.clientWidth,
        scrollWidth: node.scrollWidth,
        rectWidth: rect.width,
        viewportWidth: window.innerWidth,
        railHeight: railRect.height,
        railBottom: railRect.bottom,
        actionsTop: actionsRect.top,
        selectedCardDisplay,
        labelButtonDisplay,
        labelSummaryAfter,
        labelSummaryPointerEvents,
        lockedAccordionCount,
        visibleStep1PanelCount,
        selectedWriteRequestCount,
        askColor: askStyle.color,
        visibleHeaderButtonCount: visibleHeaderButtons.length,
      };
    });
    expect(metrics.scrollWidth).toBeLessThanOrEqual(metrics.clientWidth + 2);
    expect(metrics.rectWidth).toBeGreaterThanOrEqual(metrics.viewportWidth - 56);
    expect(metrics.railHeight).toBeLessThanOrEqual(150);
    expect(metrics.railBottom).toBeLessThanOrEqual(metrics.actionsTop);
    expect(metrics.selectedCardDisplay).toBe('none');
    expect(metrics.labelButtonDisplay).toBe('none');
    expect(metrics.labelSummaryAfter).toContain('Locked');
    expect(metrics.labelSummaryPointerEvents).toBe('none');
    expect(metrics.lockedAccordionCount).toBeGreaterThanOrEqual(3);
    expect(metrics.visibleStep1PanelCount).toBe(1);
    expect(metrics.selectedWriteRequestCount).toBe(0);
    expect(metrics.askColor).toBe('rgb(255, 255, 255)');
    expect(metrics.visibleHeaderButtonCount).toBe(1);

    await page.evaluate(() => {
      const documents = (((workspaceSession || {}).review || {}).documents || []);
      const firstDocument = documents[0];
      if (firstDocument) {
        firstDocument.question_count = 1;
        firstDocument.impact_summary = '';
        firstDocument.ready_to_label_saved = false;
        firstDocument.selected_document_write_count = 0;
      }
      renderDocketLane(workspaceSession || {});
    });
    await expect(page.locator('#docket-mobile-step-ask')).toHaveClass(/is-current/);
    await expect(page.locator('#docket-mobile-step-ask')).toHaveAttribute('data-step-state', 'active');
    await expect(page.locator('#docket-mobile-step-label')).toHaveAttribute('data-step-state', 'waiting');
    await expect(page.locator('#docket-mobile-step-annotation')).toHaveAttribute('data-step-state', 'waiting');
    await expect(page.locator('#docket-mobile-step1-current-state')).toContainText(/^chat_started$/i);
    await expect(page.locator('#docket-mobile-step1-first-unmet')).toContainText(/^create the impact summary from chat$/i);
    await expect(page.locator('#docket-gate-presenter')).toHaveAttribute('data-current-state', 'chat_started');
    await expect(page.locator('#docket-gate-presenter')).toHaveAttribute('data-ready-eligible', 'false');
    await expect(page.locator('#docket-gate-primary-action')).toContainText(/Generate Impact Summary/i);
    await expect(page.locator('#docket-gate-secondary-chat-link')).toContainText(/Open Chat/i);
    await expect(page.locator('#docket-gate-write-count')).toContainText(/Document updates captured: 0/i);
    await expect(page.locator('#docket-mobile-next-unlock')).toContainText(/Review the chat impact summary to turn on Confirm this document is ready to label/i);
    await expect(page.locator('#docket-mobile-check-question')).toContainText(/Question asked: Yes \(1\)/i);
    await expect(page.locator('#docket-mobile-check-question')).toHaveAttribute('data-check-state', 'complete');
    await expect(page.locator('#docket-mobile-check-impact')).toBeVisible();
    await expect(page.locator('#docket-mobile-check-impact')).toContainText(/Create impact summary from chat/i);
    await expect(page.locator('#docket-mobile-check-impact')).toHaveAttribute('data-check-state', 'missing');
    await expect(page.locator('#docket-mobile-check-ready')).toBeHidden();
    await expect(page.locator('#docket-mobile-ready-label-button')).toBeVisible();
    await expect(page.locator('#docket-mobile-ready-label-button')).toBeDisabled();
    await expect(page.locator('#docket-mobile-ready-label-button')).toHaveAttribute('data-ready-visibility', 'guided');
    await expect(page.locator('#docket-mobile-ready-label-button')).toContainText(/^Confirm this document is ready to label$/i);
    await expect(page.locator('#docket-mobile-ready-disabled-reason')).toContainText(/Waiting for the chat impact summary before the ready-to-label confirmation can save/i);
    await expect(page.locator('#docket-mobile-step1-write-count')).toContainText(/Document updates captured: 0/i);
    await expect(page.locator('#docket-mobile-label-button')).toBeDisabled();
    await expect(page.locator('#docket-mobile-annotation-button')).toBeDisabled();
    const postChatMetrics = await docketPanel.evaluate((node) => {
      const selectedWriteRequestCount = performance.getEntriesByType('resource')
        .filter((entry) => /ready_to_label|selected_document|docket.*write/i.test(entry.name)).length;
      const readyRect = document.querySelector('#docket-mobile-ready-label-button').getBoundingClientRect();
      return {
        scrollWidth: node.scrollWidth,
        clientWidth: node.clientWidth,
        selectedWriteRequestCount,
        readyButtonHeight: readyRect.height,
      };
    });
    expect(postChatMetrics.scrollWidth).toBeLessThanOrEqual(postChatMetrics.clientWidth + 2);
    expect(postChatMetrics.readyButtonHeight).toBeGreaterThanOrEqual(40);
    expect(postChatMetrics.selectedWriteRequestCount).toBe(0);

    await page.evaluate(() => document.getElementById('docket-gate-primary-action').click());
    await expect(page.locator('#workspace-status')).toContainText(/Impact summary generated locally\. No selected-document write has been sent\./i);
    await expect(page.locator('#docket-gate-presenter')).toHaveAttribute('data-current-state', 'impact_summary_ready');
    await expect(page.locator('#docket-gate-presenter')).toHaveAttribute('data-ready-eligible', 'true');
    await expect(page.locator('#docket-gate-ready-action')).toContainText(/Confirm this document is ready to label/i);
    await expect(page.locator('#docket-gate-write-count')).toContainText(/Document updates captured: 0/i);

    await page.locator('#docket-mobile-show-documents').click();
    await expect(docketPanel).toHaveClass(/mobile-docket-view-documents/);
    await expect(page.locator('.docket-documents-card')).toBeVisible();
    await expect(page.locator('#docket-selected-rail')).toBeHidden();
    await expect(page.locator('#docket-mobile-ask-chat-link')).toBeHidden();
    await expect(page.locator('#docket-mobile-show-selected')).toBeEnabled();
    await expect(page.locator('#docket-mobile-show-selected')).toBeVisible();

    await page.locator('#docket-mobile-show-selected').click();
    await expect(docketPanel).toHaveClass(/mobile-docket-view-selected/);
    await expect(page.locator('.docket-documents-card')).toBeHidden();
    await expect(page.locator('#docket-selected-rail')).toBeVisible();
    await expect(page.locator('.docket-selected-card')).toBeHidden();
    await expectScreenshotBudget(docketPanel, {
      label: 'mobile docket loaded panel',
      maxRenderedHeight: 4200,
      maxScrollHeight: 4200,
    });

    const screenshotPath = testInfo.outputPath('workspace-docket-mobile-loaded.png');
    await docketPanel.screenshot({ path: screenshotPath });
    await testInfo.attach('workspace-docket-mobile-loaded', {
      path: screenshotPath,
      contentType: 'image/png',
    });
  });

  test('first-class pages share the same DID-backed application sidebar and session summary', async ({ page, request }) => {
    await page.addInitScript(() => {
      window.localStorage.setItem('complaintGenerator.did', 'did:key:nav-shared-shell');
    });
    await page.goto('/');

    const cachedDid = await page.evaluate(() => window.localStorage.getItem('complaintGenerator.did'));
    expect(cachedDid).toMatch(/^did:key:/);

    await request.post('/api/complaint-workspace/mcp/rpc', {
      data: {
        jsonrpc: '2.0',
        id: 1,
        method: 'tools/call',
        params: {
          name: 'complaint.reset_session',
          arguments: {
            user_id: cachedDid,
          },
        },
      },
    });

    await request.post('/api/complaint-workspace/mcp/rpc', {
      data: {
        jsonrpc: '2.0',
        id: 2,
        method: 'tools/call',
        params: {
          name: 'complaint.submit_intake',
          arguments: {
            user_id: cachedDid,
            answers: {
              party_name: 'Jordan Rivera',
              opposing_party: 'Acme Health Systems',
              protected_activity: 'Reported patient safety violations',
              adverse_action: 'Termination',
              timeline: 'Reported in January and was fired in March',
              harm: 'Lost wages and emotional distress',
            },
          },
        },
      },
    });

    const seededSession = await request.get(`/api/complaint-workspace/session?user_id=${encodeURIComponent(cachedDid)}`);
    const seededJson = await seededSession.json();
    expect(Object.keys(seededJson.session.intake_answers)).toHaveLength(6);

    await page.goto('/');
    await expect(page.locator('#cg-app-shell')).toHaveCount(0);
    await expect(page.locator('#homepage-did')).toContainText(cachedDid);
    await expect(page.locator('#homepage-intake-count')).toHaveText('6');
    await expect(page.locator('#homepage-supported-count')).toHaveText('5');
    await expect(page.locator('#homepage-evidence-count')).toHaveText('0');
    await expect(page.locator('#homepage-tool-count')).not.toHaveText('0');
    await expect(page.locator('#homepage-session-status')).toContainText(cachedDid);
    await expect(page.locator('#homepage-resume-link')).toHaveAttribute('href', new RegExp(`/claim-support-review\\?[^\"]*user_id=${encodeURIComponent(cachedDid)}`));
    await expect(page.locator('#homepage-open-workspace')).toHaveAttribute('href', new RegExp(`/claim-support-review\\?[^\"]*user_id=${encodeURIComponent(cachedDid)}`));
    await expect(page.locator('#homepage-open-workspace')).toContainText(/Review Claim Support|Review Support First/i);
    await expect(page.locator('#homepage-nav-builder')).toHaveAttribute('href', new RegExp(`/document\\?[^\"]*user_id=${encodeURIComponent(cachedDid)}`));
    await expect(page.locator('#homepage-nav-chat')).toHaveAttribute('href', new RegExp(`/chat\\?[^\"]*user_id=${encodeURIComponent(cachedDid)}`));
    await expect(page.locator('#homepage-next-step')).toContainText(/Inspect missing claim elements/i);
    await expect(page.locator('#homepage-complaint-readiness-summary')).toContainText(/Still building the record|Ready for first draft|Draft in progress/i);

    await page.goto(`/home?user_id=${encodeURIComponent(cachedDid)}&case_synopsis=${encodeURIComponent('Jordan Rivera reported patient safety violations before termination.')}`);
    await expect(page).toHaveURL(new RegExp(`/chat\\?[^\"]*user_id=${encodeURIComponent(cachedDid)}`));
    await expect(page.locator('#chat-nav-review')).toHaveAttribute('href', new RegExp(`/claim-support-review\\?[^\"]*user_id=${encodeURIComponent(cachedDid)}`));

    await page.goto(`/document/optimization-trace?user_id=${encodeURIComponent(cachedDid)}&claim_type=retaliation&cid=trace-demo-cid`);
    await expect(page.locator('#trace-nav-review')).toHaveAttribute('href', new RegExp(`/claim-support-review\\?[^\"]*user_id=${encodeURIComponent(cachedDid)}`));
    await expect(page.locator('#trace-open-builder')).toHaveAttribute('href', new RegExp(`/document\\?[^\"]*user_id=${encodeURIComponent(cachedDid)}`));
    await expect(page.locator('#trace-nav-trace')).toHaveAttribute('href', /cid=trace-demo-cid/);
    await expect(page.locator('#cg-app-shell a[href*="user_id="]').first()).toBeVisible();

    for (const path of ['/home', '/chat', '/profile', '/results', '/document', '/claim-support-review', '/mlwysiwyg', '/document/optimization-trace', '/ipfs-datasets/sdk-playground']) {
      await page.goto(path);
      await expect(page.locator('#cg-app-shell')).toBeVisible();
      await expect(page.locator('#cg-app-shell-did')).toContainText(cachedDid);
      await expect(page.locator('#cg-app-shell-intake-count')).toHaveText('6');
      await expect(page.locator('#cg-app-shell-supported-count')).toHaveText('5');
      await expect(page.locator('#cg-app-shell-complaint-readiness')).toContainText(/Not ready to draft|Still building the record|Ready for first draft|Draft in progress/i);
      await expect(page.locator('#cg-app-shell-complaint-readiness')).toContainText(/Answered intake:/i);
      await expect(page.locator(`#cg-app-shell a[href*="/workspace?"][href*="user_id=${encodeURIComponent(cachedDid)}"]`).first()).toBeVisible();
      await expect(page.locator(`#cg-app-shell a[href*="/document?"][href*="user_id=${encodeURIComponent(cachedDid)}"]`).first()).toBeVisible();
      await expect(page.locator(`#cg-app-shell a[href*="/claim-support-review?"][href*="user_id=${encodeURIComponent(cachedDid)}"]`).first()).toBeVisible();
    }
  });
});
