import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { MemoryRouter } from "react-router-dom";
import { QueryClientProvider } from "@tanstack/react-query";
import App from "../App";
import { queryClient } from "../lib/queryClient";

describe("App shell", () => {
  it("renders header", () => {
    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter>
          <App />
        </MemoryRouter>
      </QueryClientProvider>,
    );
    expect(screen.getByText(/SPVX-Lite Operations Dashboard/i)).toBeInTheDocument();
  });
});
