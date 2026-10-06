import { reactive, computed } from 'vue'
import * as api from '../services/api'

const MAX_POINTS = 300
const MAX_ALERTS = 100
const HISTORY_MINUTES = 10

const ERRORS = {
  403: 'Action réservée aux superviseurs.',
  429: 'Trop de tentatives, réessayez dans une minute.',
}

function sessionUser() {
  const s = api.getSession()
  return s ? { username: s.username, role: s.role } : null
}

export const state = reactive({
  authenticated: api.hasToken(),
  user: sessionUser(),
  live: false,
  status: null,
  telemetry: [],
  alerts: [],
  commands: {},
  error: null,
})

let stopLive = null
let expiryTimer = null

// ---------- Getters ----------

export const isSupervisor = computed(() => state.user?.role === 'supervisor')

export const latest = computed(() => state.telemetry.at(-1) ?? null)

export const activeAlerts = computed(() =>
  state.alerts.filter((a) => a.event === 'raised' && !a.acknowledged)
)

export const chart = computed(() => ({
  labels: state.telemetry.map((t) => t.received_at),
  temperature: state.telemetry.map((t) => t.sensors.temperature_c ?? null),
  humidity: state.telemetry.map((t) => t.sensors.humidity_pct ?? null),
  gas: state.telemetry.map((t) => t.sensors.gas_ppm ?? null),
}))

// ---------- Messages temps réel ----------

function upsertAlert(alert) {
  const i = state.alerts.findIndex((a) => a.id === alert.id)
  if (i >= 0) state.alerts[i] = alert
  else state.alerts.unshift(alert)
  if (state.alerts.length > MAX_ALERTS) state.alerts.length = MAX_ALERTS
}

function handleMessage({ type, data }) {
  switch (type) {
    case 'telemetry':
      state.telemetry.push(data)
      if (state.telemetry.length > MAX_POINTS) state.telemetry.shift()
      break
    case 'alert':
      upsertAlert(data)
      break
    case 'status':
      state.status = data
      break
    case 'command':
      state.commands[data.id] = { ...state.commands[data.id], ...data }
      break
  }
}

// ---------- Actions ----------

async function loadHistory() {
  const since = new Date(Date.now() - HISTORY_MINUTES * 60000).toISOString()
  const [status, telemetry, alerts] = await Promise.all([
    api.getStatus(),
    api.getTelemetry({ since, limit: MAX_POINTS }),
    api.getAlerts({ limit: 50 }),
  ])
  state.status = status
  state.telemetry = telemetry.items
  state.alerts = alerts.items
}

async function guarded(fn) {
  try {
    state.error = null
    return await fn()
  } catch (e) {
    if (e.status === 401) {
      state.authenticated = false
      state.user = null
    }
    state.error = ERRORS[e.status] || (e.status === 401 ? 'Identifiants incorrects ou session expirée.' : e.message)
    throw e
  }
}

function scheduleExpiry() {
  clearTimeout(expiryTimer)
  const s = api.getSession()
  if (!s) return
  expiryTimer = setTimeout(() => {
    actions.logout()
    state.error = 'Session expirée, reconnectez-vous.'
  }, Math.max(0, s.expires_at - Date.now()))
}

export const actions = {
  async login(username, password) {
    await guarded(() => api.login(username, password))
    state.authenticated = true
    state.user = sessionUser()
    await actions.start()
  },

  async start() {
    if (!state.authenticated) return
    scheduleExpiry()
    await guarded(loadHistory)
    stopLive?.()
    stopLive = api.connectLive({
      onMessage: handleMessage,
      onOpen: () => {
        state.live = true
        loadHistory().catch(() => {})
      },
      onClose: () => {
        state.live = false
      },
    })
  },

  logout() {
    stopLive?.()
    stopLive = null
    clearTimeout(expiryTimer)
    api.setSession(null)
    Object.assign(state, {
      authenticated: false,
      user: null,
      error: null,
      live: false,
      status: null,
      telemetry: [],
      alerts: [],
      commands: {},
    })
  },

  async sendCommand(target, action, duration_ms = 0) {
    const res = await guarded(() => api.sendCommand(target, action, duration_ms))
    state.commands[res.id] = { id: res.id, target, action, status: res.status }
    return res
  },
}