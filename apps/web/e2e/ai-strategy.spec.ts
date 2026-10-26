import { test, expect } from "@playwright/test";

const specification = {
  name: "AAPL crossover browser fixture",
  description: "Daily SMA 20/50 crossover.",
  symbol: "AAPL",
  timeframe: "1Day",
  indicator: "SMA",
  fast: 20,
  slow: 50,
  entry: "fast_crosses_above_slow",
  exit: "fast_crosses_below_slow",
  direction: "long_only",
};

test("mocked AI draft can be reviewed, approved, backtested and edited as a new version", async ({
  page,
  request,
}) => {
  // Stub generation only; drafts, approvals, versioning and backtesting use the real API/DB.
  await page.route("**/api/strategy-drafts/generate", async (route) => {
    const response = await request.post("/api/strategy-drafts", {
      data: { specification },
    });
    expect(response.status()).toBe(201);
    const draft = await response.json();
    await route.fulfill({
      json: {
        status: "supported",
        explanation: "Mocked provider response.",
        draft,
      },
    });
  });
  await page.goto("/");
  await page.getByRole("button", { name: "Generate strategy draft" }).click();
  await expect(
    page.getByRole("heading", { name: "Review strategy rules" }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Run backtest", exact: true }),
  ).toBeDisabled();
  await expect(
    page.getByRole("button", { name: "Backtest approved version" }),
  ).toBeDisabled();
  await page.getByRole("button", { name: "Approve for backtesting" }).click();
  await expect(
    page.getByRole("button", { name: "Version approved", exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Backtest approved version" }).click();
  await expect(
    page.getByRole("heading", { name: "AAPL · Research results" }),
  ).toBeVisible();
  const approvedId = await page
    .getByLabel("Saved strategy versions")
    .inputValue();
  await page.getByLabel("Draft fast SMA").fill("10");
  await expect(
    page.getByRole("button", { name: "Backtest approved version" }),
  ).toBeDisabled();
  await page.getByRole("button", { name: "Save as new draft version" }).click();
  await expect(
    page.getByRole("button", { name: "Approve for backtesting" }),
  ).toBeEnabled();
  await expect(
    page.getByRole("button", { name: "Backtest approved version" }),
  ).toBeDisabled();
  expect(
    await page.getByLabel("Saved strategy versions").inputValue(),
  ).not.toBe(approvedId);
  await page.getByLabel("Saved strategy versions").selectOption(approvedId);
  await expect(page.getByLabel("Draft fast SMA")).toHaveValue("20");
  await expect(
    page.getByRole("button", { name: "Version approved", exact: true }),
  ).toBeVisible();
  await page.reload();
  await page.getByLabel("Saved strategy versions").selectOption(approvedId);
  await expect(page.getByLabel("Draft fast SMA")).toHaveValue("20");
  await page
    .getByRole("button", { name: "Return to manual backtesting" })
    .click();
  await expect(
    page.getByRole("button", { name: "Run backtest", exact: true }),
  ).toBeEnabled();
  await expect(
    page.getByRole("heading", { name: "Review strategy rules" }),
  ).toHaveCount(0);
});

test("unsupported AI output asks for clarification without offering approval", async ({
  page,
}) => {
  await page.route("**/api/strategy-drafts/generate", (route) =>
    route.fulfill({
      json: {
        status: "unsupported",
        explanation: "RSI is not supported. Specify a daily SMA crossover.",
        draft: null,
      },
    }),
  );
  await page.goto("/");
  await page
    .getByLabel("Describe a strategy")
    .fill("Buy AAPL when its RSI is below 30.");
  await page.getByRole("button", { name: "Generate strategy draft" }).click();
  await expect(
    page.getByText("RSI is not supported. Specify a daily SMA crossover."),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Approve for backtesting" }),
  ).toHaveCount(0);
  await expect(page.getByText("Your research starts here")).toBeVisible();
});

test("provider failure is shown without fabricating a strategy", async ({
  page,
}) => {
  await page.route("**/api/strategy-drafts/generate", (route) =>
    route.fulfill({
      status: 503,
      json: {
        detail:
          "AI is not configured. Set QUANTPILOT_AI_API_KEY securely on the server.",
      },
    }),
  );
  await page.goto("/");
  await page.getByRole("button", { name: "Generate strategy draft" }).click();
  await expect(
    page.getByRole("alert").filter({ hasText: "AI is not configured" }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Review strategy rules" }),
  ).toHaveCount(0);
});
