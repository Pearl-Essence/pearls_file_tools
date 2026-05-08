"""Project model for Pearl Post Suite.

A Project is a higher-level container that organises presets (naming profiles)
and sets default folder locations for ingest, export, and media browsing.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List


@dataclass
class Project:
    """A named collection of default paths and bound naming profiles."""

    name: str
    description: str = ""
    default_paths: Dict[str, str] = field(default_factory=dict)
    # Recognised keys:
    #   ingest_source, ingest_dest, mirror_dest, export_output, media_folder
    profile_names: List[str] = field(default_factory=list)
    # Names of ProductionTemplates bound to this project.
    # Empty list means "show all global profiles".
    created: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    # ── serialisation ────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "default_paths": dict(self.default_paths),
            "profile_names": list(self.profile_names),
            "created": self.created,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Project":
        return cls(
            name=d.get("name", "Untitled"),
            description=d.get("description", ""),
            default_paths=d.get("default_paths", {}),
            profile_names=d.get("profile_names", []),
            created=d.get("created", ""),
        )
