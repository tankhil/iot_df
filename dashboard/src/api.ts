export const API_URL = import.meta.env.VITE_API_URL?.trim() || "http://localhost:8000";

export type RiskReason = {
  signal: string;
  contribution: number;
  explanation: string;
};

export type Risk = {
  device_id: string;
  device_type: string;
  status: string;
  risk: null | {
    risk_score: number;
    level: string;
    reasons: RiskReason[];
    created_at: string;
  };
};

export type ApiPage = {
  items: Record<string, unknown>[];
  total: number;
  limit: number;
  offset: number;
};

export type DashboardData = {
  risks: Risk[];
  alerts: Record<string, unknown>[];
  actions: Record<string, unknown>[];
  audit: Record<string, unknown>[];
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function validatePage(value: unknown, name: string): ApiPage {
  if (!isRecord(value) || !Array.isArray(value.items)) {
    throw new Error(`${name} returned an unexpected response shape`);
  }
  return {
    items: value.items.filter(isRecord),
    total: typeof value.total === "number" ? value.total : value.items.length,
    limit: typeof value.limit === "number" ? value.limit : value.items.length,
    offset: typeof value.offset === "number" ? value.offset : 0,
  };
}

function validateRisks(value: unknown): Risk[] {
  if (!Array.isArray(value)) {
    throw new Error("Risk endpoint returned an unexpected response shape");
  }
  return value.filter((item): item is Risk => {
    if (!isRecord(item)) {
      return false;
    }
    return (
      typeof item.device_id === "string" &&
      typeof item.device_type === "string" &&
      typeof item.status === "string"
    );
  });
}

function validateRecords(value: unknown, name: string): Record<string, unknown>[] {
  if (!Array.isArray(value)) {
    throw new Error(`${name} returned an unexpected response shape`);
  }
  return value.filter(isRecord);
}

async function fetchJson(path: string, signal: AbortSignal): Promise<unknown> {
  const response = await fetch(`${API_URL}${path}`, {
    signal,
    headers: { Accept: "application/json" },
  });
  if (!response.ok) {
    throw new Error(`${path} failed with HTTP ${response.status}`);
  }
  return response.json() as Promise<unknown>;
}

export async function loadDashboardData(timeoutMs = 5000): Promise<DashboardData> {
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), timeoutMs);
  try {
    const [riskJson, alertJson, actionJson, auditJson] = await Promise.all([
      fetchJson("/api/risks/current", controller.signal),
      fetchJson("/api/alerts", controller.signal),
      fetchJson("/api/response-actions?limit=20", controller.signal),
      fetchJson("/api/audit-logs?limit=20", controller.signal),
    ]);
    return {
      risks: validateRisks(riskJson),
      alerts: validateRecords(alertJson, "Alerts endpoint"),
      actions: validatePage(actionJson, "Response actions endpoint").items,
      audit: validatePage(auditJson, "Audit endpoint").items,
    };
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") {
      throw new Error("API request timed out");
    }
    throw error;
  } finally {
    window.clearTimeout(timeout);
  }
}
