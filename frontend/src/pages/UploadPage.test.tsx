import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";

import UploadPage from "./UploadPage";

describe("UploadPage", () => {
  it("renders hero and upload zone", () => {
    render(
      <MemoryRouter>
        <UploadPage />
      </MemoryRouter>
    );

    expect(screen.getByText(/BTK Akademi Hackathon 2026/i)).toBeInTheDocument();
    expect(screen.getByText(/CSV \/ Excel/i)).toBeInTheDocument();
  });

  it("shows selected file in the list", () => {
    const { container } = render(
      <MemoryRouter>
        <UploadPage />
      </MemoryRouter>
    );

    const input = container.querySelector('input[type="file"]');
    expect(input).not.toBeNull();
    fireEvent.change(input as HTMLInputElement, {
      target: {
        files: [new File(["sku,data"], "orders.csv", { type: "text/csv" })],
      },
    });

    expect(screen.getByText("orders.csv")).toBeInTheDocument();
  });
});
