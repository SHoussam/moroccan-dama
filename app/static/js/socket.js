export class RoomSocket {
  constructor({ roomCode, token, onMessage, onConnectionChange, onFatalClose }) {
    this.roomCode = roomCode;
    this.token = token;
    this.onMessage = onMessage;
    this.onConnectionChange = onConnectionChange;
    this.onFatalClose = onFatalClose;

    this.ws = null;
    this.closedIntentionally = false;
    this.reconnectAttempts = 0;
    this.reconnectTimer = null;
    this.pingInterval = null;
  }

  connect() {
    this.closedIntentionally = false;
    this._openSocket();
  }

  _buildUrl() {
    const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
    const code = encodeURIComponent(this.roomCode);
    const tok = encodeURIComponent(this.token);
    return `${proto}//${window.location.host}/ws/${code}?token=${tok}`;
  }

  _openSocket() {
    this._clearTimers();
    const ws = new WebSocket(this._buildUrl());
    this.ws = ws;

    ws.addEventListener("open", () => {
      if (this.ws !== ws) return;
      this.reconnectAttempts = 0;
      this.onConnectionChange?.({ connected: true, reconnecting: false });
      this.pingInterval = window.setInterval(() => {
        this.send({ type: "ping" });
      }, 25000);
    });

    ws.addEventListener("message", (event) => {
      if (this.ws !== ws) return;
      try {
        const msg = JSON.parse(event.data);
        if (msg.type === "pong") return;
        this.onMessage?.(msg);
      } catch {
        // Ignore unparseable frames
      }
    });

    ws.addEventListener("close", (event) => {
      if (this.ws !== ws) return;
      this._clearPing();

      if (this.closedIntentionally) {
        this.onConnectionChange?.({ connected: false, reconnecting: false });
        return;
      }

      // 4403 (unauthorized), 4404 (not found / expired), 4000 (superseded)
      if (event.code === 4403 || event.code === 4404 || event.code === 4000) {
        this.closedIntentionally = true;
        this.onConnectionChange?.({ connected: false, reconnecting: false });
        this.onFatalClose?.(event.code);
        return;
      }

      this.onConnectionChange?.({ connected: false, reconnecting: true });
      const delay = Math.min(8000, 800 * Math.pow(1.8, this.reconnectAttempts));
      this.reconnectAttempts += 1;
      this.reconnectTimer = window.setTimeout(() => {
        if (!this.closedIntentionally) {
          this._openSocket();
        }
      }, delay);
    });
  }

  send(payload) {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(payload));
      return true;
    }
    return false;
  }

  sendMove(fromCoord, landings, revision) {
    return this.send({
      type: "make_move",
      from: fromCoord,
      landings,
      revision,
    });
  }

  sendResign() {
    return this.send({ type: "resign" });
  }

  sendRematchRequest() {
    return this.send({ type: "request_rematch" });
  }

  _clearPing() {
    if (this.pingInterval !== null) {
      window.clearInterval(this.pingInterval);
      this.pingInterval = null;
    }
  }

  _clearTimers() {
    this._clearPing();
    if (this.reconnectTimer !== null) {
      window.clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
  }

  close() {
    this.closedIntentionally = true;
    this._clearTimers();
    if (this.ws) {
      try {
        this.ws.close(1000, "Client leaving room");
      } catch {
        // Ignore close error
      }
      this.ws = null;
    }
  }
}
