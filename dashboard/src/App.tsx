import { Activity, AlertTriangle, Lock, Radio, ShieldCheck } from "lucide-react";
import { useEffect, useState } from "react";

import { API_URL, DashboardData, Risk, loadDashboardData } from "./api";

const EMPTY_DATA: DashboardData = {
  risks: [],
  alerts: [],
  actions: [],
  audit: [],
};

function levelClass(level?: string) {
  return `level ${level ?? "normal"}`;
}

function firstRiskWithReasons(risks: Risk[]) {
  return risks.find((item) => item.risk && item.risk.reasons.length > 0);
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
                  <span>{item.status}</span>
                </div>
              ))
            )}
          </div>
        </div>
        <div>
          <h2>Risk Explanation</h2>
          {explained?.risk?.reasons.length ? (
            explained.risk.reasons.map((reason) => (
              <article className="explain" key={reason.signal}>
                <strong>
                  {reason.signal}: +{reason.contribution}
                </strong>
                <p>{reason.explanation}</p>
              </article>
            ))
          ) : (
            <p className="empty">No risk breakdown is available yet.</p>
          )}
        </div>
      </section>

      <section className="grid">
        <div>
          <h2>Alerts</h2>
          {data.alerts.length === 0 ? (
            <p className="empty">No simulated alerts.</p>
          ) : (
            data.alerts.slice(0, 8).map((alert) => (
              <article className="timeline" key={String(alert.id)}>
                <strong>
                  {String(alert.device_id)} risk {String(alert.risk_score)}
                </strong>
                <span>{String(alert.created_at)}</span>
              </article>
            ))
          )}
        </div>
        <div>
          <h2>Policy Actions</h2>
          {data.actions.length === 0 ? (
            <p className="empty">No policy actions yet.</p>
          ) : (
            data.actions.map((action) => (
              <article className="timeline" key={String(action.id)}>
                <strong>
                  {String(action.action)}: {String(action.device_id)}
                </strong>
                <span>{String(action.created_at)}</span>
              </article>
            ))
          )}
        </div>
      </section>

      <section>
        <h2>Audit Trail</h2>
        {data.audit.length === 0 ? (
          <p className="empty">No audit events yet.</p>
        ) : (
          data.audit.map((item) => (
            <article className="timeline" key={String(item.id)}>
              <strong>{String(item.event_type)}</strong>
              <span>
                {String(item.device_id ?? "system")} · {String(item.created_at)}
              </span>
            </article>
          ))
        )}
      </section>
    </main>
  );
}
