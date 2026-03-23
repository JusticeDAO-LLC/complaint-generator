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
    await expect(page.locator('body')).toContainText(/Resume an existing complaint/i);
    await expect(page.locator('body')).toContainText(/Three Simple Steps/i);
    await expect(page.locator('body')).toContainText(/Choose Your Next Step/i);
    await expect(page.locator('a[href="/workspace"]').first()).toBeVisible();
    await expect(page.locator('a[href="/claim-support-review"]').first()).toBeVisible();
    await expect(page.locator('a[href="/document"]').first()).toBeVisible();
    await expect(page.locator('#homepage-session-badge')).toContainText(/Connected|Offline/i);
    await expect(page.locator('#homepage-did')).toContainText(/did:key:|Unavailable/i);
    await expect(page.locator('#cg-app-shell')).toHaveCount(0);
    await expect(page.locator('[data-surface-nav="primary"]')).toContainText(/Secure Intake/i);
    await expect(page.locator('[data-surface-nav="primary"]')).toContainText(/Builder/i);

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
    await expect(page.locator('a[href="/workspace"]').first()).toBeVisible();
    await expect(page.locator('a[href="/claim-support-review"]').first()).toBeVisible();

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
    await expect(page.locator('a[href="/workspace"]').first()).toBeVisible();
    await expect(page.locator('a[href="/claim-support-review"]').first()).toBeVisible();
    await expect(page.locator('a[href="/document"]').first()).toBeVisible();
    await expect(page.locator('body')).toContainText(/Three Simple Steps/i);
    await expect(page.locator('body')).toContainText(/Choose Your Next Step/i);
    await expect(page.locator('#homepage-next-step')).toBeVisible();
    await expect(page.locator('#cg-app-shell')).toHaveCount(0);

    await page.goto('/chat');
    await expect(page.locator('a[href="/document"]').first()).toBeVisible();
    await expect(page.locator('a[href="/claim-support-review"]').first()).toBeVisible();

    await page.goto('/results');
    await expect(page.locator('a[href="/document"]').first()).toBeVisible();
    await expect(page.locator('a[href="/claim-support-review"]').first()).toBeVisible();

    await page.goto('/document');
    await expect(page.locator('a[href="/claim-support-review"]').first()).toBeVisible();
    await expect(page.locator('a[href="/workspace"]').first()).toBeVisible();
    await expect(page.locator('a[href="/mlwysiwyg"]').first()).toBeVisible();
    await expect(page.locator('a[href="/ipfs-datasets/sdk-playground"]').first()).toBeVisible();

    await page.goto('/claim-support-review');
    await expect(page.locator('a[href="/document"]').first()).toBeVisible();
    await expect(page.locator('a[href="/workspace"]').first()).toBeVisible();
    await expect(page.locator('a[href="/mlwysiwyg"]').first()).toBeVisible();
    await expect(page.locator('a[href="/ipfs-datasets/sdk-playground"]').first()).toBeVisible();
    await expect(page.locator('a[href="/dashboards"]').first()).toBeVisible();
  });

  test('profile and results surfaces explain stored complaint state clearly', async ({ page }, testInfo) => {
    await page.goto('/profile');
    await expect(page).toHaveTitle(/Profile Data/i);
    await expect(page.locator('h1').first()).toContainText(/Profile data without the clutter/i);
    await expect(page.locator('body')).toContainText(/A readable snapshot of the complaint account, stored facts, and recent guided intake history/i);
    await expect(page.locator('body')).toContainText(/Connected workflow/i);
    await expect(page.locator('#profile_data')).toBeVisible();
    await expect(page.locator('#chat_history')).toBeVisible();
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
    await expect(page.locator('h1').first()).toContainText(/Tell the story before the pleading/i);
    await expect(page.locator('body')).toContainText(/What to focus on in the interview|Complaint narrative chat/i);
    await expect(page.locator('#chat-context-card')).toBeVisible();
    await expect(page.locator('#chat-context-summary')).toContainText(/did:key:handoff-demo/i);
    await expect(page.locator('#chat-context-summary')).toContainText(/Jordan Example alleges retaliation/i);
    await expect(page.locator('#chat-context-prefill')).toContainText(/Prepared mediator prompt/i);
    await expect(page.locator('#chat-context-return-link')).toHaveAttribute('href', /\/workspace\?target_tab=review/);
    await expect(page.locator('#chat-form input')).toHaveValue(/Mediator, help turn this into testimony-ready narrative/i);
    await expect(page.locator('[aria-label="Chat next steps"]')).toBeVisible();
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

  test('chat next-step actions preserve complaint context across workflow handoffs', async ({ page }) => {
    const handoffUrl = '/chat?source=workspace'
      + '&user_id=did:key:chat-step-demo'
      + '&case_synopsis=Jordan%20Example%20needs%20causation%20support%20before%20drafting.'
      + '&prefill_message=Help%20organize%20the%20timeline%20and%20missing%20proof.'
      + '&return_to=%2Fworkspace%3Ftarget_tab%3Dreview';

    await page.goto(handoffUrl);
    await expect(page.locator('[aria-label="Chat next steps"]')).toBeVisible();
    await page.locator('#chat-open-profile').click();
    await expect(page).toHaveURL(/\/profile\?/);
    await expect(page.locator('#profile-context-card')).toBeVisible();
    await expect(page.locator('#profile-context-summary')).toContainText(/did:key:chat-step-demo/);
    await expect(page.locator('#profile-open-results')).toHaveAttribute('href', /user_id=did%3Akey%3Achat-step-demo/);
    await expect(page.locator('#profile-open-trace')).toHaveAttribute('href', /user_id=did%3Akey%3Achat-step-demo/);
    await page.locator('#profile-open-results').click();
    await expect(page).toHaveURL(/\/results\?/);
    await expect(page.locator('#results-context-card')).toBeVisible();
    await expect(page.locator('#results-context-summary')).toContainText(/did:key:chat-step-demo/);
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
    await page.addInitScript(() => {
      window.localStorage.setItem('complaintGenerator.did', 'did:key:workspace-handoff-demo');
    });

    await page.goto('/workspace');
    await page.waitForFunction(
      () => document.getElementById('sdk-server-info').innerText.includes('complaint-workspace-mcp'),
    );

    await page.locator('#intake-party_name').fill('Jordan Example');
    await page.locator('#intake-opposing_party').fill('Acme Corporation');
    await page.locator('#intake-protected_activity').fill('Reported discrimination to HR');
    await page.locator('#intake-adverse_action').fill('Termination two days later');
    await page.locator('#intake-timeline').fill('Complaint on March 8, termination on March 10');
    await page.locator('#intake-harm').fill('Lost wages and emotional distress');
    await page.locator('#save-intake-button').click();
    await expect(page.locator('#workspace-status')).toContainText(/Intake answers saved/i);

    await page.locator('#case-synopsis').fill(
      'Jordan Example alleges retaliation after reporting discrimination to HR, with the clearest current support on timeline and the main remaining need being corroboration.',
    );
    await page.locator('#save-synopsis-button').click();
    await expect(page.locator('#workspace-status')).toContainText(/Shared case synopsis saved/i);

    await expect(page.locator('#handoff-chat-summary')).toContainText(/Open Chat/i);
    await expect(page.locator('#handoff-review-summary')).toContainText(/Open the review dashboard/i);
    await expect(page.locator('#handoff-builder-summary')).toContainText(/Open the formal builder/i);
    await expect(page.locator('#handoff-chat-button')).toHaveAttribute('href', /\/chat\?/);
    await expect(page.locator('#handoff-chat-button')).toHaveAttribute('href', /source=workspace/);
    await expect(page.locator('#handoff-chat-button')).toHaveAttribute('href', /user_id=did%3Akey%3Aworkspace-handoff-demo/);
    await expect(page.locator('#handoff-chat-button')).toHaveAttribute('href', /prefill_message=/);
    await expect(page.locator('#handoff-chat-button')).toHaveAttribute('href', /return_to=%2Fworkspace/);
    await expect(page.locator('#handoff-review-button')).toHaveAttribute('href', /\/claim-support-review\?/);
    await expect(page.locator('#handoff-review-button')).toHaveAttribute('href', /workspace_user_id=did%3Akey%3Aworkspace-handoff-demo/);
    await expect(page.locator('#handoff-builder-button')).toHaveAttribute('href', /\/document\?/);
    await expect(page.locator('#handoff-builder-button')).toHaveAttribute('href', /user_id=did%3Akey%3Aworkspace-handoff-demo/);

    const screenshotPath = testInfo.outputPath('workspace-handoffs-overview.png');
    await page.locator('[aria-label="Connected surface handoffs"]').screenshot({ path: screenshotPath });
    await testInfo.attach('workspace-handoffs-overview', {
      path: screenshotPath,
      contentType: 'image/png',
    });
  });

  test('document and dashboard remain mutually navigable as one website', async ({ page }) => {
    await page.goto('/document');
    await page.locator('a[href="/claim-support-review"]').first().click();
    await expect(page).toHaveURL(/\/claim-support-review/);
    await expect(page.locator('body')).toContainText(/Operator Review Surface/i);

    await page.locator('a[href="/document"]').first().click();
    await expect(page).toHaveURL(/\/document/);
    await expect(page.locator('body')).toContainText(/Formal Complaint Builder/i);
  });

  test('editor and sdk dashboards are part of the same unified navigation experience', async ({ page }) => {
    await page.goto('/mlwysiwyg');
    await expect(page.locator('[data-surface-nav="primary"]')).toBeVisible();
    await expect(page.locator('#draft-preview')).toContainText(/Retaliation Complaint Draft/i);
    await page.locator('a[href="/workspace"]').first().click();

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
    await page.goto('/claim-support-review');
    await expect(page.locator('[aria-label="Review next steps"]')).toBeVisible();
    await expect(page.locator('#review-open-workspace-link')).toBeVisible();
    await expect(page.locator('#review-open-chat-link')).toBeVisible();
    await expect(page.locator('#review-open-builder-link')).toBeVisible();
    await expect(page.locator('#review-open-trace-link')).toBeVisible();
    await page.locator('#review-open-builder-link').click();
    await expect(page).toHaveURL(/\/document/);
  });

  test('dashboard hub and every mounted shell route are reachable in the JS stub surface', async ({ page }) => {
    await page.goto('/dashboards');
    await expect(page.locator('body')).toContainText(/Unified Dashboard Hub/i);

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
    await page.addInitScript(() => {
      window.localStorage.setItem('complaintGenerator.did', 'did:key:nav-workspace-flow');
    });
    await page.goto('/workspace');
    await page.getByRole('button', { name: 'Draft', exact: true }).click();
    await page.locator('#reset-session-button').click();
    await expect(page.locator('#workspace-status')).toContainText(/reset to a clean state/i);
    await page.getByRole('button', { name: 'Intake', exact: true }).click();
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
    await expect(page.locator('#quick-action-grid')).toContainText(/Update the mediator brief/i);
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
    await page.locator('#quick-action-grid').getByRole('button', { name: 'Open Review' }).click();
    await expect(page.locator('#workspace-status')).toContainText(/Opened Review/i);
    await expect(page.locator('#support-grid')).toBeVisible();
    await page.locator('#shortcut-intake-button').click();

    await page.locator('#intake-party_name').fill('Jane Doe');
    await page.locator('#intake-opposing_party').fill('Acme Corporation');
    await page.locator('#intake-protected_activity').fill('Reported discrimination to HR');
    await page.locator('#intake-adverse_action').fill('Termination two days later');
    await page.locator('#intake-timeline').fill('Complaint on March 8, termination on March 10');
    await page.locator('#intake-harm').fill('Lost wages and benefits');
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
    await expect(page.locator('#chat-context-prefill')).toContainText(/Prepared mediator prompt/i);
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

    await page.getByRole('button', { name: 'Draft', exact: true }).click();
    await page.locator('#draft-title').fill('Jane Doe v. Acme Corporation Complaint');
    await page.locator('#requested-relief').fill('Back pay\nInjunctive relief');
    await page.locator('#generate-draft-button').click();

    await expect(page.locator('#workspace-status')).toContainText(/Complaint draft generated through the llm_router formal complaint path/i);
    await expect(page.locator('#draft-preview')).toContainText(/Jane Doe brings this retaliation complaint against Acme Corporation/i);
    await expect(page.locator('#feature-walkthrough-list')).toContainText(/A complaint draft exists and can be revised directly/i);
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
    await expect(page.locator('#ux-review-stage-findings')).toContainText(/The evidence step should explain which documents help prove causation before users are asked to upload or summarize proof/i);
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
    await expect(page.locator('#homepage-resume-link')).toHaveAttribute('href', '/claim-support-review');
    await expect(page.locator('#homepage-open-workspace')).toHaveAttribute('href', '/claim-support-review');
    await expect(page.locator('#homepage-open-workspace')).toContainText(/Review Claim Support|Review Support First/i);
    await expect(page.locator('#homepage-next-step')).toContainText(/Inspect missing claim elements/i);
    await expect(page.locator('#homepage-complaint-readiness-summary')).toContainText(/Still building the record|Ready for first draft|Draft in progress/i);

    for (const path of ['/home', '/chat', '/profile', '/results', '/document', '/claim-support-review', '/mlwysiwyg', '/document/optimization-trace', '/ipfs-datasets/sdk-playground']) {
      await page.goto(path);
      await expect(page.locator('#cg-app-shell')).toBeVisible();
      await expect(page.locator('#cg-app-shell-did')).toContainText(cachedDid);
      await expect(page.locator('#cg-app-shell-intake-count')).toHaveText('6');
      await expect(page.locator('#cg-app-shell-supported-count')).toHaveText('5');
      await expect(page.locator('#cg-app-shell-complaint-readiness')).toContainText(/Not ready to draft|Still building the record|Ready for first draft|Draft in progress/i);
      await expect(page.locator('#cg-app-shell-complaint-readiness')).toContainText(/Answered intake:/i);
      await expect(page.locator('#cg-app-shell a[href="/workspace"]').first()).toBeVisible();
      await expect(page.locator('#cg-app-shell a[href="/document"]').first()).toBeVisible();
      await expect(page.locator('#cg-app-shell a[href="/claim-support-review"]').first()).toBeVisible();
    }
  });
});
