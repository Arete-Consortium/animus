import { useMemo, useState } from "react";
import "./Tools.css";

type ToolCategory = "Harness" | "Model" | "Memory";

interface ToolRecord {
  name: string;
  category: ToolCategory;
  state: string;
  source: string;
  lastVerified: string;
}

const EXAMPLE_TOOLS: ToolRecord[] = [
  { name: "Forgehand", category: "Harness", state: "Example only", source: "Local handoff", lastVerified: "Not connected" },
  { name: "Animus", category: "Model", state: "Example only", source: "PWA shell", lastVerified: "Not connected" },
  { name: "Memboot", category: "Memory", state: "Example only", source: "Local notes", lastVerified: "Not connected" },
];

const CATEGORIES: Array<"All" | ToolCategory> = ["All", "Harness", "Model", "Memory"];

export function ToolsView() {
  const [category, setCategory] = useState<"All" | ToolCategory>("All");
  const visibleTools = useMemo(
    () => (category === "All" ? EXAMPLE_TOOLS : EXAMPLE_TOOLS.filter((tool) => tool.category === category)),
    [category],
  );

  return (
    <section className="tools-view" aria-labelledby="tools-heading">
      <header className="tools-header">
        <p className="tools-eyebrow">Read-only dashboard shell</p>
        <h1 id="tools-heading">AI tools</h1>
        <p>Example inventory data only. No live inventory connector is connected yet.</p>
      </header>

      <label className="tools-filter">
        <span>Filter by category</span>
        <select value={category} onChange={(event) => setCategory(event.target.value as "All" | ToolCategory)}>
          {CATEGORIES.map((option) => <option key={option} value={option}>{option}</option>)}
        </select>
      </label>

      <div className="tools-list" aria-live="polite">
        {visibleTools.map((tool) => (
          <article className="tool-card" key={tool.name}>
            <div className="tool-card-heading">
              <h2>{tool.name}</h2>
              <span className="tool-badge">Example</span>
            </div>
            <dl>
              <div><dt>Category</dt><dd>{tool.category}</dd></div>
              <div><dt>State</dt><dd>{tool.state}</dd></div>
              <div><dt>Source</dt><dd>{tool.source}</dd></div>
              <div><dt>Last verified</dt><dd>{tool.lastVerified}</dd></div>
            </dl>
          </article>
        ))}
      </div>
    </section>
  );
}
