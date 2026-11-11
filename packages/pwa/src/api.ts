/** API client for Animus Bootstrap dashboard backend. */

import { AuthError, clearToken, getToken } from "./auth";
import { API_BASE_URL, API_RETRY_COUNT, WS_BASE_URL } from "./config";

const BASE = API_BASE_URL;

async function request<T>(path: string, options?: RequestInit, attempt = 0): Promise<T> {
  const token = getToken();
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...((options?.headers as Record<string, string>) ?? {}),
  };
  if (token) headers["Authorization"] = `Bearer ${token}`;

  try {
    const res = await fetch(`${BASE}${path}`, { ...options, headers });
    if (res.status === 401) {
      clearToken();
      window.dispatchEvent(new Event("animus:unauthorized"));
      throw new AuthError();
    }
    if (!res.ok) {
      const text = await res.text().catch(() => res.statusText);
      // Retry on 5xx or network-like errors (0 status from fetch abort)
      if (attempt < API_RETRY_COUNT && (res.status >= 500 || res.status === 0)) {
        await new Promise((r) => setTimeout(r, 500 * (attempt + 1)));
        return request(path, options, attempt + 1);
      }
      throw new Error(`${res.status}: ${text}`);
    }
    return res.json() as Promise<T>;
  } catch (err) {
    // Retry on network failures (not HTTP errors handled above)
    if (attempt < API_RETRY_COUNT && err instanceof TypeError) {
      await new Promise((r) => setTimeout(r, 500 * (attempt + 1)));
      return request(path, options, attempt + 1);
    }
    throw err;
  }
}

// Health
export interface HealthResponse {
  status: string;
  version: string;
  components: {
    memory: boolean;
    tools: boolean;
    proactive: boolean;
    automations: boolean;
  };
}

export async function getHealth(): Promise<HealthResponse> {
  return request("/health");
}

// Citizens
export interface CitizenSummary {
  citizens_total: number;
  citizens_active: number;
  proposals_total: number;
  proposals_pending: number;
  proposals_approved: number;
  proposals_completed: number;
  core_available: boolean;
}

export interface CitizenProposal {
  id: string;
  title: string;
  problem: string;
  recommendation: string;
  confidence_score: number;
  confidence_label: string;
  estimated_effort_hours: number;
  affected_components: string[];
  status: string;
  source_citizen: string;
  created_at: string;
  evidence_count: number;
}

export async function getCitizensSummary(): Promise<CitizenSummary> {
  return request("/citizens/summary");
}

export async function getCitizenProposals(
  status?: string,
  citizen?: string,
): Promise<CitizenProposal[]> {
  const params = new URLSearchParams();
  if (status) params.set("status", status);
  if (citizen) params.set("citizen", citizen);
  const qs = params.toString();
  return request(`/citizens/proposals${qs ? "?" + qs : ""}`);
}

export async function approveProposal(proposalId: string): Promise<{ success: boolean }> {
  return request(`/citizens/proposals/${proposalId}/approve`, { method: "POST" });
}

export async function rejectProposal(proposalId: string): Promise<{ success: boolean }> {
  return request(`/citizens/proposals/${proposalId}/reject`, { method: "POST" });
}

export async function commissionProposal(proposalId: string): Promise<{
  success: boolean;
  error?: string;
  stage_reached?: string;
}> {
  return request(`/citizens/proposals/${proposalId}/commission`, { method: "POST" });
}

// Chat (REST fallback)
export async function sendMessage(text: string): Promise<{ text: string }> {
  return request("/conversations/messages", {
    method: "POST",
    body: JSON.stringify({ text }),
  });
}

// WebSocket chat
export type WSMessage = {
  id: string;
  channel: string;
  text: string;
  timestamp: string;
  sender: string;
  role?: string;
  metadata: Record<string, unknown>;
};

export type OnWSMessage = (msg: WSMessage) => void;

export function connectChat(onMessage: OnWSMessage): {
  send: (text: string) => void;
  close: () => void;
  getState: () => number;
  getPendingCount: () => number;
} {
  const proto = location.protocol === "https:" ? "wss:" : "ws:";
  const token = getToken();
  const query = token ? `?token=${encodeURIComponent(token)}` : "";
  const wsPath = WS_BASE_URL.startsWith("/")
    ? `${proto}//${location.host}${WS_BASE_URL}/chat${query}`
    : `${WS_BASE_URL}/chat${query}`;
  const ws = new WebSocket(wsPath);
  const pending: string[] = [];

  ws.onopen = () => {
    while (pending.length > 0) {
      const text = pending.shift()!;
      ws.send(JSON.stringify({ text, sender_id: "pwa-user", sender_name: "User" }));
    }
  };

  ws.onmessage = (event) => {
    try {
      const msg = JSON.parse(event.data) as WSMessage;
      onMessage(msg);
    } catch {
      // ignore malformed messages
    }
  };

  return {
    send: (text: string) => {
      if (ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ text, sender_id: "pwa-user", sender_name: "User" }));
      } else {
        pending.push(text);
      }
    },
    close: () => ws.close(),
    getState: () => ws.readyState,
    getPendingCount: () => pending.length,
  };
}

// Conversation history (persisted server-side)
export async function getHistory(limit = 50): Promise<WSMessage[]> {
  return request(`/conversations/history?limit=${limit}`);
}

// Personas
export interface Persona {
  id: string;
  name: string;
  description: string;
  tone: string;
  active: boolean;
  is_default: boolean;
  knowledge_domains: string[];
}

export async function listPersonas(): Promise<Persona[]> {
  return request("/personas");
}

export async function createPersona(data: Partial<Persona>): Promise<{ id: string }> {
  return request("/personas", {
    method: "POST",
    body: JSON.stringify(data),
  });
}

export async function deletePersona(id: string): Promise<void> {
  await request(`/personas/${id}`, { method: "DELETE" });
}

// Feedback
export async function submitFeedback(rating: number, messageText: string): Promise<void> {
  await request("/feedback", {
    method: "POST",
    body: JSON.stringify({ rating, message_text: messageText }),
  });
}

// Quick capture
export async function captureNote(text: string): Promise<{ ok: boolean; message: string }> {
  return request("/capture", {
    method: "POST",
    body: JSON.stringify({ text }),
  });
}

// Web Push
export async function getVapidPublicKey(): Promise<string> {
  const res = await request<{ publicKey: string }>("/push/vapid-public-key");
  return res.publicKey;
}

export async function subscribePush(subscription: PushSubscriptionJSON): Promise<void> {
  await request("/push/subscribe", {
    method: "POST",
    body: JSON.stringify({ subscription }),
  });
}

export async function unsubscribePush(endpoint: string): Promise<void> {
  await request("/push/unsubscribe", {
    method: "POST",
    body: JSON.stringify({ endpoint }),
  });
}

export async function sendTestPush(title: string, body: string, url?: string): Promise<{ sent: number; pruned: number; detail?: string }> {
  return request("/push/send-test", {
    method: "POST",
    body: JSON.stringify({ title, body, url: url ?? "/" }),
  });
}

// Session continuity (checkpoint load/save)
export interface CheckpointPayload {
  available?: boolean;
  session_id?: string;
  messages: { role: string; content: string }[];
  summary: string;
  turns: number;
}

export async function loadCheckpoint(): Promise<CheckpointPayload | null> {
  try {
    return await request<CheckpointPayload>("/session/checkpoint");
  } catch {
    return null;
  }
}

export async function saveCheckpoint(payload: CheckpointPayload): Promise<void> {
  await request("/session/checkpoint", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}
