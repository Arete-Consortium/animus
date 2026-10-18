use chrono::{DateTime, Utc};
use rusqlite::{params, Connection, Result as SqlResult};
use serde_json;

use crate::models::{
    Adjustment, AdjustmentKind, ConflictReport, Constraint, IntentNode, InterfaceSpec,
    ResolutionResult,
};
use crate::stability::StabilityScorer;

/// The shared intent graph. Append-only, SQLite-backed.
/// All agents read from and write to this structure.
///
/// # Interior mutability
///
/// Methods like [`publish`](Self::publish) take `&self` despite mutating SQLite.
/// This is intentional: SQLite provides its own internal locking and transaction
/// safety, making the `Connection` effectively an interior-mutable handle (like
/// `RefCell` but with database-level guarantees). Using `&self` allows multiple
/// readers to coexist with a single writer without requiring `&mut self` at the
/// Rust level, which mirrors the actual concurrency model of the graph — many
/// agents reading, one writing at a time, serialized by SQLite's WAL.
pub struct IntentGraph {
    conn: Connection,
    scorer: StabilityScorer,
}

impl IntentGraph {
    /// Create a new intent graph backed by an in-memory SQLite database.
    pub fn in_memory() -> SqlResult<Self> {
        let conn = Connection::open_in_memory()?;
        let graph = Self {
            conn,
            scorer: StabilityScorer::new(),
        };
        graph.init_schema()?;
        Ok(graph)
    }

    /// Create a new intent graph backed by a file-based SQLite database.
    pub fn persistent(path: &str) -> SqlResult<Self> {
        let conn = Connection::open(path)?;
        let graph = Self {
            conn,
            scorer: StabilityScorer::new(),
        };
        graph.init_schema()?;
        Ok(graph)
    }

    fn init_schema(&self) -> SqlResult<()> {
        self.conn.execute_batch(
            "
            CREATE TABLE IF NOT EXISTS intents (
                id TEXT PRIMARY KEY,
                agent_id TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                intent TEXT NOT NULL,
                provides TEXT NOT NULL,      -- JSON array of InterfaceSpec
                requires TEXT NOT NULL,      -- JSON array of InterfaceSpec
                constraints TEXT NOT NULL,   -- JSON array of Constraint
                stability REAL NOT NULL,
                evidence TEXT NOT NULL,      -- JSON array of Evidence
                parent_id TEXT,
                computed_stability REAL,
                FOREIGN KEY (parent_id) REFERENCES intents(id)
            );

            CREATE INDEX IF NOT EXISTS idx_intents_agent ON intents(agent_id);
            CREATE INDEX IF NOT EXISTS idx_intents_stability ON intents(computed_stability);
            CREATE INDEX IF NOT EXISTS idx_intents_timestamp ON intents(timestamp);

            -- Denormalized interface lookup table for O(1) overlap queries.
            -- Avoids deserializing all intent JSON to check structural overlap.
            CREATE TABLE IF NOT EXISTS intent_interfaces (
                intent_id TEXT NOT NULL,
                agent_id TEXT NOT NULL,
                normalized_name TEXT NOT NULL,
                role TEXT NOT NULL,           -- 'provides' or 'requires'
                tags TEXT NOT NULL,           -- space-separated for FTS-like matching
                FOREIGN KEY (intent_id) REFERENCES intents(id)
            );

            CREATE INDEX IF NOT EXISTS idx_ifaces_name ON intent_interfaces(normalized_name);
            CREATE INDEX IF NOT EXISTS idx_ifaces_agent ON intent_interfaces(agent_id);
            CREATE INDEX IF NOT EXISTS idx_ifaces_intent ON intent_interfaces(intent_id);
            ",
        )?;
        Ok(())
    }

    /// Publish an intent to the graph. Append-only — once published, cannot be modified.
    /// Returns the computed stability score.
    ///
    /// Also populates the denormalized `intent_interfaces` table for fast
    /// overlap queries (see [`find_overlapping`](Self::find_overlapping)).
    pub fn publish(&self, intent: &IntentNode) -> SqlResult<f64> {
        let computed_stability = self.scorer.compute(intent);

        self.conn.execute(
            "INSERT INTO intents (id, agent_id, timestamp, intent, provides, requires,
             constraints, stability, evidence, parent_id, computed_stability)
             VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9, ?10, ?11)",
            params![
                intent.id,
                intent.agent_id,
                intent.timestamp.to_rfc3339(),
                intent.intent,
                serde_json::to_string(&intent.provides).unwrap_or_default(),
                serde_json::to_string(&intent.requires).unwrap_or_default(),
                serde_json::to_string(&intent.constraints).unwrap_or_default(),
                intent.stability,
                serde_json::to_string(&intent.evidence).unwrap_or_default(),
                intent.parent_id,
                computed_stability,
            ],
        )?;

        // Populate denormalized interface lookup table
        self.index_interfaces(intent, "provides", &intent.provides)?;
        self.index_interfaces(intent, "requires", &intent.requires)?;

        Ok(computed_stability)
    }

    /// Insert denormalized interface entries for fast overlap lookup.
    fn index_interfaces(
        &self,
        intent: &IntentNode,
        role: &str,
        specs: &[InterfaceSpec],
    ) -> SqlResult<()> {
        for spec in specs {
            let normalized = crate::matching::normalize_name(&spec.name);
            let tags_str = spec.tags.join(" ");
            self.conn.execute(
                "INSERT INTO intent_interfaces (intent_id, agent_id, normalized_name, role, tags)
                 VALUES (?1, ?2, ?3, ?4, ?5)",
                params![intent.id, intent.agent_id, normalized, role, tags_str],
            )?;
        }
        Ok(())
    }

    /// Query all intents, optionally filtered by minimum stability.
    pub fn query_all(&self, min_stability: Option<f64>) -> SqlResult<Vec<IntentNode>> {
        let min_stab = min_stability.unwrap_or(0.0);
        let mut stmt = self.conn.prepare(
            "SELECT id, agent_id, timestamp, intent, provides, requires,
                    constraints, stability, evidence, parent_id, computed_stability
             FROM intents
             WHERE computed_stability >= ?1
             ORDER BY timestamp ASC",
        )?;

        let intents = stmt
            .query_map(params![min_stab], |row| Ok(self.row_to_intent(row)))?
            .filter_map(|r| r.ok())
            .collect();

        Ok(intents)
    }

    /// Query intents from a specific agent.
    pub fn query_by_agent(&self, agent_id: &str) -> SqlResult<Vec<IntentNode>> {
        let mut stmt = self.conn.prepare(
            "SELECT id, agent_id, timestamp, intent, provides, requires,
                    constraints, stability, evidence, parent_id, computed_stability
             FROM intents
             WHERE agent_id = ?1
             ORDER BY timestamp ASC",
        )?;

        let intents = stmt
            .query_map(params![agent_id], |row| Ok(self.row_to_intent(row)))?
            .filter_map(|r| r.ok())
            .collect();

        Ok(intents)
    }

    /// Query intents published after a given timestamp.
    pub fn query_since(
        &self,
        since: DateTime<Utc>,
        min_stability: Option<f64>,
    ) -> SqlResult<Vec<IntentNode>> {
        let min_stab = min_stability.unwrap_or(0.0);
        let mut stmt = self.conn.prepare(
            "SELECT id, agent_id, timestamp, intent, provides, requires,
                    constraints, stability, evidence, parent_id, computed_stability
             FROM intents
             WHERE timestamp > ?1 AND computed_stability >= ?2
             ORDER BY timestamp ASC",
        )?;

        let intents = stmt
            .query_map(params![since.to_rfc3339(), min_stab], |row| {
                Ok(self.row_to_intent(row))
            })?
            .filter_map(|r| r.ok())
            .collect();

        Ok(intents)
    }

    /// Find all intents that provide or require interfaces overlapping with the given specs.
    /// This is the core query for the intent resolver.
    ///
    /// Uses the denormalized `intent_interfaces` table for a fast first-pass
    /// candidate filter (indexed name/tag lookup), then validates candidates
    /// with full structural overlap checks. This avoids the O(n) JSON
    /// deserialization scan that the naive approach requires.
    pub fn find_overlapping(
        &self,
        specs: &[InterfaceSpec],
        exclude_agent: &str,
        min_stability: f64,
    ) -> SqlResult<Vec<IntentNode>> {
        if specs.is_empty() {
            return Ok(Vec::new());
        }

        // Phase 1: Fast indexed candidate lookup via denormalized table.
        // Find intent IDs that have matching normalized names or >=2 shared tags.
        let mut candidate_ids: std::collections::HashSet<String> = std::collections::HashSet::new();

        for spec in specs {
            let normalized = crate::matching::normalize_name(&spec.name);

            // Name-based candidates: normalized name overlap
            let mut name_stmt = self.conn.prepare(
                "SELECT DISTINCT ii.intent_id
                 FROM intent_interfaces ii
                 JOIN intents i ON i.id = ii.intent_id
                 WHERE ii.agent_id != ?1
                   AND i.computed_stability >= ?2
                   AND (ii.normalized_name = ?3
                        OR ii.normalized_name LIKE ?4
                        OR ?3 LIKE '%' || ii.normalized_name || '%')",
            )?;

            let pattern = format!("%{}%", normalized);
            let rows = name_stmt.query_map(
                params![exclude_agent, min_stability, normalized, pattern],
                |row| row.get::<_, String>(0),
            )?;
            for id in rows.flatten() {
                candidate_ids.insert(id);
            }

            // Tag-based candidates: >=2 shared tags
            if spec.tags.len() >= 2 {
                for tag in &spec.tags {
                    let mut tag_stmt = self.conn.prepare(
                        "SELECT DISTINCT ii.intent_id
                         FROM intent_interfaces ii
                         JOIN intents i ON i.id = ii.intent_id
                         WHERE ii.agent_id != ?1
                           AND i.computed_stability >= ?2
                           AND ii.tags LIKE ?3",
                    )?;
                    let tag_pattern = format!("%{}%", tag);
                    let rows = tag_stmt
                        .query_map(params![exclude_agent, min_stability, tag_pattern], |row| {
                            row.get::<_, String>(0)
                        })?;
                    for id in rows.flatten() {
                        candidate_ids.insert(id);
                    }
                }
            }
        }

        if candidate_ids.is_empty() {
            return Ok(Vec::new());
        }

        // Phase 2: Load candidate intents and verify with full structural check.
        let all_candidates = self.query_all(Some(min_stability))?;
        let overlapping: Vec<IntentNode> = all_candidates
            .into_iter()
            .filter(|intent| candidate_ids.contains(&intent.id))
            .filter(|intent| {
                let their_specs: Vec<&InterfaceSpec> = intent
                    .provides
                    .iter()
                    .chain(intent.requires.iter())
                    .collect();

                specs.iter().any(|my_spec| {
                    their_specs
                        .iter()
                        .any(|their_spec| my_spec.structurally_overlaps(their_spec))
                })
            })
            .collect();

        Ok(overlapping)
    }

    /// Find constraints from other agents that apply to the given intent.
    pub fn find_applicable_constraints(
        &self,
        intent: &IntentNode,
        min_stability: f64,
    ) -> SqlResult<Vec<(Constraint, String, f64)>> {
        // Returns (constraint, source_intent_id, source_stability)
        let all = self.query_all(Some(min_stability))?;

        let applicable: Vec<(Constraint, String, f64)> = all
            .into_iter()
            .filter(|other| other.agent_id != intent.agent_id)
            .flat_map(|other| {
                let id = other.id.clone();
                let stability = self.scorer.compute(&other);
                other
                    .constraints
                    .into_iter()
                    .filter(|c| c.applies_to(intent))
                    .map(move |c| (c, id.clone(), stability))
            })
            .collect();

        Ok(applicable)
    }

    /// Resolve an intent against the current graph state.
    /// Returns adjustments the agent should make for compatibility.
    pub fn resolve(&self, intent: &IntentNode, min_stability: f64) -> SqlResult<ResolutionResult> {
        let mut adjustments = Vec::new();
        let mut conflicts = Vec::new();
        let mut adopted_constraints = Vec::new();

        // 1. Find overlapping provisions — avoid duplication
        let my_specs: Vec<InterfaceSpec> = intent
            .provides
            .iter()
            .chain(intent.requires.iter())
            .cloned()
            .collect();

        let overlapping = self.find_overlapping(&my_specs, &intent.agent_id, min_stability)?;

        for other in &overlapping {
            let other_stability = self.scorer.compute(other);

            // Check for duplicate provisions
            for my_provision in &intent.provides {
                for their_provision in &other.provides {
                    if my_provision.structurally_overlaps(their_provision) {
                        if other_stability > self.scorer.compute(intent) {
                            // They're more committed — consume theirs
                            adjustments.push(Adjustment {
                                kind: AdjustmentKind::ConsumeInstead,
                                description: format!(
                                    "Drop '{}', consume '{}' from agent {} (stability {:.2})",
                                    my_provision.name,
                                    their_provision.name,
                                    other.agent_id,
                                    other_stability
                                ),
                                source_intent_id: other.id.clone(),
                            });
                        } else {
                            // We're more committed or equal — report conflict
                            conflicts.push(ConflictReport {
                                my_intent_id: intent.id.clone(),
                                their_intent_id: other.id.clone(),
                                description: format!(
                                    "Both provide '{}' — my stability {:.2} vs their {:.2}",
                                    my_provision.name,
                                    self.scorer.compute(intent),
                                    other_stability,
                                ),
                                their_stability: other_stability,
                                resolution_suggestion:
                                    "Higher stability should provide; other should consume"
                                        .to_string(),
                            });
                        }
                    }
                }
            }

            // Check for interface signature mismatches in required→provided pairs
            for my_requirement in &intent.requires {
                for their_provision in &other.provides {
                    if my_requirement.structurally_overlaps(their_provision)
                        && !my_requirement.signature_compatible(their_provision)
                        && other_stability > self.scorer.compute(intent)
                    {
                        adjustments.push(Adjustment {
                            kind: AdjustmentKind::AdaptSignature,
                            description: format!(
                                "Adapt '{}' signature to match '{}' from agent {} — \
                                     expected '{}', they provide '{}'",
                                my_requirement.name,
                                their_provision.name,
                                other.agent_id,
                                my_requirement.signature,
                                their_provision.signature,
                            ),
                            source_intent_id: other.id.clone(),
                        });
                    }
                }
            }
        }

        // 2. Find applicable constraints from other agents
        let applicable = self.find_applicable_constraints(intent, min_stability)?;

        for (constraint, source_id, _source_stability) in applicable {
            // Check if this constraint conflicts with our own constraints
            let has_conflict = intent
                .constraints
                .iter()
                .any(|my_c| my_c.conflicts_with(&constraint));

            if has_conflict {
                conflicts.push(ConflictReport {
                    my_intent_id: intent.id.clone(),
                    their_intent_id: source_id.clone(),
                    description: format!(
                        "Constraint conflict on '{}': my requirement vs their requirement",
                        constraint.target
                    ),
                    their_stability: _source_stability,
                    resolution_suggestion: "Higher stability constraint should win".to_string(),
                });
            } else {
                adopted_constraints.push(constraint.clone());
                adjustments.push(Adjustment {
                    kind: AdjustmentKind::AdoptConstraint,
                    description: format!(
                        "Adopt constraint: {} — {}",
                        constraint.target, constraint.requirement
                    ),
                    source_intent_id: source_id,
                });
            }
        }

        Ok(ResolutionResult {
            original_intent: intent.id.clone(),
            adjustments,
            conflicts,
            adopted_constraints,
        })
    }

    /// Get a count of all intents in the graph.
    pub fn count(&self) -> SqlResult<usize> {
        let count: i64 = self
            .conn
            .query_row("SELECT COUNT(*) FROM intents", [], |row| row.get(0))?;
        Ok(count as usize)
    }

    /// Get a snapshot summary of the graph state.
    pub fn summary(&self) -> SqlResult<GraphSummary> {
        let total = self.count()?;
        let all = self.query_all(None)?;

        let agents: Vec<String> = {
            let mut ids: Vec<String> = all.iter().map(|i| i.agent_id.clone()).collect();
            ids.sort();
            ids.dedup();
            ids
        };

        let avg_stability = if all.is_empty() {
            0.0
        } else {
            all.iter().map(|i| self.scorer.compute(i)).sum::<f64>() / all.len() as f64
        };

        let high_stability = all.iter().filter(|i| self.scorer.compute(i) >= 0.7).count();

        Ok(GraphSummary {
            total_intents: total,
            agent_count: agents.len(),
            agents,
            average_stability: avg_stability,
            high_stability_count: high_stability,
        })
    }

    fn row_to_intent(&self, row: &rusqlite::Row) -> IntentNode {
        let provides_json: String = row.get(4).unwrap_or_default();
        let requires_json: String = row.get(5).unwrap_or_default();
        let constraints_json: String = row.get(6).unwrap_or_default();
        let evidence_json: String = row.get(8).unwrap_or_default();

        IntentNode {
            id: row.get(0).unwrap_or_default(),
            agent_id: row.get(1).unwrap_or_default(),
            timestamp: row
                .get::<_, String>(2)
                .ok()
                .and_then(|s| DateTime::parse_from_rfc3339(&s).ok())
                .map(|dt| dt.with_timezone(&Utc))
                .unwrap_or_else(Utc::now),
            intent: row.get(3).unwrap_or_default(),
            provides: serde_json::from_str(&provides_json).unwrap_or_default(),
            requires: serde_json::from_str(&requires_json).unwrap_or_default(),
            constraints: serde_json::from_str(&constraints_json).unwrap_or_default(),
            stability: row.get(7).unwrap_or(0.3),
            evidence: serde_json::from_str(&evidence_json).unwrap_or_default(),
            parent_id: row.get(9).ok(),
        }
    }
}

#[derive(Debug, Clone)]
pub struct GraphSummary {
    pub total_intents: usize,
    pub agent_count: usize,
    pub agents: Vec<String>,
    pub average_stability: f64,
    pub high_stability_count: usize,
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::models::{Evidence, InterfaceKind};

    fn make_graph() -> IntentGraph {
        IntentGraph::in_memory().unwrap()
    }

    #[test]
    fn test_publish_and_query() {
        let graph = make_graph();
        let intent = IntentNode::new("agent-a", "Build AuthService");
        graph.publish(&intent).unwrap();

        let all = graph.query_all(None).unwrap();
        assert_eq!(all.len(), 1);
        assert_eq!(all[0].agent_id, "agent-a");
    }

    #[test]
    fn test_query_by_agent() {
        let graph = make_graph();
        graph.publish(&IntentNode::new("agent-a", "Auth")).unwrap();
        graph
            .publish(&IntentNode::new("agent-b", "Recipes"))
            .unwrap();
        graph
            .publish(&IntentNode::new("agent-a", "Auth v2"))
            .unwrap();

        let a_intents = graph.query_by_agent("agent-a").unwrap();
        assert_eq!(a_intents.len(), 2);
    }

    #[test]
    fn test_stability_filter() {
        let graph = make_graph();

        // Low stability intent
        let low = IntentNode::new("agent-a", "exploring");
        graph.publish(&low).unwrap();

        // High stability intent
        let high = IntentNode::new("agent-b", "committed").with_evidence(vec![
            Evidence::code_committed("initial"),
            Evidence::test_pass("tests"),
            Evidence::consumed_by("agent-c"),
        ]);
        graph.publish(&high).unwrap();

        let high_only = graph.query_all(Some(0.6)).unwrap();
        assert_eq!(high_only.len(), 1);
        assert_eq!(high_only[0].agent_id, "agent-b");
    }

    #[test]
    fn test_find_overlapping() {
        let graph = make_graph();

        // Agent A provides UserModel
        let a = IntentNode::new("agent-a", "Auth module").with_provides(vec![InterfaceSpec::new(
            "User",
            InterfaceKind::Model,
            "id: UUID, email: str",
        )
        .with_tags(vec!["user", "auth", "model"])]);
        graph.publish(&a).unwrap();

        // Agent B requires something user-related
        let my_specs = vec![
            InterfaceSpec::new("UserRef", InterfaceKind::Model, "user_id: UUID")
                .with_tags(vec!["user", "recipe", "model"]),
        ];

        let overlapping = graph.find_overlapping(&my_specs, "agent-b", 0.0).unwrap();
        assert_eq!(overlapping.len(), 1);
        assert_eq!(overlapping[0].agent_id, "agent-a");
    }

    #[test]
    fn test_resolve_consume_instead() {
        let graph = make_graph();

        // Agent A provides User model with high stability
        let a = IntentNode::new("agent-a", "Auth module")
            .with_provides(vec![InterfaceSpec::new(
                "User",
                InterfaceKind::Model,
                "id: UUID, email: str",
            )
            .with_tags(vec!["user", "auth", "model"])])
            .with_evidence(vec![
                Evidence::code_committed("committed"),
                Evidence::test_pass("passing"),
            ]);
        graph.publish(&a).unwrap();

        // Agent C also wants to provide a User model but is less committed
        let c =
            IntentNode::new("agent-c", "Meal planning").with_provides(vec![InterfaceSpec::new(
                "User",
                InterfaceKind::Model,
                "id: UUID, name: str",
            )
            .with_tags(vec!["user", "meal", "model"])]);

        let result = graph.resolve(&c, 0.0).unwrap();
        assert!(!result.adjustments.is_empty());
        assert_eq!(result.adjustments[0].kind, AdjustmentKind::ConsumeInstead);
    }

    #[test]
    fn test_resolve_adopt_constraint() {
        let graph = make_graph();

        // Agent A publishes a constraint about User model
        let a = IntentNode::new("agent-a", "Auth module")
            .with_provides(vec![InterfaceSpec::new(
                "User",
                InterfaceKind::Model,
                "id: UUID, email: str",
            )
            .with_tags(vec!["user", "auth"])])
            .with_constraints(vec![Constraint::new(
                "User model",
                "must have email: str as unique field",
            )
            .with_affects(vec!["user", "account"])])
            .with_evidence(vec![Evidence::code_committed("committed")]);
        graph.publish(&a).unwrap();

        // Agent B works on something user-related
        let b =
            IntentNode::new("agent-b", "Recipe module").with_provides(vec![InterfaceSpec::new(
                "Recipe",
                InterfaceKind::Model,
                "id: UUID, author_id: UUID",
            )
            .with_tags(vec!["recipe", "user", "model"])]);

        let result = graph.resolve(&b, 0.0).unwrap();
        assert!(!result.adopted_constraints.is_empty());
    }

    #[test]
    fn test_graph_summary() {
        let graph = make_graph();
        graph.publish(&IntentNode::new("agent-a", "Auth")).unwrap();
        graph
            .publish(&IntentNode::new("agent-b", "Recipes"))
            .unwrap();
        graph.publish(&IntentNode::new("agent-c", "Meals")).unwrap();

        let summary = graph.summary().unwrap();
        assert_eq!(summary.total_intents, 3);
        assert_eq!(summary.agent_count, 3);
    }

    #[test]
    fn test_no_self_overlap() {
        let graph = make_graph();

        let a = IntentNode::new("agent-a", "Auth module").with_provides(vec![InterfaceSpec::new(
            "User",
            InterfaceKind::Model,
            "id: UUID",
        )
        .with_tags(vec!["user", "model"])]);
        graph.publish(&a).unwrap();

        // Querying overlap for agent-a's own specs should exclude itself
        let overlapping = graph.find_overlapping(&a.provides, "agent-a", 0.0).unwrap();
        assert!(overlapping.is_empty());
    }
}
