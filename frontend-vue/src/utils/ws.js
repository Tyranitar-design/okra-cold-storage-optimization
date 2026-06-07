class WsClient {
  constructor(baseUrl = '') {
    this.baseUrl = baseUrl || window.location.origin.replace(/^http/, 'ws')
    this.connections = {}
    this.listeners = {}
  }

  connect(channel, token) {
    if (this.connections[channel]) {
      this.disconnect(channel)
    }
    const url = `${this.baseUrl}/ws/${channel}?token=${token}`
    const ws = new WebSocket(url)
    this.connections[channel] = ws

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data)
        const handlers = this.listeners[channel] || []
        handlers.forEach((h) => h(data))
      } catch {
        // ignore parse errors
      }
    }

    ws.onerror = () => {}

    ws.onclose = () => {
      // 5 秒后自动重连
      this.connections[channel] = null
      setTimeout(() => {
        const t = localStorage.getItem('token')
        if (t) this.connect(channel, t)
      }, 5000)
    }
  }

  on(channel, handler) {
    if (!this.listeners[channel]) this.listeners[channel] = []
    this.listeners[channel].push(handler)
  }

  off(channel, handler) {
    if (!this.listeners[channel]) return
    this.listeners[channel] = this.listeners[channel].filter((h) => h !== handler)
  }

  disconnect(channel) {
    if (this.connections[channel]) {
      this.connections[channel].close()
      this.connections[channel] = null
    }
  }

  disconnectAll() {
    Object.keys(this.connections).forEach((ch) => this.disconnect(ch))
  }

  getStatus(channel) {
    const ws = this.connections[channel]
    if (!ws) return 'disconnected'
    if (ws.readyState === WebSocket.OPEN) return 'connected'
    if (ws.readyState === WebSocket.CONNECTING) return 'connecting'
    return 'disconnected'
  }
}

export const wsClient = new WsClient()
