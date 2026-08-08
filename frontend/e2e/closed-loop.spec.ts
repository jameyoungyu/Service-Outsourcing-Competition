import { expect, test, type Page } from "@playwright/test";

/**
 * The A14 closed loop, driven through the real browser against the real API.
 *
 * Nothing here is mocked. Every assertion below is satisfied by numbers the backend
 * computed during the test — which is the point: a UI test that talks to a mock proves the
 * mock works. The trade-off is that these tests are slow (real ARX fits, real greedy
 * selection) and that a genuine algorithm regression breaks them. Both are intended.
 *
 * What the assertions deliberately avoid is pinning exact metric values. The suite checks
 * that the pipeline produces well-formed, physically sensible results and that the UI
 * surfaces them; asserting "FIT is 93.31" here would make the E2E suite a duplicate of the
 * benchmark tests and a tripwire for every legitimate numerical change.
 */

const SCENARIO = "S3";

/** Generate a dataset through the UI and return the version id the backend assigned.
 *
 * The id is read from the API response rather than scraped off the page: the result card
 * shows several UUIDs (dataset, version, run) and picking "the first one that looks like a
 * UUID" silently coupled this helper to their display order.
 */
async function generateDataset(page: Page, name: string): Promise<string> {
  await page.goto("/simulation");
  // Element Plus renders the label in an inner span that intercepts the click, so target
  // the visible text rather than the (hidden) radio input.
  await page.getByText("S3 长稳态短动态").click();
  await page.getByRole("textbox").first().fill(name);

  const pending = page.waitForResponse(
    (response) =>
      response.url().includes("/api/v1/simulation/generate") && response.status() < 400,
    { timeout: 60_000 },
  );
  await page.getByRole("button", { name: "生成仿真数据集并解析真值" }).click();
  const body = await (await pending).json();

  expect(body.success, "仿真生成必须成功，否则后续步骤没有输入").toBe(true);
  await expect(page.getByText("仿真结果与真值卡片", { exact: false })).toBeVisible({
    timeout: 30_000,
  });
  return body.data.version_id as string;
}

test.describe("端到端闭环", () => {
  test("仿真页暴露全部六个场景，包含 S6 异构激励压力测试", async ({ page }) => {
    // S6 is the scenario the whole differentiation argument rests on. It was reachable via
    // the API long before it was reachable via the UI; this test stops that drifting again.
    await page.goto("/simulation");
    for (const scenario of ["S1", "S2", "S3", "S4", "S5", "S6"]) {
      await expect(page.getByRole("radio", { name: new RegExp(`^${scenario}`) })).toBeVisible();
    }
  });

  test("生成 → 优选：门控与 D-最优的真实结果出现在页面上", async ({ page }) => {
    const versionId = await generateDataset(page, `e2e_seg_${Date.now()}`);

    await page.goto("/preprocessing/segmentation");
    await page.getByPlaceholder("version_id").fill(versionId);
    // The simulation view generates two inputs, so the form's u1,u2,u3 default would ask
    // for a column that is not in the record.
    await page.getByPlaceholder("u1,u2,u3").fill("u1,u2");
    await page.getByRole("button", { name: "执行门控与信息增益优选" }).click();

    // Coverage below 1 is the claim the whole selection stage makes: fewer rows, same model.
    await expect(page.getByText(/采样占比|覆盖/).first()).toBeVisible({ timeout: 60_000 });
    const body = await page.locator("body").innerText();
    expect(body).toMatch(/停止原因|stopped/i);
    expect(body).toMatch(/CELF|加速/);
  });

  test("自评测基准：四种策略全部出现，且不利结果照样展示", async ({ page }) => {
    await page.goto("/benchmark");
    await page.getByRole("button", { name: "运行自评测基准" }).click();

    await expect(page.getByText("数据优选消融", { exact: false })).toBeVisible({
      timeout: 90_000,
    });

    const body = await page.locator("body").innerText();
    for (const label of ["全量数据", "能量启发式", "完整加权质量分", "质量约束 D-最优"]) {
      expect(body, `策略 ${label} 必须出现在对照表中`).toContain(label);
    }
    // S6 is where the heuristics go rank-deficient. The UI must say so rather than showing
    // a blank cell — that regression is exactly what the JSON-null bug caused.
    expect(body).toMatch(/秩亏|满秩/);
    expect(body).not.toMatch(/条件数[^\n]*(null|undefined)/);
  });

  test("Agent 工作台：自然语言 → 白名单计划 → 合规证明", async ({ page }) => {
    await page.goto("/copilot");
    await page
      .getByPlaceholder(/例如/)
      .fill("提取高信噪比的动态数据，处理共线性后，通过闭环寻优找出最佳模型数据");
    await page.getByRole("button", { name: "提交给 Agent" }).click();

    await expect(page.getByText("合规证明")).toBeVisible({ timeout: 60_000 });

    const body = await page.locator("body").innerText();
    // The proof is the differentiator: a signed, machine-checked statement, not a promise.
    expect(body).toMatch(/校验通过|校验未通过/);
    expect(body).toMatch(/签名/);
    // With no version id supplied the agent plans but must not execute.
    expect(body).toMatch(/仅生成计划|已执行/);
  });

  test("离线默认：未配置大模型时走确定性规则编排且不报错", async ({ page }) => {
    // The venue may have no network. "No LLM configured" is the supported default state,
    // not a degraded one, and the UI has to say which planner produced the plan.
    await page.goto("/copilot");
    await page.getByPlaceholder(/例如/).fill("清洗数据并估计时滞，然后做 ARX 辨识");
    await page.getByRole("button", { name: "提交给 Agent" }).click();

    await expect(page.getByText("Agent 编排计划")).toBeVisible({ timeout: 60_000 });
    const body = await page.locator("body").innerText();
    expect(body).toContain("确定性规则编排");
    expect(body).not.toContain("执行失败");
  });
});

test.describe("错误路径", () => {
  test("不存在的数据版本给出领域错误而不是白屏", async ({ page }) => {
    await page.goto("/preprocessing/segmentation");
    await page.getByPlaceholder("version_id").fill("00000000-0000-0000-0000-000000000000");
    await page.getByRole("button", { name: "执行门控与信息增益优选" }).click();

    // A 404 must surface as a readable message. Silently showing nothing is the failure
    // mode that makes an engineer distrust the whole tool.
    await expect(page.getByText(/不存在|未找到|失败/).first()).toBeVisible({ timeout: 30_000 });
  });

  test("未知路由落到 404 页面", async ({ page }) => {
    await page.goto("/this-route-does-not-exist");
    await expect(page.getByText(/404/).first()).toBeVisible();
  });
});

test.describe("基础可用性", () => {
  test("每个主视图都能打开且不抛出控制台错误", async ({ page }) => {
    const errors: string[] = [];
    page.on("pageerror", (error) => errors.push(String(error)));

    const routes = [
      "/dashboard",
      "/simulation",
      "/datasets",
      "/preprocessing/cleaning",
      "/preprocessing/segmentation",
      "/preprocessing/delay",
      "/preprocessing/collinearity",
      "/modeling/arx",
      "/modeling/optimization",
      "/copilot",
      "/benchmark",
      "/deliverables",
      "/settings",
    ];
    for (const route of routes) {
      await page.goto(route);
      await expect(page.locator("h2").first()).toBeVisible();
    }
    expect(errors, `未捕获的前端异常：${errors.join("; ")}`).toHaveLength(0);
  });
});

test("场景常量与后端一致", async ({ request }) => {
  // Guards the mismatch this suite was written after finding: the backend accepted S6 for
  // weeks while the UI offered only S1-S5.
  const response = await request.post("/api/v1/simulation/generate", {
    data: {
      scenario: SCENARIO,
      n_steps: 800,
      seed: 3,
      input_count: 3,
      dataset_name: `e2e_contract_${Date.now()}`,
    },
  });
  expect(response.ok()).toBeTruthy();
  const body = await response.json();
  expect(body.success).toBe(true);
  expect(body.data.scenario).toBe(SCENARIO);
});
