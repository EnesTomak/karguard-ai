import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it } from "vitest";

import Layout from "./Layout";

describe("Layout", () => {
  it("renders navbar brand and outlet content", () => {
    render(
      <MemoryRouter initialEntries={["/"]}>
        <Routes>
          <Route element={<Layout />}>
            <Route path="/" element={<div>Outlet Content</div>} />
          </Route>
        </Routes>
      </MemoryRouter>
    );

    expect(screen.getByText(/Gemini \+ RAG \+ MCP/i)).toBeInTheDocument();
    expect(screen.getByText("Outlet Content")).toBeInTheDocument();
  });
});
