import { defineStore } from 'pinia';
import { WebSocketService } from '../services/websocket';

export const useSentinelStore = defineStore('sentinel', {
  state: () => ({
    connected: false,
    wsService: null,
    metrics: {
      dht22_temp: null,
      mq2_gas: null,
      pir_motion: false,
      anomaly_score: null,
    },
    actuators: {
      buzzer: false,
      led_mode: 'AUTO',
    },
    alerts: [],
    history: {
      labels: [],
      temp: [],
      gas: [],
    }
  }),
  actions: {
    initWebSocket() {
      const wsUrl = `wss://${window.location.hostname}:8443/ws`;
      this.wsService = new WebSocketService(wsUrl, this.handleRealtimeData);
      this.wsService.connect();
    },
    handleRealtimeData(data) {
      if (data.type === 'telemetry') {
        this.metrics = { ...this.metrics, ...data.payload };
        
        // Mise à jour de l'historique Chart.js
        const timeStr = new Date().toLocaleTimeString();
        this.history.labels.push(timeStr);
        this.history.temp.push(data.payload.dht22_temp);
        this.history.gas.push(data.payload.mq2_gas);

        if (this.history.labels.length > 20) {
          this.history.labels.shift();
          this.history.temp.shift();
          this.history.gas.shift();
        }
      } else if (data.type === 'alert') {
        this.alerts.unshift(data.payload);
      }
    },
    toggleBuzzer() {
      this.actuators.buzzer = !this.actuators.buzzer;
      this.wsService.send({ type: 'command', target: 'buzzer', state: this.actuators.buzzer });
    },
    setLedMode(mode) {
      this.actuators.led_mode = mode;
      this.wsService.send({ type: 'command', target: 'leds', mode });
    },
    acknowledgeAlert(id) {
      this.alerts = this.alerts.filter(a => a.id !== id);
    }
  }
});