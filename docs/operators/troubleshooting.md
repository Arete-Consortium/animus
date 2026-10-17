# Troubleshooting

> Runbook for common Animus failures.

---

## Service Won't Start

**Symptom**: `animus-bootstrap start` fails silently

**Diagnosis**:
```bash
animus-bootstrap status
systemctl --user status animus  # Linux
```

**Fix**: Check logs for missing config:
```bash
tail ~/.local/share/animus/logs/animus.log
```

## Ollama Unreachable

**Symptom**: "Connection refused" on port 11434

**Fix**:
```bash
ollama serve  # Start Ollama
ollama list     # Verify models installed
```

## Memory Backend Errors

**Symptom**: Core reports that the configured Chroma backend is retired

**Fix**: Keep the service stopped and follow the
[Chroma retirement plan](chroma-retirement-plan.md). Inventory and back up the
actual store, rehearse migration, verify retrieval parity, and obtain cutover
authorization before changing configuration or restarting the service. A new
Core installation with no legacy data can use the default `local` backend.

## Forge Budget Exceeded

**Symptom**: `BudgetExceededError` during workflow execution

**Fix**: Check current spend:
```python
from animus_forge.budget import BudgetManager
bm = BudgetManager(total_budget=10000)
print(bm.current_spend)
```

## Import Errors After Update

**Symptom**: `ModuleNotFoundError` after pulling latest code

**Fix**: Reinstall in editable mode:
```bash
pip install -e packages/types/
pip install -e packages/core/
```

---

## See Also

- [Known Issues](known-issues.md) — Documented bugs
- [Debugging Guide](../contributing/debugging.md) — Dev environment issues
- [Recovery](recovery.md) — Disaster recovery procedures
