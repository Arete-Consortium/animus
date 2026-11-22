import { useEffect, useState } from "react";
import { ChatView } from "./views/Chat";
import { StatusView } from "./views/Status";
import { PersonasView } from "./views/Personas";
import { CaptureView } from "./views/Capture";
import { CitizensView } from "./views/Citizens";
import { ToolsView } from "./views/Tools";
import { LoginView } from "./views/Login";
import { ErrorBoundary } from "./components/ErrorBoundary";
import { getToken } from "./auth";
import "./App.css";

type View = "chat" | "capture" | "status" | "personas" | "citizens" | "tools";

/** Read text shared into the app via the manifest share_target (?title/text/url). */
function readSharedText(): string {
  const params = new URLSearchParams(window.location.search);
  const parts = [params.get("title"), params.get("text"), params.get("url")].filter(
    (p): p is string => !!p,
  );
  return parts.join("\n");
}

export function App() {
  const [sharedText] = useState(readSharedText);
  const [view, setView] = useState<View>(() => (sharedText ? "capture" : "chat"));
  const [authed, setAuthed] = useState<boolean>(() => getToken() !== null);
  const [online, setOnline] = useState<boolean>(() => navigator.onLine);

  useEffect(() => {
    const onUnauthorized = () => setAuthed(false);
    window.addEventListener("animus:unauthorized", onUnauthorized);
    return () => window.removeEventListener("animus:unauthorized", onUnauthorized);
  }, []);

  useEffect(() => {
    const onOnline = () => setOnline(true);
    const onOffline = () => setOnline(false);
    window.addEventListener("online", onOnline);
    window.addEventListener("offline", onOffline);
    return () => {
      window.removeEventListener("online", onOnline);
      window.removeEventListener("offline", onOffline);
    };
  }, []);

  if (!authed) {
    return (
      <div className="app">
        <main className="app-main">
          <LoginView onAuthed={() => setAuthed(true)} />
        </main>
      </div>
    );
  }

  return (
    <div className="app">
      {!online && (
        <div className="app-offline-banner">Offline — changes will sync when reconnected</div>
      )}
      <main className="app-main">
        <ErrorBoundary>
          {view === "chat" && <ChatView />}
          {view === "capture" && <CaptureView initialText={sharedText} />}
          {view === "status" && <StatusView />}
          {view === "personas" && <PersonasView />}
          {view === "citizens" && <CitizensView />}
          {view === "tools" && <ToolsView />}
        </ErrorBoundary>
      </main>

      <nav className="app-nav">
        <NavButton
          icon="💬"
          label="Chat"
          active={view === "chat"}
          onClick={() => setView("chat")}
        />
        <NavButton
          icon="📝"
          label="Capture"
          active={view === "capture"}
          onClick={() => setView("capture")}
        />
        <NavButton
          icon="📊"
          label="Status"
          active={view === "status"}
          onClick={() => setView("status")}
        />
        <NavButton
          icon="🎭"
          label="Personas"
          active={view === "personas"}
          onClick={() => setView("personas")}
        />
        <NavButton
          icon="🏛️"
          label="Citizens"
          active={view === "citizens"}
          onClick={() => setView("citizens")}
        />
        <NavButton
          icon="🧰"
          label="Tools"
          active={view === "tools"}
          onClick={() => setView("tools")}
        />
      </nav>
    </div>
  );
}

function NavButton({
  icon,
  label,
  active,
  onClick,
}: {
  icon: string;
  label: string;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      className={`nav-btn ${active ? "nav-btn--active" : ""}`}
      onClick={onClick}
    >
      <span className="nav-btn-icon">{icon}</span>
      <span className="nav-btn-label">{label}</span>
    </button>
  );
}
