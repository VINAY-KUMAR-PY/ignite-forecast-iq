import { expect, test } from "@playwright/test";

test.use({ viewport: { width: 375, height: 812 } });

test("landing theme toggle stays visible and persists across landing and dashboard routes", async ({
  page,
}) => {
  await page.goto("/");
  await page.evaluate(() => localStorage.setItem("theme", "dark"));
  await page.reload();

  const landingToggle = page.getByRole("button", { name: "Switch to light mode" });
  await expect(landingToggle).toBeVisible();
  await expect(page.locator("html")).toHaveClass(/dark/);

  await landingToggle.click();
  await expect(page.getByRole("button", { name: "Switch to dark mode" })).toBeVisible();
  await expect(page.locator("html")).not.toHaveClass(/dark/);
  await expect.poll(() => page.evaluate(() => localStorage.getItem("theme"))).toBe("light");

  await page.locator("header").getByRole("link", { name: "Try Live Demo" }).click();
  await expect(page).toHaveURL(/\/app$/);
  await expect(page.locator("html")).not.toHaveClass(/dark/);
  await expect(page.getByRole("button", { name: "Switch to dark mode" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Restart judge workflow" })).toBeVisible();

  await page.locator('header a[href="/"]').click();
  await expect(page).toHaveURL(/\/$/);
  await expect(page.getByRole("button", { name: "Switch to dark mode" })).toBeVisible();
  await expect(page.locator("html")).not.toHaveClass(/dark/);
});

test("budget simulator contains wide planning tables on mobile", async ({ page }) => {
  await page.route("**/api/**", async (route) => route.abort());
  await page.goto("/app/simulator");
  await expect(page.getByRole("heading", { name: "Budget simulator" })).toBeVisible();
  await expect(page.getByTestId("automatic-allocation")).toBeVisible();

  const documentWidth = await page.evaluate(() => ({
    client: document.documentElement.clientWidth,
    scroll: document.body.scrollWidth,
  }));
  expect(documentWidth.scroll).toBeLessThanOrEqual(documentWidth.client);
});
