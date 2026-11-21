import { useState, useEffect, useCallback } from "react";
import {
  getHealth,
  getOperationsStatus,
  sendTestPush,
  type HealthResponse,
  type OperationsStatusResponse,
} from "../api";
import { disablePush, enablePush, isPushEnabled, pushSupported } from "../push";
import "./Status.css";

const REFRESH_INTERVAL_MS = 10_000;

const COMPONENT_LABELS: Record<string, string> = {
  memory: "Memory",
  tools: "Tools",
  proactive: "Proactive Engine",
  automations: "Automations",
};

export function StatusView() {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [operations, setOperations] =
    useState<OperationsStatusResponse | null>(null);
  const [operationsError, setOperationsError] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [lastChecked, setLastChecked] = useState<Date | null>(null);
  const [pushOn, setPushOn] = useState(false);
  const [pushBusy, setPushBusy] = useState(false);
  const [pushError, setPushError] = useState<string | null>(null);
  const [testPushResult, setTestPushResult] = useState<string | null>(null);
  const [testPushBusy, setTestPushBusy] = useState(false);

  const refresh = useCallback(() => {
    getHealth()
      .then((data) => {
        setHealth(data);
        setError(null);
        setLastChecked(new Date());
      })
      .catch((err: unknown) => {
        setError(err instanceof Error ? err.message : "Connection failed");
        setHealth(null);
        setLastChecked(new Date());
      });
    getOperationsStatus()
      .then((data) => {
        setOperations(data);
        setOperationsError(null);
      })
      .catch((err: unknown) => {
        setOperations(null);
        setOperationsError(
          err instanceof Error ? err.message : "Status unavailable",
        );
      });
  }, []);

  useEffect(() => {
    refresh();
    const id = setInterval(refresh, REFRESH_INTERVAL_MS);
    return () => clearInterval(id);
  }, [refresh]);

  useEffect(() => {
    isPushEnabled().then(setPushOn).catch(() => setPushOn(false));
  }, []);

  const togglePush = useCallback(async () => {
    setPushBusy(true);
    setPushError(null);
    setTestPushResult(null);
    try {
      if (pushOn) {
        await disablePush();
        setPushOn(false);
      } else {
        await enablePush();
        setPushOn(true);
      }
    } catch (err: unknown) {
      setPushError(err instanceof Error ? err.message : "Push toggle failed");
    } finally {
      setPushBusy(false);
    }
  }, [pushOn]);

  const onTestPush = useCallback(async () => {
    setTestPushBusy(true);
    setTestPushResult(null);
    setPushError(null);
    try {
      const res = await sendTestPush("Animus Test", "This is a test push notification.", "/pwa/status");
      setTestPushResult(`Sent ${res.sent} notification(s)` + (res.pruned ? `, pruned ${res.pruned} stale.` : "."));
    } catch (err: unknown) {
      setPushError(err instanceof Error ? err.message : "Test push failed");
    } finally {
      setTestPushBusy(false);
    }
  }, []);

  return (
    <div className="status">
      <h1 className="status-title">System Status</h1>

      <div className="status-card">
        <div className="status-row">
          <span className="status-label">Backend</span>
          {error ? (
            <span className="status-badge status-badge--error">Offline</span>
          ) : health ? (
            <span className="status-badge status-badge--ok">
              {health.status === "ok" ? "Online" : "Degraded"}
            </span>
          ) : (
            <span className="status-badge status-badge--loading">
              Checking...
            </span>
          )}
        </div>

        {health && (
          <div className="status-row">
            <span className="status-label">Backend Version</span>
            <span className="status-value">{health.version}</span>
          </div>
        )}

        <div className="status-row">
          <span className="status-label">Dashboard</span>
          <span className="status-value">localhost:7700</span>
        </div>

        <div className="status-row">
          <span className="status-label">PWA Version</span>
          <span className="status-value">0.1.0</span>
        </div>

        {lastChecked && (
          <div className="status-row">
            <span className="status-label">Last Checked</span>
            <span className="status-value">
              {lastChecked.toLocaleTimeString()}
            </span>
          </div>
        )}
      </div>

      {health && (
        <div className="status-card status-components">
          <h2 className="status-section-title">Components</h2>
          {Object.entries(health.components).map(([key, ok]) => (
            <div key={key} className="status-row">
              <span className="status-label">
                {COMPONENT_LABELS[key] ?? key}
              </span>
              <span
                className={`status-badge ${ok ? "status-badge--ok" : "status-badge--error"}`}
              >
                {ok ? "Active" : "Inactive"}
              </span>
            </div>
          ))}
        </div>
      )}

      <div className="status-card status-components">
        <h2 className="status-section-title">Engineering Workflow</h2>
        <div className="status-row">
          <span className="status-label">Forgehand relay</span>
          {operationsError ? (
            <span className="status-badge status-badge--error">
              Unavailable
            </span>
          ) : operations ? (
            <RelayStatusBadge status={operations.forgehand_relay.status} />
          ) : (
            <span className="status-badge status-badge--loading">
              Checking...
            </span>
          )}
        </div>
        <p className="status-value">
          Listener response only. This does not validate Ollama, worker
          activation, or job execution.
        </p>
        {operations && (
          <div className="status-row">
            <span className="status-label">Relay checked</span>
            <span className="status-value">
              {new Date(operations.checked_at).toLocaleTimeString()}
            </span>
          </div>
        )}
      </div>

      {pushSupported() && (
        <div className="status-card">
          <div className="status-row">
            <span className="status-label">Push Notifications</span>
            <button
              className={`status-toggle ${pushOn ? "status-toggle--on" : ""}`}
              onClick={togglePush}
              disabled={pushBusy}
            >
              {pushBusy ? "..." : pushOn ? "On" : "Off"}
            </button>
            {pushOn && (
              <button
                className="status-button"
                onClick={onTestPush}
                disabled={testPushBusy}
                title="Send a test push notification to this device"
              >
                {testPushBusy ? "Sending..." : "Test Push"}
              </button>
            )}
          </div>
          {pushError && <p className="status-error">{pushError}</p>}
          {testPushResult && <p className="status-ok">{testPushResult}</p>}
        </div>
      )}

      {error && (
        <p className="status-error">
          Cannot reach backend: {error}. Make sure Bootstrap dashboard is
          running.
        </p>
      )}
    </div>
  );
}

function RelayStatusBadge({
  status,
}: {
  status: OperationsStatusResponse["forgehand_relay"]["status"];
}) {
  const tone =
    status === "responding"
      ? "ok"
      : status === "not_configured"
        ? "warning"
        : "error";
  const label = status.replace(/_/g, " ");

  return <span className={`status-badge status-badge--${tone}`}>{label}</span>;
}
