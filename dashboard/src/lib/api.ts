// ============================================================
// 🚦 Central API Configuration
// ============================================================
// In production (Vercel), these read from NEXT_PUBLIC_* env vars
// pointing to your Render.com service URLs.
// In development, they fall back to localhost ports.

export const API = {
  VEHICLE_REGISTRY: process.env.NEXT_PUBLIC_VEHICLE_REGISTRY_URL || 'http://localhost:8006',
  EDGE_REGISTRY:    process.env.NEXT_PUBLIC_EDGE_REGISTRY_URL    || 'http://localhost:8002',
  EVENT_SERVICE:    process.env.NEXT_PUBLIC_EVENT_SERVICE_URL     || 'http://localhost:8001',
  PRIORITY_QUEUE:   process.env.NEXT_PUBLIC_PRIORITY_QUEUE_URL   || 'http://localhost:8004',
  ROUTE_ENGINE:     process.env.NEXT_PUBLIC_ROUTE_ENGINE_URL     || 'http://localhost:8003',
  OTA_SERVICE:      process.env.NEXT_PUBLIC_OTA_SERVICE_URL      || 'http://localhost:8005',
} as const;

// WebSocket URL for the live event stream
// Defaults to ws:// for local dev; set to wss:// in production
export const WS_EVENT_STREAM =
  process.env.NEXT_PUBLIC_EVENT_WS_URL || 'ws://localhost:8001/api/v1/stream';
