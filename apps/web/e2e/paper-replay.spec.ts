import { test, expect } from "@playwright/test";

test("approved historical strategy creates a durable paper account and emergency stop retains holdings", async ({
  page,
  request,
}) => {
  const created = await request.post("/api/strategy-drafts", {
    data: {
      specification: {
        name: "Paper replay browser test",
        description: "Daily AAPL SMA crossover",
        symbol: "AAPL",
        timeframe: "1Day",
        indicator: "SMA",
        fast: 2,
        slow: 3,
        direction: "long_only",
        entry: "fast_crosses_above_slow",
        exit: "fast_crosses_below_slow",
      },
    },
  });
  expect(created.status()).toBe(201);
  const draft = await created.json();
  expect(
    (
      await request.post(`/api/strategy-drafts/${draft.id}/approve`, {
        data: {},
      })
    ).status(),
  ).toBe(200);
  const simulated = await request.post(
    `/api/strategy-drafts/${draft.id}/backtests`,
    { data: {} },
  );
  expect(simulated.status()).toBe(201);
  const run = await simulated.json();
  await page.goto("/");
  await page
    .getByRole("combobox", { name: "Saved runs", exact: true })
    .selectOption(run.id);
  const panel = page.getByRole("region", { name: "Paper portfolio replay" });
  const createButton = panel.getByRole("button", {
    name: "Create virtual replay account",
  });
  if (!(await createButton.isVisible()))
    await panel
      .getByText("Limits for a new virtual account", { exact: true })
      .click();
  await createButton.click();
  await expect(panel.getByTestId("replay-status")).toHaveText("paused");
  await panel.getByRole("button", { name: "Advance 100 bars" }).click();
  await expect(
    panel.getByRole("progressbar", { name: "Replay progress" }),
  ).toHaveAttribute("value", "100");
  expect(await panel.locator("tbody tr").count()).toBeGreaterThan(0);
  const id = await panel
    .getByRole("combobox", { name: "Saved replay accounts" })
    .inputValue();
  const before = await (await request.get(`/api/paper/sessions/${id}`)).json();
  await panel.getByRole("button", { name: "Start automatic replay" }).click();
  await expect(panel.getByTestId("replay-status")).toHaveText("running");
  await panel.getByRole("button", { name: "Pause replay" }).click();
  await expect(panel.getByTestId("replay-status")).toHaveText("paused");
  const paused = await (await request.get(`/api/paper/sessions/${id}`)).json();
  expect(paused.cursor).toBeGreaterThanOrEqual(before.cursor);
  await panel.getByRole("button", { name: "Emergency stop" }).click();
  await expect(panel.getByTestId("replay-status")).toHaveText("stopped");
  const stopped = await (await request.get(`/api/paper/sessions/${id}`)).json();
  expect(stopped.quantity).toBe(paused.quantity);
  expect(stopped.orders).toEqual(paused.orders);
  await expect(
    panel.getByRole("button", { name: "Advance 100 bars" }),
  ).toBeDisabled();
  await page.reload();
  await panel
    .getByRole("combobox", { name: "Saved replay accounts" })
    .selectOption(id);
  await expect(panel.getByTestId("replay-status")).toHaveText("stopped");
});
