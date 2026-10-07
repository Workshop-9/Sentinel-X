import { reactive, computed } from "vue";
import * as api from "../services/api";

const MAX_POINTS = 300;
const MAX_ALERTS = 100;
const HISTORY_MINUTES = 10;

const ERRORS = { 429: "Trop de requêtes, réessayez dans une minute." };

export const state = reactive({
  live: false,
  status: null,
  telemetry: [],
  alerts: [],
  commands: {},
  error: null,
});

let stopLive = null;

// ---------- Getters ----------

export const latest = computed(() => state.telemetry.at(-1) ?? null);

export const activeAlerts = computed(() =>
  state.alerts.filter((a) => a.event === "raised" && !a.acknowledged),
);

export const chart = computed(() => ({
  labels: state.telemetry.map((t) => t.received_at),
  temperature: state.telemetry.map((t) => t.sensors.temperature_c ?? null),
  humidity: state.telemetry.map((t) => t.sensors.humidity_pct ?? null),
  gas: state.telemetry.map((t) => t.sensors.gas_ppm ?? null),
}));

// ---------- Messages temps réel ----------

function upsertAlert(alert) {
  const i = state.alerts.findIndex((a) => a.id === alert.id);
  if (i >= 0) state.alerts[i] = alert;
  else state.alerts.unshift(alert);
  if (state.alerts.length > MAX_ALERTS) state.alerts.length = MAX_ALERTS;
}

function handleMessage({ type, data }) {
  switch (type) {
    case "telemetry":
      state.telemetry.push(data);
      if (state.telemetry.length > MAX_POINTS) state.telemetry.shift();
      break;
    case "alert":
      upsertAlert(data);
      break;
    case "status":
      state.status = data;
      break;
    case "command":
      state.commands[data.id] = { ...state.commands[data.id], ...data };
      break;
  }
}

// ---------- Actions ----------

async function loadHistory() {
  const since = new Date(Date.now() - HISTORY_MINUTES * 60000).toISOString();
  const [status, telemetry, alerts] = await Promise.all([
    api.getStatus(),
    api.getTelemetry({ since, limit: MAX_POINTS }),
    api.getAlerts({ limit: 50 }),
  ]);
  state.status = status;
  state.telemetry = telemetry.items;
  state.alerts = alerts.items;
}

async function guarded(fn) {
  try {
    state.error = null;
    return await fn();
  } catch (e) {
    state.error = ERRORS[e.status] || e.message;
    throw e;
  }
}

export const actions = {
  async start() {
    await guarded(loadHistory);
    stopLive?.();
    stopLive = api.connectLive({
      onMessage: handleMessage,
      onOpen: () => {
        state.live = true;
        loadHistory().catch(() => {});
      },
      onClose: () => {
        state.live = false;
      },
    });
  },

  async sendCommand(target, action, duration_ms = 0) {
    return guarded(async () => {
      const deviceId = state.status?.device_id;
      if (!deviceId) {
        throw new Error("Identifiant du boîtier indisponible.");
      }

      const res = await api.sendCommand(deviceId, target, action, duration_ms);
      state.commands[res.id] = {
        id: res.id,
        device_id: deviceId,
        target,
        action,
        status: res.status,
      };
      return res;
    });
  },
};
