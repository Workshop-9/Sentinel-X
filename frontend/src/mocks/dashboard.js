export const dashboardMock = {
  live: true,
  status: {
    device_id: "esp8266-01",
    state: "WARNING",
    online: true,
    rssi_dbm: -61,
  },
  telemetry: [
    {
      received_at: "2026-10-06T10:15:00Z",
      sensors: { temperature_c: 22.8, humidity_pct: 46, gas_ppm: 310 },
    },
    {
      received_at: "2026-10-06T10:16:00Z",
      sensors: { temperature_c: 23.1, humidity_pct: 47, gas_ppm: 420 },
    },
    {
      received_at: "2026-10-06T10:17:00Z",
      sensors: { temperature_c: 23.4, humidity_pct: 47, gas_ppm: 680 },
    },
  ],
  alerts: [
    {
      id: "alert-001",
      type: "GAZ ÉLEVÉ",
      severity: "critical",
      event: "raised",
      source: "mq2",
      received_at: "2026-10-06T10:17:00Z",
      acknowledged: false,
    },
  ],
  commands: {
    "cmd-1042": {
      id: "cmd-1042",
      target: "buzzer",
      action: "blink",
      status: "completed",
    },
  },
  error: null,
};
