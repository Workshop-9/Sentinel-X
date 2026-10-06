export class WebSocketService {
  // Mémorisation de l'URL du WebSocket et du callback pour traiter les messages entrants
  constructor(url, onMessageCallback) {
    this.url = url;
    this.onMessage = onMessageCallback;
    this.ws = null;
  }

  connect() {
    this.ws = new WebSocket(this.url);

    // Gestion des événements WebSocket
    this.ws.onopen = () => console.log('[WS] Connecté au Backend Sentinel-X');
    this.ws.onmessage = (event) => {
      const data = JSON.parse(event.data);
      this.onMessage(data);
    };
    this.ws.onclose = () => {
      console.warn('[WS] Déconnecté. Reconnexion dans 3s...');
      setTimeout(() => this.connect(), 3000);
    };
  }

  // Méthode pour envoyer des messages au serveur WebSocket
  send(payload) {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(payload));
    }
  }
}