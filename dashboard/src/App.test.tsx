import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import React from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { App } from "./App";
import { ErrorBoundary } from "./ErrorBoundary";

function jsonResponse(value: unknown, status = 200): Response {
  return new Response(JSON.stringify(value), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

it("renders the application shell and loading state", () => {
  vi.spyOn(globalThis, "fetch").mockImplementation(() => new Promise(() => undefined));
  render(<App />);
  expect(screen.getByText("AI Adaptive IoT Defense Platform")).toBeInTheDocument();
  expect(screen.getByText("Loading simulated telemetry...")).toBeInTheDocument();
});

it("renders useful empty states when the API returns no data", async () => {
  vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse({ items: [], total: 0, limit: 20, offset: 0 }));
  vi.mocked(fetch)
    .mockResolvedValueOnce(jsonResponse([]))
    .mockResolvedValueOnce(jsonResponse([]))
    .mockResolvedValueOnce(jsonResponse({ items: [], total: 0, limit: 20, offset: 0 }))
    .mockResolvedValueOnce(jsonResponse({ items: [], total: 0, limit: 20, offset: 0 }));

  render(<App />);

  expect(await screen.findByText("No simulated devices have reported yet.")).toBeInTheDocument();
  expect(screen.getByText("No simulated alerts.")).toBeInTheDocument();
  expect(screen.getByText("No audit events yet.")).toBeInTheDocument();
});

it("renders an API error state instead of a blank page", async () => {
  vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse({ detail: "down" }, 503));

  render(<App />);

  expect(await screen.findByRole("alert")).toHaveTextContent("API unavailable");
  expect(screen.getByText("AI Adaptive IoT Defense Platform")).toBeInTheDocument();
});

it("retry triggers another request", async () => {
  vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse({ detail: "down" }, 503));

  render(<App />);
  await screen.findByRole("alert");
  fireEvent.click(screen.getByRole("button", { name: "Retry dashboard data load" }));

  await waitFor(() => expect(fetch).toHaveBeenCalledTimes(8));
});

it("renders valid risk data", async () => {
  vi.spyOn(globalThis, "fetch")
    .mockResolvedValueOnce(
      jsonResponse([
        {
          device_id: "camera-01",
          device_type: "smart_camera",
          status: "active",
          risk: {
            risk_score: 92,
            level: "critical",
            created_at: "2026-08-06T00:00:00Z",
            reasons: [
              {
                signal: "traffic_spike",
                contribution: 20,
                explanation: "Traffic increased by 540% from baseline",
              },
            ],
          },
        },
      ]),
    )
    .mockResolvedValueOnce(jsonResponse([{ id: "a1", device_id: "camera-01", risk_score: 92 }]))
    .mockResolvedValueOnce(jsonResponse({ items: [], total: 0, limit: 20, offset: 0 }))
    .mockResolvedValueOnce(jsonResponse({ items: [], total: 0, limit: 20, offset: 0 }));

  render(<App />);

  expect(await screen.findByText("camera-01")).toBeInTheDocument();
  expect(screen.getByText("critical")).toBeInTheDocument();
  expect(screen.getByText("traffic_spike: +20")).toBeInTheDocument();
});

it("unexpected component errors reach the error boundary", () => {
  vi.spyOn(console, "error").mockImplementation(() => undefined);

  function Broken(): JSX.Element {
    throw new Error("boom");
  }

  render(
    <ErrorBoundary>
      <Broken />
    </ErrorBoundary>,
  );

  expect(screen.getByRole("alert")).toHaveTextContent("Dashboard rendering error");
  expect(screen.getByText("boom")).toBeInTheDocument();
});
