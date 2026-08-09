import { Activity, AlertTriangle, Lock, Radio, ShieldCheck } from "lucide-react";
import { useEffect, useState } from "react";

import { API_URL, DashboardData, Risk, loadDashboardData } from "./api";

const ALERT_LIMIT = 8;
const EVENT_LIMIT = 10;

const EMPTY_DATA: DashboardData = {
  risks: [],
  alerts: [],
  actions: [],
  audit: [],
};

const timestampFormatter = new Intl.DateTimeFormat("en-US", {
  month: "short",
  day: "numeric",
  year: "numeric",
  hour: "2-digit",
  minute: "2-digit",
  timeZone: "UTC",
  timeZoneName: "short",
});

function levelClass(level?: string) {
  return `level ${level ?? "normal"}`;
}

function statusClass(status?: string) {
  return `status ${status ?? "unknown"}`;
}

function firstRiskWithReasons(risks: Risk[]) {
  return risks.find((item) => item.risk && item.risk.reasons.length > 0);
}

function words(value: unknown): string {
  if (typeof value !== "string" || value.trim() === "") {
    return "";
  }
  return value.replace(/_/g, " ");
}

function titleCase(value: unknown, fallback = "Unknown"): string {
  const text = words(value);
  if (!text) {
    return fallback;
  }
  return text.replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function formatTimestamp(value: unknown): string {
  if (typeof value !== "string") {
    return "Time unavailable";
  }
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return "Time unavailable";
  }
  return timestampFormatter.format(parsed);
}

function stringField(record: Record<string, unknown>, key: string, fallback = "Unknown"): string {
  const value = record[key];
  if (typeof value === "string" && value.trim()) {
    return value;
  }
  if (typeof value === "number") {
    return String(value);
  }
  return fallback;
}

function details(record: Record<string, unknown>): Record<string, unknown> {
  const value = record.details ?? record.result;
  return typeof value === "object" && value !== null && !Array.isArray(value) ? (value as Record<string, unknown>) : {};
}

function reasonText(record: Record<string, unknown>, fallback: string): string {
  const source = details(record);
  if (typeof source.rationale === "string" && source.rationale.trim()) {
    return source.rationale;
  }
  if (Array.isArray(source.actions) && source.actions.length > 0) {
    return `Action evidence: ${source.actions.map((action) => titleCase(action)).join(", ")}`;
  }
  if (typeof source.reason === "string" && source.reason.trim()) {
    return source.reason;
  }
  if (typeof source.expires_at === "string") {
    return `Quarantine expires ${formatTimestamp(source.expires_at)}`;
  }
  if (source.restored === true) {
    return "Device access restored by response action.";
  }
  if (typeof record.risk_score === "number") {
    return `Risk score reached ${record.risk_score}.`;
  }
  return fallback;
}

function actionTitle(action: Record<string, unknown>): string {
  const name = stringField(action, "action", "response action");
  if (name === "temporary_quarantine") {
    return "Quarantined access";
  }
  if (name === "restore_access") {
    return "Restored access";
  }
  return titleCase(name, "Response Action");
}

function auditTitle(item: Record<string, unknown>): string {
  return titleCase(item.event_type, "Audit Event");
}

function alertTitle(alert: Record<string, unknown>): string {
  const level = titleCase(alert.level, "Risk");
  return `${level} risk: score ${stringField(alert, "risk_score", "unknown")}`;
}

export function App() {
  const [data, setData] = useState<DashboardData>(EMPTY_DATA);
  const [error, setError] = useState<string>("");
  const [loading, setLoading] = useState(true);

  async function load() {
    setLoading(true);
    try {
      setData(await loadDashboardData());
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown dashboard error");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
    const timer = window.setInterval(() => void load(), 10000);
    return () => window.clearInterval(timer);
  }, []);

  const active = data.risks.filter((item) => item.status === "active").length;
  const quarantined = data.risks.filter((item) => item.status === "quarantined").length;
  const high = data.risks.filter((item) => (item.risk?.risk_score ?? 0) >= 60).length;
  const explained = firstRiskWithReasons(data.risks);
  const visibleAlerts = data.alerts.slice(0, ALERT_LIMIT);
  const visibleActions = data.actions.slice(0, EVENT_LIMIT);
  const visibleAudit = data.audit.slice(0, EVENT_LIMIT);

  return (
    <main>
      <header>
        <div>
          <p className="eyebrow">Simulated defensive lab</p>
          <h1>AI Adaptive IoT Defense Platform</h1>
          <p className="subtle">
            Hardware-free IoT defense dashboard. All telemetry, attacks, and responses are simulated.
          </p>
        </div>
        <button aria-label="Retry dashboard data load" onClick={() => void load()}>
          <Activity size={18} /> Retry
        </button>
      </header>

      <section className="status-strip" aria-live="polite">
        <span>API: {API_URL}</span>
        <span>{loading ? "Loading simulated telemetry" : "Dashboard ready"}</span>
      </section>

      {error ? (
        <section className="error" role="alert">
          <strong>API unavailable or returned invalid data.</strong>
          <p>{error}</p>
        </section>
      ) : null}
      {loading ? <section className="empty">Loading simulated telemetry...</section> : null}

      <section className="summary" aria-label="System summary">
        <article>
          <Radio />
          <span>Devices</span>
          <strong>{data.risks.length}</strong>
        </article>
        <article>
          <ShieldCheck />
          <span>Active</span>
          <strong>{active}</strong>
        </article>
        <article>
          <Lock />
          <span>Quarantined</span>
          <strong>{quarantined}</strong>
        </article>
        <article>
          <AlertTriangle />
          <span>High risk</span>
          <strong>{high}</strong>
        </article>
      </section>

      <section className="grid">
        <div>
          <h2>Device Inventory</h2>
          <div className="table" role="table" aria-label="Device inventory">
            {data.risks.length === 0 ? (
              <p className="empty">No simulated devices have reported yet.</p>
            ) : (
              data.risks.map((item) => (
                <div className="row" key={item.device_id}>
                  <div>
                    <strong>{item.device_id}</strong>
                    <span>{item.device_type}</span>
                  </div>
                  <span className={levelClass(item.risk?.level)}>{item.risk?.level ?? "normal"}</span>
                  <strong>{item.risk?.risk_score ?? 0}</strong>
                  <span className={statusClass(item.status)}>Status: {titleCase(item.status)}</span>
                </div>
              ))
            )}
          </div>
        </div>
        <div>
          <h2>Risk Explanation</h2>
          {explained?.risk?.reasons.length ? (
            <>
              <p className="event-meta">
                Device: <strong>{explained.device_id}</strong> · Status: {titleCase(explained.status)}
              </p>
              {explained.risk.reasons.map((reason) => (
                <article className="explain" key={reason.signal}>
                  <strong>
                    {titleCase(reason.signal)}: +{reason.contribution}
                  </strong>
                  <p>{reason.explanation}</p>
                  <time>{formatTimestamp(explained.risk?.created_at)}</time>
                </article>
              ))}
            </>
          ) : (
            <p className="empty">No risk breakdown is available yet.</p>
          )}
        </div>
      </section>

      <section className="grid grid-events">
        <div>
          <div className="section-heading">
            <h2>Alerts</h2>
            <span>Latest {visibleAlerts.length} of {data.alerts.length}</span>
          </div>
          {data.alerts.length === 0 ? (
            <p className="empty">No simulated alerts.</p>
          ) : (
            <div className="event-list compact" role="list" aria-label="Latest alerts">
              {visibleAlerts.map((alert) => (
                <article className="timeline" key={String(alert.id)} role="listitem">
                  <strong>{alertTitle(alert)}</strong>
                  <span className="event-device">Device: {stringField(alert, "device_id")}</span>
                  <span className="event-reason">{reasonText(alert, "Risk threshold crossed.")}</span>
                  <time>{formatTimestamp(alert.created_at)}</time>
                </article>
              ))}
            </div>
          )}
        </div>
        <div>
          <div className="section-heading">
            <h2>Policy Actions</h2>
            <span>Latest {visibleActions.length} of {data.actions.length}</span>
          </div>
          {data.actions.length === 0 ? (
            <p className="empty">No policy actions yet.</p>
          ) : (
            <div className="event-list" role="list" aria-label="Latest policy actions">
              {visibleActions.map((action) => (
                <article className="timeline" key={String(action.id)} role="listitem">
                  <strong>{actionTitle(action)}</strong>
                  <span className="event-device">Device: {stringField(action, "device_id")}</span>
                  <span className="event-reason">{reasonText(action, "Policy selected an allow-listed response.")}</span>
                  <span className="status-text">Status: {titleCase(action.status, "Unknown")}</span>
                  <time>{formatTimestamp(action.created_at)}</time>
                </article>
              ))}
            </div>
          )}
        </div>
      </section>

      <section>
        <div className="section-heading">
          <h2>Audit Trail</h2>
          <span>Latest {visibleAudit.length} of {data.audit.length}</span>
        </div>
        {data.audit.length === 0 ? (
          <p className="empty">No audit events yet.</p>
        ) : (
          <div className="event-list audit-list" role="list" aria-label="Latest audit trail">
            {visibleAudit.map((item) => (
              <article className="timeline" key={String(item.id)} role="listitem">
                <strong>{auditTitle(item)}</strong>
                <span className="event-device">Device: {stringField(item, "device_id", "system")}</span>
                <span className="event-reason">{reasonText(item, "Append-only audit evidence recorded.")}</span>
                <time>{formatTimestamp(item.created_at)}</time>
              </article>
            ))}
          </div>
        )}
      </section>
    </main>
  );
}
