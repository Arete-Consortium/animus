"""Hunter OS — canonical Monster Hunter Wilds knowledge domain.

Hunter OS keeps game facts in structured, versioned records that can be
validated independently of Animus memory or LLM reasoning.
"""

from .audit import audit_record
from .chat import HUNTER_CHAT_SYSTEM, HunterChatContext, HunterOSChatService
from .models import (
    AuditFinding,
    AuditReport,
    AuditSeverity,
    GuideRecord,
    HunterRecord,
    MonsterRecord,
    RecordStatus,
    SourceRef,
    SpecialEncounterRecord,
    WeaponTypeRecord,
)
from .repository import HunterOSRepository
from .security import HunterOSChatPolicy

__all__ = [
    "AuditFinding",
    "AuditReport",
    "AuditSeverity",
    "GuideRecord",
    "HUNTER_CHAT_SYSTEM",
    "HunterChatContext",
    "HunterOSChatPolicy",
    "HunterOSChatService",
    "HunterOSRepository",
    "HunterRecord",
    "MonsterRecord",
    "RecordStatus",
    "SourceRef",
    "SpecialEncounterRecord",
    "WeaponTypeRecord",
    "audit_record",
]
