const BASE =
  import.meta.env.VITE_API_URL ||
  `${location.protocol}//${location.hostname}:8000`;

// Un seul boîtier : identifiant fixe, aligné avec DEVICE_ID du backend (.env)
export const DEVICE_ID = import.meta.env.VITE_DEVICE_ID || "esp8266-01";

export class ApiError extends Error {
  constructor(status, code, message) {
    super(message);
    this.status = status;
    this.code = code;
  }
}

async function request(path, { method = "GET", body, params } = {}) {
  const url = new URL(BASE + path);
  if (params) {
    Object.entries(params).forEach(([k, v]) => {
      if (v !== undefined && v !== null) url.searchParams.set(k, v);
    });
  }
  const res = await fetch(url, {
    method,
    headers: { "Content-Type": "application/json" },
    body: body ? JSON.stringify(body) : undefined,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const e = data.error || {};
    throw new ApiError(
      res.status,
      e.code || "unknown",
      e.message || res.statusText,
    );
  }
  return data;
}

export const getStatus = () => request("/api/v1/status");
export const getTelemetry = (params) =>
  request("/api/v1/telemetry", { params });
export const getAlerts = (params) => request("/api/v1/alerts", { params });
export const sendCommand = (target, action, duration_ms = 0) =>
  request("/api/v1/commands", {
    method: "POST",
    body: { device_id: DEVICE_ID, target, action, duration_ms },
  });

export const videoUrl = () => `${BASE}/video/stream`;

// Connexion temps réel avec reconnexion automatique (max 10 s)
export function connectLive({ onMessage, onOpen, onClose }) {
  let ws = null;
  let delay = 1000;
  let stopped = false;

  const open = () => {
    ws = new WebSocket(`${BASE.replace(/^http/, "ws")}/ws/live`);
    ws.onopen = () => {
      delay = 1000;
      onOpen?.();
    };
    ws.onmessage = (e) => {
      try {
        onMessage(JSON.parse(e.data));
      } catch {
        // message illisible : ignoré
      }
    };
    ws.onclose = () => {
      onClose?.();
      if (stopped) return;
      setTimeout(open, delay);
      delay = Math.min(delay * 2, 10000);
    };
  };

  open();
  return () => {
    stopped = true;
    ws?.close();
  };
}
