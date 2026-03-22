const { test, expect } = require('@playwright/test');

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
      ['/mlwysiwyg', /Complaint Editor Workshop/i],
      ['/document', /Formal Complaint Builder/i],
      ['/claim-support-review', /Operator Review Surface/i],
      ['/document/optimization-trace', /Optimization Trace Viewer/i],
      ['/ipfs-datasets/sdk-playground', /SDK Playground Preview|SDK Playground/i],
      ['/dashboards', /Unified Dashboard Hub/i],
      ['/dashboards/ipfs-datasets/mcp', /IPFS Datasets MCP Dashboard/i],
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

  test('dashboard hub and shell routes are reachable in the JS stub surface', async ({ page }) => {
    await page.goto('/dashboards');
    await expect(page.locator('body')).toContainText(/Unified Dashboard Hub/i);
    await page.locator('a[href="/dashboards/ipfs-datasets/mcp"]').first().click();

    await expect(page).toHaveURL(/\/dashboards\/ipfs-datasets\/mcp/);
    await expect(page.locator('body')).toContainText(/IPFS Datasets MCP Dashboard/i);
    await expect(page.locator('iframe')).toBeVisible();
  });
});
