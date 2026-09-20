import { test, expect } from '@playwright/test';

test.describe('LexMetra Legal Metrology Verification Platform', () => {
  test('login, dashboard load, and browser back/forward navigation history', async ({ page }) => {
    // 1. Open the web app
    await page.goto('/');

    // If on landing page, click Sign In button
    const landingSignInBtn = page.getByRole('button', { name: /^sign in$/i }).first();
    if (await landingSignInBtn.isVisible()) {
      await landingSignInBtn.click();
      await page.waitForTimeout(500);
    }

    // On login view: use Instant Role Access "Field Inspector" button or form
    const fieldInspectorBtn = page.getByRole('button', { name: /field inspector/i });
    if (await fieldInspectorBtn.isVisible({ timeout: 4000 }).catch(() => false)) {
      await fieldInspectorBtn.click();
      await page.waitForTimeout(1000);
    } else {
      const usernameInput = page.getByPlaceholder(/inspector or admin/i);
      if (await usernameInput.isVisible({ timeout: 3000 }).catch(() => false)) {
        await usernameInput.fill('inspector');
        const passwordInput = page.locator('input[type="password"]').first();
        await passwordInput.fill('password123');
        const submitBtn = page.getByRole('button', { name: /sign in to lexmetra/i });
        await submitBtn.click();
        await page.waitForTimeout(1000);
      }
    }

    // 2. Verify we land on the platform dashboard (#home)
    await expect(page).toHaveURL(/#(home|regional)/, { timeout: 10000 });

    // 3. Test navigation tabs via desktop rail / navigation
    // Click Inspections (History) tab
    const historyLink = page.getByRole('button', { name: /inspections/i }).first();
    await expect(historyLink).toBeVisible();
    await historyLink.click();
    await page.waitForTimeout(600);
    expect(page.url()).toContain('#history');

    // 4. Test Scan Package tab
    const scanLink = page.getByRole('button', { name: /scan package/i }).first();
    await expect(scanLink).toBeVisible();
    await scanLink.click();
    await page.waitForTimeout(600);
    expect(page.url()).toContain('#scan');

    // 5. Test Native Browser BACK button
    await page.goBack();
    await page.waitForTimeout(600);
    // Verify browser back navigated to #history without exiting app
    expect(page.url()).toContain('#history');

    // 6. Test Native Browser FORWARD button
    await page.goForward();
    await page.waitForTimeout(600);
    // Verify browser forward navigated back to #scan
    expect(page.url()).toContain('#scan');

    // 7. Verify no 500 error banner on page
    const error500 = page.locator('text="Couldn\'t complete the check"');
    await expect(error500).not.toBeVisible();
  });

  test('responsive mobile viewport simulation', async ({ page }) => {
    // Set mobile viewport (iPhone 14 / standard 390x844)
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto('/#home');

    // Ensure layout adapts fluidly
    await expect(page.locator('body')).toBeVisible();

    // Check header renders responsively
    const header = page.locator('header').first();
    await expect(header).toBeVisible();
  });

  test('citizen portal public access and consumer verification', async ({ page }) => {
    await page.goto('/#customer');
    await expect(page.locator('text=/Citizen|Consumer|National Consumer Helpline/i').first()).toBeVisible({ timeout: 5000 });
    expect(page.url()).toContain('#customer');
  });
});
