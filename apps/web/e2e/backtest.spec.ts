import { test, expect } from "@playwright/test";

test("configure, run, inspect, export, and reload a persisted historical backtest", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto("/");
  await expect(
    page.getByRole("heading", {
      name: "Test an idea. Understand the trade-offs.",
    }),
  ).toBeVisible();
  await expect(page.getByText("Your research starts here")).toBeVisible();
  await page.getByLabel("Fast SMA (bars)").fill("10");
  await page.getByLabel("Slow SMA (bars)").fill("30");
  await page.getByRole("button", { name: "Run backtest" }).click();
  await expect(
    page.getByRole("heading", { name: "AAPL · Research results" }),
  ).toBeVisible();
  await expect(page.getByRole("table")).toBeVisible();
  expect(await page.locator("tbody tr").count()).toBeGreaterThan(0);
  await expect(
    page.getByRole("img", {
      name: "Strategy and buy-and-hold equity over time",
    }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Drawdown", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Portfolio drawdown" }),
  ).toBeVisible();
  const downloaded = page.waitForEvent("download");
  await page.getByRole("button", { name: "Export run" }).click();
  expect((await downloaded).suggestedFilename()).toMatch(
    /^quantpilot-.*\.json$/,
  );
  const saved = await page
    .getByRole("combobox", { name: "Saved runs", exact: true })
    .inputValue();
  await page.reload();
  await page
    .getByRole("combobox", { name: "Saved runs", exact: true })
    .selectOption(saved);
  await expect(
    page.getByRole("heading", { name: "AAPL · Research results" }),
  ).toBeVisible();
  await expect(page.getByLabel("Fast SMA (bars)")).toHaveValue("10");
  expect(errors).toEqual([]);
});

test("invalid periods show an error without creating performance", async ({
  page,
}) => {
  await page.goto("/");
  await page.getByLabel("Fast SMA (bars)").fill("50");
  await page.getByLabel("Slow SMA (bars)").fill("20");
  await page.getByRole("button", { name: "Run backtest" }).click();
  await expect(page.getByRole("alert").filter({ hasText: "Invalid configuration" })).toContainText("Invalid configuration");
  await expect(page.getByText("Your research starts here")).toBeVisible();
});

test("dashboard remains usable on a narrow viewport", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  expect(
    await page.evaluate(() => document.documentElement.scrollWidth),
  ).toBeLessThanOrEqual(390);
  await page.getByRole("button", { name: "Run backtest" }).click();
  await expect(
    page.getByRole("heading", { name: "AAPL · Research results" }),
  ).toBeVisible();
  expect(
    await page.evaluate(() => document.documentElement.scrollWidth),
  ).toBeLessThanOrEqual(390);
});
