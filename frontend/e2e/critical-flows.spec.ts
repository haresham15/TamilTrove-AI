import { expect, test } from "@playwright/test";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const axePath = require.resolve("axe-core/axe.min.js");

interface AxeViolation {
  id: string;
  help: string;
  impact: "minor" | "moderate" | "serious" | "critical" | null;
}

test.beforeEach(async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
});

test.describe("V2 discovery", () => {
  test("searches in Tamil, applies a filter, and recovers with the offline catalog", async ({
    page,
  }) => {
    await page.goto("/");
    await expect(
      page.getByRole("heading", { name: /Describe the story/i }),
    ).toBeVisible();

    await page.getByRole("button", { name: /^Filters/ }).click();
    const filterDialog = page.getByRole("dialog", { name: "Search filters" });
    await expect(filterDialog).toBeVisible();
    await filterDialog.getByLabel("Drama", { exact: true }).check();
    await filterDialog.getByRole("button", { name: "Show matches" }).click();
    await expect(filterDialog).not.toBeVisible();

    await page
      .getByLabel("What are you in the mood for?")
      .fill("கிராம வாழ்க்கை பற்றிய மனதை தொடும் படம்");
    await page.getByRole("button", { name: "Discover" }).click();

    await expect(page.getByRole("heading", { name: /Matches for/ })).toBeVisible();
    await expect(page.getByText(/live service is offline/i)).toBeVisible();
    await expect(page.getByRole("heading", { name: "Kadaisi Vivasayi" })).toBeVisible();
    await expect(page.getByText("Why it fits").first()).toBeVisible();
  });

  test("supports keyboard-only entry, dialog dismissal, and result actions", async ({
    page,
  }) => {
    await page.goto("/");
    await page.keyboard.press("Tab");
    await expect(page.getByRole("link", { name: "Skip to main content" })).toBeFocused();
    await page.keyboard.press("Enter");
    await expect(page.locator("#main-content")).toBeFocused();

    await page.getByRole("button", { name: /^Filters/ }).focus();
    await page.keyboard.press("Enter");
    await expect(page.getByRole("dialog", { name: "Search filters" })).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(page.getByRole("dialog", { name: "Search filters" })).not.toBeVisible();

    const query = page.getByLabel("What are you in the mood for?");
    await query.fill("one night prisoner chase");
    await query.press("Enter");
    const kaithi = page.getByRole("article").filter({ hasText: "Kaithi" });
    await expect(kaithi).toBeVisible();
    await kaithi.getByRole("button", { name: "Watchlist" }).click();
    await expect(kaithi.getByRole("button", { name: "Saved" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
  });

  test("has no serious or critical automated accessibility violations", async ({
    page,
  }) => {
    await page.goto("/");
    await expect(page.getByRole("main")).toBeVisible();
    await page.addScriptTag({ path: axePath });
    const results = await page.evaluate(async () => {
      const axe = (
        window as unknown as Window & {
          axe: {
            run: (options: { runOnly: string[] }) => Promise<{
              violations: AxeViolation[];
            }>;
          };
        }
      ).axe;
      return axe.run({
        runOnly: ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"],
      });
    });
    const blocking = results.violations.filter((violation) =>
      violation.impact === "serious" || violation.impact === "critical",
    );
    expect(
      blocking,
      blocking
        .map((violation) => `${violation.id}: ${violation.help}`)
        .join("\n"),
    ).toEqual([]);
  });
});
