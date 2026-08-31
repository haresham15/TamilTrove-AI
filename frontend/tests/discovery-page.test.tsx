import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { AppProvider } from "@/components/app-provider";
import { DiscoveryPage } from "@/components/discovery-page";
import { demoSearch } from "@/lib/demo-search";

const { search } = vi.hoisted(() => ({ search: vi.fn() }));
vi.mock("@/lib/api-client", async (importOriginal) => {
  const original = await importOriginal<typeof import("@/lib/api-client")>();
  return {
    ...original,
    apiClient: {
      ...original.apiClient,
      profile: vi.fn().mockRejectedValue(new TypeError("offline")),
      search,
    },
  };
});

describe("DiscoveryPage", () => {
  it("submits a natural-language query and announces results", async () => {
    search.mockResolvedValueOnce({
      ...demoSearch({ query: "one night chase", page_size: 12 }),
      source: "api",
    });
    render(
      <AppProvider>
        <DiscoveryPage />
      </AppProvider>,
    );
    fireEvent.change(screen.getByLabelText("What are you in the mood for?"), {
      target: { value: "one night chase" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Discover" }));
    expect(screen.getByText("Searching the catalog")).toBeInTheDocument();
    await waitFor(() =>
      expect(
        screen.getByRole("heading", { name: /Matches for/ }),
      ).toBeInTheDocument(),
    );
    expect(search).toHaveBeenCalledWith(
      expect.objectContaining({ query: "one night chase" }),
      expect.any(AbortSignal),
      null,
    );
    expect(
      screen.getByText(/results shown for one night chase/),
    ).toBeInTheDocument();
  });

  it("shows a retryable server error without disguising it as demo data", async () => {
    const { ApiClientError } = await import("@/lib/api-client");
    search.mockRejectedValueOnce(
      new ApiClientError("Ranking service failed", { status: 503 }),
    );
    render(
      <AppProvider>
        <DiscoveryPage />
      </AppProvider>,
    );
    fireEvent.change(screen.getByLabelText("What are you in the mood for?"), {
      target: { value: "village drama" },
    });
    fireEvent.submit(
      screen.getByRole("button", { name: "Discover" }).closest("form")!,
    );
    await waitFor(() =>
      expect(screen.getByRole("alert")).toHaveTextContent(
        "Ranking service failed",
      ),
    );
    expect(
      screen.getByRole("button", { name: /Try again/ }),
    ).toBeInTheDocument();
  });

  it("opens the filter drawer and exposes labeled controls", () => {
    render(
      <AppProvider>
        <DiscoveryPage />
      </AppProvider>,
    );
    fireEvent.click(screen.getByRole("button", { name: /^Filters/ }));
    expect(
      screen.getByRole("dialog", { name: "Search filters" }),
    ).toHaveAttribute("open");
    expect(screen.getByLabelText("Released after")).toBeInTheDocument();
    expect(screen.getByLabelText("Prioritize hidden gems")).toBeInTheDocument();
  });
});
