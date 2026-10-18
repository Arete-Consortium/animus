# Animus Known Issues & Gaps

Last updated: 2026-01-27 (v0.6.0)

## Testing Gaps

### ~~HIGH: No Offline/Mock LLM Testing~~ RESOLVED

**Status:** Resolved (v0.6.0) — `MockModel` added to `animus/cognitive.py`

**Solution implemented:**
- `MockModel(ModelInterface)` with configurable default response and response map
- `ModelConfig.mock()` classmethod for easy construction
- `MOCK` provider in `ModelProvider` enum + `create_model()` factory
- Call history recording (`calls: list[dict]`) for test assertions
- Tests in `tests/test_cognitive_mock.py` covering MockModel, CognitiveLayer, and DecisionFramework

---

### ~~MEDIUM: API Server Test Coverage~~ RESOLVED

**Status:** Resolved (v0.6.0) — `tests/test_api.py` added

**Solution implemented:**
- 30 tests covering all endpoints (status, chat, memory CRUD, tools, tasks CRUD, decisions, brief, integrations, learning, auth)
- Uses MockModel backend for deterministic responses
- Skips gracefully when FastAPI not installed

---

### ~~MEDIUM: Asyncio Deprecation Warnings~~ RESOLVED

**Status:** Resolved (v0.6.0) — All `asyncio.get_event_loop().run_until_complete()` replaced with `asyncio.run()`

**Files fixed:**
- `animus/__main__.py` — 11 call sites
- `tests/test_phase4.py` — 7 call sites
- All 6 previously failing tests now pass

---

### LOW: Voice Interface Testing

**Problem:** Voice interface requires audio hardware, cannot test in CI.

**Affected Components:**
- `VoiceInput` - Microphone capture
- `VoiceOutput` - Audio playback
- Whisper transcription

**Proposed Solution:**
- Add audio file input mode for testing
- Mock `sounddevice` for unit tests
- Integration test with pre-recorded audio files

**Priority:** Low - Hardware dependent

---

## API Inconsistencies

### ~~Memory.create() Missing~~ RESOLVED

**Status:** Resolved (v0.6.0) — `Memory.create()` classmethod added to `animus/memory.py`

**Solution:** Factory method auto-generates `id` (UUID), `created_at`, `updated_at`. All other fields have sensible defaults. Tests in `tests/test_core.py::TestMemoryCreate`.

---

### Inconsistent Method Names

**Problem:** Similar operations have different names across modules.

| Module | Add | Complete/Apply |
|--------|-----|----------------|
| TaskTracker | `add()` | `complete()` |
| MemoryStore | `store()` | N/A |
| LearningLayer | N/A | `approve_learning()` |

**Proposed:** Standardize on `add`/`remove` or document conventions.

**Priority:** Low - Documentation

---

## Feature Gaps

### No Web Dashboard

**Problem:** Learning transparency data has no visual interface.

**Current:** CLI-only via `/learning` command

**Proposed:**
- Simple HTML dashboard served by API
- Or separate React/Vue frontend
- Real-time updates via WebSocket

**Priority:** Medium - Usability

---

### ~~No Scheduled Tasks~~ RESOLVED

**Status:** Resolved (v0.6.0) — Background scheduler added to `LearningLayer`

**Solution:** `threading.Timer`-based scheduler with `start_auto_scan(interval_hours)`, `stop_auto_scan()`, and `auto_scan_running` property. Daemon thread, no external dependencies. Tests in `tests/test_phase5.py::TestAutoScanScheduler`.

---

### No Data Export

**Problem:** No way to export memories, learnings, or decisions.

**Proposed:**
- `/export memories` - JSON/CSV export
- `/export learnings` - Learning history
- `/export decisions` - Decision log
- API endpoints for same

**Priority:** Low - Nice to have

---

## Performance

### Legacy ChromaDB Cold Start (retired Core backend)

**Problem:** Historical Chroma deployments downloaded a 79MB embedding model on
the first memory operation. Chroma is no longer a supported Core runtime backend.

**Impact:** ~3s delay on first use

**Mitigation:** Preserve existing data and follow the
[Chroma retirement plan](chroma-retirement-plan.md). Do not install or prewarm
Chroma for a new Core environment.

**Priority:** Low - One-time cost

---

## Security

### ~~No Input Sanitization Audit~~ RESOLVED

**Status:** Resolved (v0.6.0) — Security hardening applied to `animus/tools.py`

**Changes:**
- `_validate_command()`: Whitespace normalization to prevent bypass; blocks `$()`, backtick subshells, `| sh`, `| bash`
- `_tool_read_file()`: Path resolution via `.resolve()` before I/O (prevents symlink traversal)
- `_tool_list_files()`: Same `.resolve()` fix
- `_tool_web_search()`: Control character stripping, 500-char query limit
- Tests in `tests/test_security.py::TestShellInjection` and `TestWebSearchSanitization`

---

## Next Actions

1. [x] Add MockModel for testing without LLM
2. [x] Add API integration tests
3. [x] Fix asyncio deprecation warnings
4. [x] Add Memory.create() factory method
5. [x] Implement background scheduler for auto-scan
6. [x] Security audit of tool inputs
