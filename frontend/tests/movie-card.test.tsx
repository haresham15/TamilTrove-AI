import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { AppProvider } from "@/components/app-provider";
import { MovieCard } from "@/components/movie-card";
import { demoSearch } from "@/lib/demo-search";

vi.mock("next/image", () => ({
  default: ({
    fill,
    priority,
    unoptimized,
    src,
    alt,
  }: React.ImgHTMLAttributes<HTMLImageElement> & {
    fill?: boolean;
    priority?: boolean;
    unoptimized?: boolean;
  }) => {
    void fill;
    void priority;
    void unoptimized;
    return <span role="img" aria-label={alt} data-src={String(src)} />;
  },
}));

describe("MovieCard", () => {
  it("renders metadata, grounded explanation, and keyboard-operable actions", () => {
    const movie = demoSearch({
      query: "one night prisoner chase",
      page_size: 1,
    }).results[0];
    render(
      <AppProvider>
        <MovieCard movie={movie} />
      </AppProvider>,
    );
    expect(
      screen.getByRole("heading", { name: movie.title }),
    ).toBeInTheDocument();
    expect(screen.getByText("Why it fits")).toBeInTheDocument();
    const watchlist = screen.getByRole("button", { name: /watchlist/i });
    fireEvent.click(watchlist);
    expect(watchlist).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByText("Saved")).toBeInTheDocument();
    fireEvent.change(
      screen.getByRole("combobox", { name: `Rate ${movie.title}` }),
      { target: { value: "4" } },
    );
    expect(
      screen.getByRole("combobox", { name: `Rate ${movie.title}` }),
    ).toHaveValue("4");
  });

  it("opens an accessible add-to-collection dialog", () => {
    const movie = demoSearch({ query: "courtroom injustice", page_size: 1 })
      .results[0];
    render(
      <AppProvider>
        <MovieCard movie={movie} />
      </AppProvider>,
    );
    fireEvent.click(
      screen.getByRole("button", { name: /add to a collection/i }),
    );
    expect(
      screen.getByRole("dialog", { name: `Add ${movie.title}` }),
    ).toHaveAttribute("open");
    expect(screen.getByLabelText("New private collection")).toBeInTheDocument();
  });
});
