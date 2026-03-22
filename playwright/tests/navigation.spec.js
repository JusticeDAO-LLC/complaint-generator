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

  test('all routed complaint surfaces load and expose expected navigation affordances', async ({ page }) => {
    const routes = [
      ['/', /Lex Publicus Complaint Generator/i],
      ['/home', /Lex Publicus Chat App/i],
      ['/chat', /Lex Publicus Chat App/i],
      ['/profile', /Profile Data/i],
      ['/results', /Profile Data/i],
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
    await expect(page.locator('a[href="/claim-support-review"]').first()).toBeVisible();
    await expect(page.locator('a[href="/document"]').first()).toBeVisible();

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
    await page.goto('/workspace');

    await expect(page.locator('#workspace-status')).toContainText(/Workspace synchronized/i);
    await expect(page.locator('#sdk-server-info')).toContainText(/complaint-workspace-mcp/i);
    await expect(page.locator('#tool-list')).toContainText(/complaint.generate_complaint/i);

    await page.locator('#intake-party_name').fill('Jane Doe');
    await page.locator('#intake-opposing_party').fill('Acme Corporation');
    await page.locator('#intake-protected_activity').fill('Reported discrimination to HR');
    await page.locator('#intake-adverse_action').fill('Termination two days later');
    await page.locator('#intake-timeline').fill('Complaint on March 8, termination on March 10');
    await page.locator('#intake-harm').fill('Lost wages and benefits');
    await page.locator('#save-intake-button').click();

    await expect(page.locator('#workspace-status')).toContainText(/Intake answers saved/i);
    await expect(page.locator('#next-question-label')).toContainText(/Intake complete/i);

    await page.getByRole('button', { name: 'Evidence' }).click();
    await page.locator('#evidence-kind').selectOption('document');
    await page.locator('#evidence-claim-element').selectOption('causation');
    await page.locator('#evidence-title').fill('Termination email');
    await page.locator('#evidence-source').fill('Inbox export');
    await page.locator('#evidence-content').fill('The termination followed the HR complaint within two days.');
    await page.locator('#save-evidence-button').click();

    await expect(page.locator('#workspace-status')).toContainText(/Evidence saved and support review refreshed/i);
    await expect(page.locator('#evidence-list')).toContainText(/Termination email/i);

    await page.getByRole('button', { name: 'Draft' }).click();
    await page.locator('#draft-title').fill('Jane Doe v. Acme Corporation Complaint');
    await page.locator('#requested-relief').fill('Back pay\nInjunctive relief');
    await page.locator('#generate-draft-button').click();

    await expect(page.locator('#workspace-status')).toContainText(/Complaint draft generated from intake and evidence/i);
    await expect(page.locator('#draft-preview')).toContainText(/Jane Doe brings this retaliation complaint against Acme Corporation/i);

    await page.getByRole('button', { name: 'CLI + MCP' }).click();
    await expect(page.locator('body')).toContainText(/complaint-workspace session/i);
    await expect(page.locator('body')).toContainText(/complaint-mcp-server/i);
    await expect(page.locator('#tool-list')).toContainText(/complaint.review_case/i);
  });
});
