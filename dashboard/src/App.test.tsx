import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { readFileSync } from "node:fs";
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

function mockDashboardData(value: {
  risks?: unknown[];
  alerts?: unknown[];
  actions?: unknown[];
  audit?: unknown[];
}): void {
  vi.spyOn(globalThis, "fetch")
    .mockResolvedValueOnce(jsonResponse(value.risks ?? []))
    .mockResolvedValueOnce(jsonResponse(value.alerts ?? []))
    .mockResolvedValueOnce(jsonResponse({ items: value.actions ?? [], total: value.actions?.length ?? 0, limit: 12, offset: 0 }))
    .mockResolvedValueOnce(jsonResponse({ items: value.audit ?? [], total: value.audit?.length ?? 0, limit: 12, offset: 0 }));
}

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

it("declares a mobile viewport for responsive layouts", () => {
  const html = readFileSync("index.html", "utf-8");

  expect(html).toContain('name="viewport"');
  expect(html).toContain("width=device-width");
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
  mockDashboardData({
    risks: [
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
      ],
    alerts: [{ id: "a1", device_id: "camera-01", risk_score: 92, level: "critical", created_at: "2026-08-06T00:00:00Z" }],
  });

  render(<App />);

  expect(await screen.findAllByText("camera-01")).not.toHaveLength(0);
  expect(screen.getByText("critical")).toBeInTheDocument();
  expect(screen.getByText("Traffic Spike: +20")).toBeInTheDocument();
  expect(screen.getAllByText(/Device:/)[0]).toHaveTextContent("camera-01");
  expect(screen.getByText("Status: Active")).toBeInTheDocument();
});

it("formats timestamps with timezone and separates event title, device, reason, and time", async () => {
  mockDashboardData({
    alerts: [
      {
        id: "alert-1",
        device_id: "camera-01",
        risk_score: 92,
        level: "critical",
        created_at: "2026-08-06T00:00:00Z",
      },
    ],
    actions: [
      {
        id: "action-1",
        device_id: "camera-01",
        action: "temporary_quarantine",
        status: "completed",
        result: { expires_at: "2026-08-06T00:30:00Z" },
        created_at: "2026-08-06T00:01:00Z",
      },
      {
        id: "action-2",
        device_id: "camera-01",
        action: "restore_access",
        status: "completed",
        result: { restored: true },
        created_at: "2026-08-06T00:20:00Z",
      },
    ],
    audit: [
      {
        id: "audit-1",
        event_type: "policy.decision",
        device_id: "camera-01",
        details: { rationale: "Critical repeated simulated anomaly" },
        created_at: "2026-08-06T00:01:00Z",
      },
    ],
  });

  render(<App />);

  expect(await screen.findByText("Critical risk: score 92")).toBeInTheDocument();
  expect(screen.getAllByText("Device: camera-01").length).toBeGreaterThanOrEqual(3);
  expect(screen.getByText("Quarantined access")).toBeInTheDocument();
  expect(screen.getByText("Restored access")).toBeInTheDocument();
  expect(screen.getAllByText("Status: Completed")).toHaveLength(2);
  expect(screen.getByText("Critical repeated simulated anomaly")).toBeInTheDocument();
  expect(screen.getAllByText(/Aug 6, 2026/)[0]).toHaveTextContent("UTC");
  expect(screen.queryByText(/2026-08-06T00:01:00Z/)).not.toBeInTheDocument();
});

it("bounds long alert, policy, and audit lists to latest visible items", async () => {
  mockDashboardData({
    alerts: Array.from({ length: 12 }, (_, index) => ({
      id: `alert-${index}`,
      device_id: `camera-${index}`,
      risk_score: 70 + index,
      created_at: "2026-08-06T00:00:00Z",
    })),
    actions: Array.from({ length: 12 }, (_, index) => ({
      id: `action-${index}`,
      device_id: `camera-${index}`,
      action: "notify_only",
      status: "completed",
      created_at: "2026-08-06T00:00:00Z",
    })),
    audit: Array.from({ length: 12 }, (_, index) => ({
      id: `audit-${index}`,
      event_type: "policy.decision",
      device_id: `camera-${index}`,
      created_at: "2026-08-06T00:00:00Z",
    })),
  });

  render(<App />);

  expect(await screen.findByText("Latest 8 of 12")).toBeInTheDocument();
  expect(screen.getAllByText("Latest 10 of 12")).toHaveLength(2);
  expect(screen.getByLabelText("Latest alerts").children).toHaveLength(8);
  expect(screen.getByLabelText("Latest policy actions").children).toHaveLength(10);
  expect(screen.getByLabelText("Latest audit trail").children).toHaveLength(10);
});

it("shows explicit active, suspicious, quarantined, and restored labels", async () => {
  mockDashboardData({
    risks: [
      { device_id: "camera-01", device_type: "smart_camera", status: "active", risk: { risk_score: 0, level: "normal", reasons: [], created_at: "2026-08-06T00:00:00Z" } },
      { device_id: "lock-01", device_type: "smart_lock", status: "active", risk: { risk_score: 45, level: "suspicious", reasons: [], created_at: "2026-08-06T00:00:00Z" } },
      { device_id: "industrial-01", device_type: "industrial_sensor", status: "quarantined", risk: { risk_score: 92, level: "critical", reasons: [], created_at: "2026-08-06T00:00:00Z" } },
    ],
    actions: [
      {
        id: "restore-1",
        device_id: "industrial-01",
        action: "restore_access",
        status: "completed",
        result: { restored: true },
        created_at: "2026-08-06T00:00:00Z",
      },
    ],
  });

  render(<App />);

  expect(await screen.findAllByText("Status: Active")).toHaveLength(2);
  expect(screen.getByText("suspicious")).toBeInTheDocument();
  expect(screen.getByText("Status: Quarantined")).toBeInTheDocument();
  expect(screen.getByText("Restored access")).toBeInTheDocument();
  expect(screen.getByText("Device access restored by response action.")).toBeInTheDocument();
});

it("requests bounded policy and audit pages", async () => {
  mockDashboardData({});

  render(<App />);

  await screen.findByText("No simulated devices have reported yet.");
  expect(fetch).toHaveBeenCalledWith("http://localhost:8000/api/response-actions?limit=12", expect.any(Object));
  expect(fetch).toHaveBeenCalledWith("http://localhost:8000/api/audit-logs?limit=12", expect.any(Object));
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
