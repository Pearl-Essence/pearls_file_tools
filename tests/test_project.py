"""Comprehensive tests for models/project.py."""

import pytest
from models.project import Project


class TestProjectInit:
    def test_minimal(self):
        p = Project(name="Test")
        assert p.name == "Test"
        assert p.description == ""
        assert p.default_paths == {}
        assert p.profile_names == []
        assert p.created != ""

    def test_full(self):
        p = Project(
            name="Big Show",
            description="A production project",
            default_paths={"ingest_source": "/vol/cards", "ingest_dest": "/vol/media"},
            profile_names=["Studio Default", "VFX"],
            created="2025-01-01T00:00:00+00:00",
        )
        assert p.name == "Big Show"
        assert p.default_paths["ingest_source"] == "/vol/cards"
        assert len(p.profile_names) == 2


class TestSerialization:
    def test_to_dict(self):
        p = Project(name="Test", description="desc",
                   default_paths={"media_folder": "/tmp"},
                   profile_names=["ProfileA"])
        d = p.to_dict()
        assert d["name"] == "Test"
        assert d["description"] == "desc"
        assert d["default_paths"]["media_folder"] == "/tmp"
        assert d["profile_names"] == ["ProfileA"]
        assert "created" in d

    def test_from_dict(self):
        d = {
            "name": "Restored",
            "description": "from dict",
            "default_paths": {"ingest_dest": "/out"},
            "profile_names": ["P1"],
            "created": "2025-06-01T00:00:00",
        }
        p = Project.from_dict(d)
        assert p.name == "Restored"
        assert p.description == "from dict"
        assert p.default_paths == {"ingest_dest": "/out"}
        assert p.created == "2025-06-01T00:00:00"

    def test_from_dict_defaults(self):
        p = Project.from_dict({})
        assert p.name == "Untitled"
        assert p.description == ""
        assert p.default_paths == {}
        assert p.profile_names == []
        assert p.created == ""

    def test_roundtrip(self):
        original = Project(
            name="RT",
            description="roundtrip test",
            default_paths={"export_output": "/export"},
            profile_names=["A", "B"],
        )
        d = original.to_dict()
        restored = Project.from_dict(d)
        assert restored.name == original.name
        assert restored.description == original.description
        assert restored.default_paths == original.default_paths
        assert restored.profile_names == original.profile_names
        assert restored.created == original.created

    def test_to_dict_copies_data(self):
        """Mutating the dict should not affect the original."""
        p = Project(name="Test", default_paths={"a": "b"}, profile_names=["x"])
        d = p.to_dict()
        d["default_paths"]["a"] = "changed"
        d["profile_names"].append("y")
        assert p.default_paths["a"] == "b"
        assert p.profile_names == ["x"]
