import http from 'node:http';
import { WebSocketServer } from 'ws';

const PORT = parseInt(process.env.PORT || '8765', 10);

let activeExtensionWs = null;
let reqId = 1;
const pendingResponses = new Map();

// HTTP Server for REST API
const server = http.createServer(async (req, res) => {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'GET, POST, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type');

  if (req.method === 'OPTIONS') {
    res.writeHead(204);
    res.end();
    return;
  }

  const url = new URL(req.url, `http://${req.headers.host || 'localhost'}`);

  // Health / Status endpoint
  if (url.pathname === '/api/status' && req.method === 'GET') {
    res.writeHead(200, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({
      status: 'ok',
      extensionConnected: activeExtensionWs !== null && activeExtensionWs.readyState === 1
    }));
    return;
  }

  // API Command handler
  if (url.pathname.startsWith('/api/')) {
    if (!activeExtensionWs || activeExtensionWs.readyState !== 1) {
      res.writeHead(503, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify({
        success: false,
        error: 'Chrome extension is not connected. Please ensure Chrome is open with the Antigravity Bridge extension loaded.'
      }));
      return;
    }

    let body = {};
    if (req.method === 'POST') {
      try {
        const buffers = [];
        for await (const chunk of req) buffers.push(chunk);
        const dataStr = Buffer.concat(buffers).toString();
        if (dataStr) body = JSON.parse(dataStr);
      } catch (err) {
        res.writeHead(400, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({ success: false, error: 'Invalid JSON payload' }));
        return;
      }
    }

    const action = url.pathname.replace('/api/', '').replace(/\/$/, '');
    const id = reqId++;

    const actionMap = {
      'tabs': 'list_tabs',
      'active-tab': 'get_active_tab',
      'navigate': 'navigate',
      'click': 'click',
      'type': 'type',
      'content': 'get_page_content',
      'scroll': 'scroll',
      'eval': 'execute_script',
      'close': 'close_tab',
      'switch': 'switch_tab'
    };

    const targetAction = actionMap[action] || action;

    const promise = new Promise((resolve, reject) => {
      const timeout = setTimeout(() => {
        pendingResponses.delete(id);
        reject(new Error(`Command "${targetAction}" timed out after 10s`));
      }, 10000);

      pendingResponses.set(id, { resolve, reject, timeout });
    });

    // Send RPC over WebSocket to Chrome extension
    activeExtensionWs.send(JSON.stringify({
      id,
      action: targetAction,
      params: body
    }));

    try {
      const result = await promise;
      res.writeHead(200, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify({ success: true, result }));
    } catch (err) {
      res.writeHead(500, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify({ success: false, error: err.message }));
    }
    return;
  }

  res.writeHead(200, { 'Content-Type': 'text/plain' });
  res.end('Antigravity Chrome Bridge Server is running on port ' + PORT + '\n');
});

// WebSocket Server for Extension communication
const wss = new WebSocketServer({ server });

wss.on('connection', (ws, req) => {
  console.log('⚡ [Server] Chrome extension connected!');
  activeExtensionWs = ws;

  ws.on('message', (message) => {
    try {
      const data = JSON.parse(message.toString());
      if (data.event === 'ping') {
        ws.send(JSON.stringify({ event: 'pong' }));
        return;
      }
      if (data.event === 'ready') {
        console.log(`🚀 [Server] Extension ready: ${data.browser}`);
      } else if (data.id && pendingResponses.has(data.id)) {
        const { resolve, reject, timeout } = pendingResponses.get(data.id);
        clearTimeout(timeout);
        pendingResponses.delete(data.id);

        if (data.success) {
          resolve(data.result);
        } else {
          reject(new Error(data.error || 'Unknown extension error'));
        }
      }
    } catch (err) {
      console.error('[Server] Failed to handle extension message:', err);
    }
  });

  ws.on('close', () => {
    console.log('⚠️ [Server] Chrome extension disconnected');
    if (activeExtensionWs === ws) {
      activeExtensionWs = null;
    }
  });
});

server.listen(PORT, '127.0.0.1', () => {
  console.log(`🌐 Antigravity Bridge Server listening on http://127.0.0.1:${PORT}`);
  console.log(`🔌 Extension WebSocket endpoint: ws://127.0.0.1:${PORT}`);
  console.log(`📡 Ready for commands!`);
});
