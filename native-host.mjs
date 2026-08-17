#!/usr/bin/env node

import net from 'node:net';
import { unlinkSync, existsSync, writeFileSync } from 'node:fs';
import { Buffer } from 'node:buffer';
import { tmpdir, platform } from 'node:os';
import { join } from 'node:path';

const isWindows = platform() === 'win32';
const SOCKET_PATH = join(tmpdir(), 'antigravity_chrome_bridge.sock');
const PORT_FILE = join(tmpdir(), 'antigravity_chrome_bridge.port');

// Map of pending MCP client requests: id -> net.Socket
const pendingRequests = new Map();

// 1. Chrome Native Messaging Framing
function sendNativeMessage(obj) {
  try {
    const jsonBuf = Buffer.from(JSON.stringify(obj), 'utf8');
    const header = Buffer.alloc(4);
    header.writeUInt32LE(jsonBuf.length, 0);
    process.stdout.write(Buffer.concat([header, jsonBuf]));
  } catch (err) {
    // Stdio write failed (Chrome may have closed)
  }
}

// Buffer incoming stdio data from Chrome
let inputBuffer = Buffer.alloc(0);

process.stdin.on('data', (chunk) => {
  inputBuffer = Buffer.concat([inputBuffer, chunk]);

  while (inputBuffer.length >= 4) {
    const msgLen = inputBuffer.readUInt32LE(0);
    if (inputBuffer.length < 4 + msgLen) {
      break; // Incomplete message, wait for more chunks
    }

    const jsonStr = inputBuffer.subarray(4, 4 + msgLen).toString('utf8');
    inputBuffer = inputBuffer.subarray(4 + msgLen);

    try {
      const response = JSON.parse(jsonStr);
      
      // Route response to waiting MCP client socket
      if (response.id && pendingRequests.has(response.id)) {
        const clientSocket = pendingRequests.get(response.id);
        pendingRequests.delete(response.id);

        if (!clientSocket.destroyed) {
          clientSocket.write(JSON.stringify(response) + '\n');
        }
      }
    } catch (err) {
      // Ignore JSON parse errors
    }
  }
});

process.stdin.on('end', () => {
  cleanup();
});

// 2. Local IPC Server for MCP Clients
if (isWindows) {
  if (existsSync(PORT_FILE)) {
    try {
      unlinkSync(PORT_FILE);
    } catch {}
  }
} else {
  if (existsSync(SOCKET_PATH)) {
    try {
      unlinkSync(SOCKET_PATH);
    } catch {}
  }
}

const server = net.createServer((clientSocket) => {
  let clientBuffer = '';

  clientSocket.on('data', (chunk) => {
    clientBuffer += chunk.toString('utf8');
    const lines = clientBuffer.split('\n');
    clientBuffer = lines.pop(); // Keep last incomplete line

    for (const line of lines) {
      if (!line.trim()) continue;
      try {
        const request = JSON.parse(line);
        if (request.id) {
          pendingRequests.set(request.id, clientSocket);
          sendNativeMessage(request);
        }
      } catch (err) {
        clientSocket.write(JSON.stringify({ success: false, error: 'Invalid JSON request' }) + '\n');
      }
    }
  });

  clientSocket.on('error', () => {});
});

if (isWindows) {
  server.listen(0, '127.0.0.1', () => {
    const addr = server.address();
    writeFileSync(PORT_FILE, String(addr.port), 'utf8');
    sendNativeMessage({ event: 'host_ready', port: addr.port });
  });
} else {
  server.listen(SOCKET_PATH, () => {
    // Signal ready to Chrome
    sendNativeMessage({ event: 'host_ready', socketPath: SOCKET_PATH });
  });
}

function cleanup() {
  try {
    if (isWindows) {
      if (existsSync(PORT_FILE)) unlinkSync(PORT_FILE);
    } else {
      if (existsSync(SOCKET_PATH)) unlinkSync(SOCKET_PATH);
    }
  } catch {}
  process.exit(0);
}

process.on('SIGINT', cleanup);
process.on('SIGTERM', cleanup);
process.on('exit', cleanup);
