import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import {
  getHealth,
  sendMessage,
  connectChat,
  getHistory,
  listPersonas,
  createPersona,
  deletePersona,
  submitFeedback,
  captureNote,
  getVapidPublicKey,
  subscribePush,
  unsubscribePush,
  loadCheckpoint,
  saveCheckpoint,
  getCitizensSummary,
  getCitizenProposals,
  type HealthResponse,
  type Persona,
  type CheckpointPayload,
} from "./api";

describe("api", () => {
  let fetchSpy: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    localStorage.clear();
    fetchSpy = vi.spyOn(globalThis, "fetch").mockImplementation(async () => {
      return new Response(JSON.stringify({ ok: true }), { status: 200 });
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
    localStorage.clear();
  });

  const mockJsonResponse = (data: unknown, status = 200) => {
    fetchSpy.mockResolvedValueOnce(
      new Response(JSON.stringify(data), {
        status,
        headers: { "Content-Type": "application/json" },
      })
    );
  };

  describe("getHealth", () => {
    it("fetches /health and returns parsed JSON", async () => {
      const health: HealthResponse = {
        status: "ok",
        version: "1.0.0",
        components: { memory: true, tools: true, proactive: false, automations: true },
      };
      mockJsonResponse(health);
      const result = await getHealth();
      expect(result).toEqual(health);
      expect(fetchSpy).toHaveBeenCalledWith(
        expect.stringContaining("/health"),
        expect.objectContaining({ headers: expect.any(Object) })
      );
    });
  });

  describe("sendMessage", () => {
    it("POSTs text to /conversations/messages", async () => {
      mockJsonResponse({ text: "reply" });
      await sendMessage("hello");
      expect(fetchSpy).toHaveBeenCalledWith(
        expect.stringContaining("/conversations/messages"),
        expect.objectContaining({ method: "POST" })
      );
      const call = fetchSpy.mock.calls[0];
      const body = JSON.parse((call[1] as RequestInit).body as string);
      expect(body.text).toBe("hello");
    });
  });

  describe("getHistory", () => {
    it("fetches history with default limit", async () => {
      mockJsonResponse([]);
      await getHistory();
      expect(fetchSpy).toHaveBeenCalledWith(
        expect.stringContaining("/conversations/history?limit=50"),
        expect.anything()
      );
    });

    it("fetches history with custom limit", async () => {
      mockJsonResponse([]);
      await getHistory(10);
      expect(fetchSpy).toHaveBeenCalledWith(
        expect.stringContaining("/conversations/history?limit=10"),
        expect.anything()
      );
    });
  });

  describe("persona CRUD", () => {
    it("lists personas", async () => {
      const personas: Persona[] = [{ id: "1", name: "Test", description: "", tone: "", active: true, is_default: false, knowledge_domains: [] }];
      mockJsonResponse(personas);
      const result = await listPersonas();
      expect(result).toEqual(personas);
      expect(fetchSpy).toHaveBeenCalledWith(expect.stringContaining("/personas"), expect.anything());
    });

    it("creates a persona", async () => {
      mockJsonResponse({ id: "new-id" });
      await createPersona({ name: "New" });
      expect(fetchSpy).toHaveBeenCalledWith(
        expect.stringContaining("/personas"),
        expect.objectContaining({ method: "POST" })
      );
    });

    it("deletes a persona", async () => {
      mockJsonResponse({});
      await deletePersona("123");
      expect(fetchSpy).toHaveBeenCalledWith(
        expect.stringContaining("/personas/123"),
        expect.objectContaining({ method: "DELETE" })
      );
    });
  });

  describe("submitFeedback", () => {
    it("POSTs feedback", async () => {
      mockJsonResponse({});
      await submitFeedback(5, "Great!");
      const call = fetchSpy.mock.calls[0];
      const body = JSON.parse((call[1] as RequestInit).body as string);
      expect(body.rating).toBe(5);
      expect(body.message_text).toBe("Great!");
    });
  });

  describe("captureNote", () => {
    it("POSTs capture text", async () => {
      mockJsonResponse({ ok: true, message: "Captured" });
      const result = await captureNote("note");
      expect(result.ok).toBe(true);
      const call = fetchSpy.mock.calls[0];
      const body = JSON.parse((call[1] as RequestInit).body as string);
      expect(body.text).toBe("note");
    });
  });

  describe("push notifications", () => {
    it("gets VAPID public key", async () => {
      mockJsonResponse({ publicKey: "key123" });
      const key = await getVapidPublicKey();
      expect(key).toBe("key123");
    });

    it("subscribes push", async () => {
      mockJsonResponse({});
      const sub = { endpoint: "https://push.example.com/1" } as PushSubscriptionJSON;
      await subscribePush(sub);
      const call = fetchSpy.mock.calls[0];
      expect(call[0]).toContain("/push/subscribe");
    });

    it("unsubscribes push", async () => {
      mockJsonResponse({});
      await unsubscribePush("https://push.example.com/1");
      const call = fetchSpy.mock.calls[0];
      expect(call[0]).toContain("/push/unsubscribe");
    });
  });

  describe("checkpoint", () => {
    it("loads checkpoint", async () => {
      const payload: CheckpointPayload = { session_id: "s1", messages: [], summary: "", turns: 0 };
      mockJsonResponse(payload);
      const result = await loadCheckpoint();
      expect(result).toEqual(payload);
    });

    it("returns null on load failure", async () => {
      fetchSpy.mockRejectedValueOnce(new Error("network"));
      const result = await loadCheckpoint();
      expect(result).toBeNull();
    });

    it("saves checkpoint", async () => {
      mockJsonResponse({});
      const payload: CheckpointPayload = { messages: [{ role: "user", content: "hi" }], summary: "", turns: 1 };
      await saveCheckpoint(payload);
      expect(fetchSpy).toHaveBeenCalledWith(
        expect.stringContaining("/session/checkpoint"),
        expect.objectContaining({ method: "POST" })
      );
    });
  });

  describe("request retries and auth", () => {
    it("retries on 5xx errors up to API_RETRY_COUNT times", async () => {
      // Default API_RETRY_COUNT is 1: first fails, second succeeds
      fetchSpy
        .mockResolvedValueOnce(new Response("error", { status: 500 }))
        .mockResolvedValueOnce(new Response(JSON.stringify({ status: "ok" }), { status: 200 }));

      const result = await getHealth();
      expect(result).toEqual({ status: "ok" });
      expect(fetchSpy).toHaveBeenCalledTimes(2);
    });

    it("dispatches unauthorized event on 401 and throws AuthError", async () => {
      const dispatchSpy = vi.spyOn(window, "dispatchEvent").mockImplementation(() => true);
      fetchSpy.mockResolvedValueOnce(new Response("Unauthorized", { status: 401 }));

      await expect(getHealth()).rejects.toThrow("Authentication required");
      expect(dispatchSpy).toHaveBeenCalledWith(expect.any(Event));
      const dispatchedEvent = dispatchSpy.mock.calls[0]?.[0];
      expect(dispatchedEvent?.type).toBe("animus:unauthorized");
      dispatchSpy.mockRestore();
    });

    it("includes bearer token when present", async () => {
      localStorage.setItem("animus_token", "tk-abc");
      mockJsonResponse({ status: "ok" });
      await getHealth();
      const call = fetchSpy.mock.calls[0];
      const headers = (call[1] as RequestInit).headers as Record<string, string>;
      expect(headers["Authorization"]).toBe("Bearer tk-abc");
    });
  });

  describe("citizens", () => {
    it("requests citizen summary under the configured API mount once", async () => {
      mockJsonResponse({ citizens_total: 0, core_available: true });

      await getCitizensSummary();

      expect(fetchSpy).toHaveBeenCalledWith(
        "/api/citizens/summary",
        expect.objectContaining({ headers: expect.any(Object) })
      );
    });

    it("requests citizen proposals without duplicating the API mount", async () => {
      mockJsonResponse([]);

      await getCitizenProposals("pending_review");

      expect(fetchSpy).toHaveBeenCalledWith(
        "/api/citizens/proposals?status=pending_review",
        expect.objectContaining({ headers: expect.any(Object) })
      );
    });
  });

  describe("connectChat", () => {
    it("returns send/close/getState/getPendingCount", () => {
      // Minimal WebSocket mock
      const mockWs = {
        readyState: 1, // OPEN
        send: vi.fn(),
        close: vi.fn(),
        onopen: null as unknown as (() => void) | null,
        onmessage: null as unknown as ((e: { data: string }) => void) | null,
      };
      const OriginalWebSocket = globalThis.WebSocket;
      let wsUrl = "";
      let wsProtocols: string[] = [];
      const mockWebSocket = function (url: string, protocols: string[]) {
        wsUrl = url;
        wsProtocols = protocols;
        return mockWs;
      } as unknown as typeof WebSocket & { OPEN: number };
      mockWebSocket.OPEN = 1;
      globalThis.WebSocket = mockWebSocket;

      localStorage.setItem("animus_token", "test-token-123");
      const onMsg = vi.fn();
      const chat = connectChat(onMsg);

      expect(wsUrl).not.toContain("test-token-123");
      expect(wsProtocols).toEqual(["animus-chat", "animus-auth.test-token-123"]);
      expect(chat.getState()).toBe(1);
      expect(chat.getPendingCount()).toBe(0);

      chat.send("hello");
      expect(mockWs.send).toHaveBeenCalled();

      chat.close();
      expect(mockWs.close).toHaveBeenCalled();

      globalThis.WebSocket = OriginalWebSocket;
    });
  });
});
