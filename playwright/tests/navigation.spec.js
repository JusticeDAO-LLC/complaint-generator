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
      ['/wysiwyg', /Complaint Editor Workshop/i],
      ['/mlwysiwyg', /Complaint Editor Workshop/i],
      ['/MLWYSIWYG', /Complaint Editor Workshop/i],
      ['/document', /Formal Complaint Builder/i],
      ['/claim-support-review', /Operator Review Surface/i],
      ['/document/optimization-trace', /Optimization Trace Viewer/i],
      ['/ipfs-datasets/sdk-playground', /SDK Playground Preview|SDK Playground/i],
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
    await expect(page.locator('a[href="/mlwysiwyg"]').first()).toBeVisible();
    await expect(page.locator('a[href="/ipfs-datasets/sdk-playground"]').first()).toBeVisible();

    await page.goto('/claim-support-review');
    await expect(page.locator('a[href="/document"]').first()).toBeVisible();
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
});
