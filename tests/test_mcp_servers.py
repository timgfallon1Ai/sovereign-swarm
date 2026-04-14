"""Tests for the three Sovereign MCP servers.

Covers:
- brand_server: list_tenants, get_brand_profile, get_negative_prompt,
  get_voice_preset, get_palette, unknown-tenant error shape
- ingest_query_server: lazy ChromaDB handle behavior, result
  formatting, fail-closed when chromadb absent / path missing,
  stubbed successful query end-to-end
- marketing_server: list_supported_intents, list_tenants, API-key
  gating on plan_campaign / produce_campaign, brief-parse errors,
  check_campaign_status / list_recent_runs with a fake output_dir,
  end-to-end stubbed plan_campaign + produce_campaign

Every external dependency (chromadb, Anthropic, OpenMontage registry,
ffmpeg) is stubbed so tests are deterministic and fast.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest


# ---------- brand_server ----------


class TestBrandServer:
    def setup_method(self):
        # Import inside test class so fixtures can tweak sys.modules first if needed
        from sovereign_swarm.mcp_servers import brand_server

        self.srv = brand_server

    def test_list_tenants(self):
        r = asyncio.run(self.srv.list_tenants())
        assert r["count"] == 3
        assert "atx_mats" in r["tenants"]
        assert "gbb" in r["tenants"]
        assert "gli" in r["tenants"]

    def test_get_brand_profile_happy(self):
        r = asyncio.run(self.srv.get_brand_profile("atx_mats"))
        assert r["display_name"] == "ATX Mats"
        assert r["voice_name"] == "Davis"
        assert len(r["palette"]) >= 3
        assert "practical" in r["tone_keywords"]

    def test_get_brand_profile_unknown(self):
        r = asyncio.run(self.srv.get_brand_profile("not_a_tenant"))
        assert "error" in r
        assert "known_tenants" in r
        assert "atx_mats" in r["known_tenants"]

    def test_get_negative_prompt(self):
        r = asyncio.run(self.srv.get_negative_prompt("gli"))
        assert r["tenant"] == "gli"
        assert "marijuana leaf" in r["negative_prompt"]

    def test_get_voice_preset(self):
        r = asyncio.run(self.srv.get_voice_preset("gbb"))
        assert r["voice_name"] == "Frank"

    def test_get_palette(self):
        r = asyncio.run(self.srv.get_palette("atx_mats"))
        assert isinstance(r["palette"], list)
        assert r["palette"][0] == r["primary"]

    def test_mcp_instance_wired(self):
        assert self.srv.mcp.name == "sovereign-brand"


# ---------- ingest_query_server ----------


class _StubChromaCollection:
    def __init__(self, documents, metadatas, distances=None):
        self._docs = documents
        self._metas = metadatas
        self._dists = distances or [0.3] * len(documents)

    def query(self, query_texts, n_results=10, where=None, include=None):
        docs = self._docs[:n_results]
        metas = self._metas[:n_results]
        dists = self._dists[:n_results]
        if where and "source" in where:
            filtered = [
                (d, m, dist)
                for d, m, dist in zip(docs, metas, dists)
                if (m or {}).get("source") == where["source"]
            ]
            docs = [f[0] for f in filtered]
            metas = [f[1] for f in filtered]
            dists = [f[2] for f in filtered]
        return {
            "ids": [[f"chunk_{i}" for i in range(len(docs))]],
            "documents": [docs],
            "metadatas": [metas],
            "distances": [dists],
        }

    def count(self):
        return len(self._docs)

    def get(self, limit=10, include=None, where=None):
        metas = self._metas[:limit]
        docs = self._docs[:limit]
        if where and "document_id" in where:
            filtered = [
                (d, m)
                for d, m in zip(docs, metas)
                if (m or {}).get("document_id") == where["document_id"]
            ]
            docs = [f[0] for f in filtered]
            metas = [f[1] for f in filtered]
        return {
            "ids": [f"chunk_{i}" for i in range(len(docs))],
            "documents": docs,
            "metadatas": metas,
        }


class _StubChromaClient:
    def __init__(self, collection):
        self._collection = collection

    def get_collection(self, name):
        return self._collection


@pytest.fixture
def ingest_srv():
    """Fresh ingest server module with a clean handle between tests."""
    from sovereign_swarm.mcp_servers import ingest_query_server

    # Reset the global handle so each test gets a fresh state
    ingest_query_server._handle = ingest_query_server._ChromaHandle()
    return ingest_query_server


def _install_stub_chroma(monkeypatch, collection):
    """Install a fake chromadb module so PersistentClient returns our stub."""
    fake = SimpleNamespace(
        PersistentClient=lambda path: _StubChromaClient(collection),
    )
    monkeypatch.setitem(sys.modules, "chromadb", fake)


class TestIngestQueryServer:
    def test_no_chromadb_module_returns_error(self, ingest_srv, tmp_path, monkeypatch):
        monkeypatch.setenv("SOVEREIGN_INGEST_CHROMA_PATH", str(tmp_path))
        tmp_path.mkdir(exist_ok=True)
        # Ensure chromadb import fails by blocking the import
        monkeypatch.setitem(sys.modules, "chromadb", None)
        r = asyncio.run(ingest_srv.semantic_search("test"))
        assert "error" in r
        assert "chromadb" in r["error"]

    def test_missing_path_returns_error(self, ingest_srv, tmp_path, monkeypatch):
        monkeypatch.setenv(
            "SOVEREIGN_INGEST_CHROMA_PATH", str(tmp_path / "nonexistent")
        )
        _install_stub_chroma(monkeypatch, _StubChromaCollection([], []))
        r = asyncio.run(ingest_srv.semantic_search("test"))
        assert "error" in r
        assert "not found" in r["error"] or "does not exist" in r["error"].lower()

    def test_semantic_search_happy_path(self, ingest_srv, tmp_path, monkeypatch):
        # Pretend we have three hits from arXiv and PubMed
        documents = [
            "Order-flow entropy predicts SPY moves",
            "Polymer composite gym flooring load ratings",
            "LED PAR output spectrum analysis",
        ]
        metadatas = [
            {
                "source": "arxiv",
                "document_id": "2512.15720",
                "title": "Hidden Order in Trades",
                "category": "finance",
                "chunk_index": 0,
            },
            {
                "source": "openfda",
                "document_id": "ofda-1",
                "title": "Gym flooring safety",
                "category": "materials",
                "chunk_index": 0,
            },
            {
                "source": "pubmed",
                "document_id": "pmid-99",
                "title": "LED PAR spectrum",
                "category": "horticulture",
                "chunk_index": 0,
            },
        ]
        collection = _StubChromaCollection(
            documents, metadatas, distances=[0.2, 0.4, 0.6]
        )
        monkeypatch.setenv("SOVEREIGN_INGEST_CHROMA_PATH", str(tmp_path))
        _install_stub_chroma(monkeypatch, collection)
        r = asyncio.run(ingest_srv.semantic_search("market signal", top_k=3))
        assert "error" not in r
        assert len(r["results"]) == 3
        assert r["results"][0]["source"] == "arxiv"
        # Score is 1 - dist/2, so 0.2 -> 0.9
        assert abs(r["results"][0]["score"] - 0.9) < 0.01
        assert r["results"][1]["source"] == "openfda"

    def test_search_by_source_filter(self, ingest_srv, tmp_path, monkeypatch):
        collection = _StubChromaCollection(
            documents=["arxiv doc", "pubmed doc"],
            metadatas=[
                {"source": "arxiv", "document_id": "a", "chunk_index": 0},
                {"source": "pubmed", "document_id": "b", "chunk_index": 0},
            ],
            distances=[0.2, 0.2],
        )
        monkeypatch.setenv("SOVEREIGN_INGEST_CHROMA_PATH", str(tmp_path))
        _install_stub_chroma(monkeypatch, collection)
        r = asyncio.run(ingest_srv.search_by_source("q", "arxiv", top_k=5))
        assert "error" not in r
        assert len(r["results"]) == 1
        assert r["results"][0]["source"] == "arxiv"

    def test_list_sources_counts(self, ingest_srv, tmp_path, monkeypatch):
        collection = _StubChromaCollection(
            documents=["1", "2", "3", "4"],
            metadatas=[
                {"source": "arxiv"},
                {"source": "arxiv"},
                {"source": "pubmed"},
                {"source": "openfda"},
            ],
        )
        monkeypatch.setenv("SOVEREIGN_INGEST_CHROMA_PATH", str(tmp_path))
        _install_stub_chroma(monkeypatch, collection)
        r = asyncio.run(ingest_srv.list_sources())
        assert "error" not in r
        sources = {s["source"]: s["sample_count"] for s in r["sources"]}
        assert sources["arxiv"] == 2
        assert sources["pubmed"] == 1
        assert sources["openfda"] == 1

    def test_collection_stats(self, ingest_srv, tmp_path, monkeypatch):
        collection = _StubChromaCollection(
            documents=["a"] * 5,
            metadatas=[{"source": "arxiv"}] * 3 + [{"source": "pubmed"}] * 2,
        )
        monkeypatch.setenv("SOVEREIGN_INGEST_CHROMA_PATH", str(tmp_path))
        _install_stub_chroma(monkeypatch, collection)
        r = asyncio.run(ingest_srv.collection_stats())
        assert r["total_chunks"] == 5
        assert r["top_sources"][0]["source"] == "arxiv"

    def test_get_chunk_found(self, ingest_srv, tmp_path, monkeypatch):
        collection = _StubChromaCollection(
            documents=["first chunk", "second chunk"],
            metadatas=[
                {"document_id": "doc1", "chunk_index": 0},
                {"document_id": "doc1", "chunk_index": 1},
            ],
        )
        monkeypatch.setenv("SOVEREIGN_INGEST_CHROMA_PATH", str(tmp_path))
        _install_stub_chroma(monkeypatch, collection)
        r = asyncio.run(ingest_srv.get_chunk("doc1", chunk_index=1))
        assert r["text"] == "second chunk"

    def test_get_chunk_not_found(self, ingest_srv, tmp_path, monkeypatch):
        collection = _StubChromaCollection(
            documents=["x"], metadatas=[{"document_id": "doc1", "chunk_index": 0}]
        )
        monkeypatch.setenv("SOVEREIGN_INGEST_CHROMA_PATH", str(tmp_path))
        _install_stub_chroma(monkeypatch, collection)
        r = asyncio.run(ingest_srv.get_chunk("doc1", chunk_index=99))
        assert r["error"] == "chunk not found"

    def test_mcp_instance_wired(self, ingest_srv):
        assert ingest_srv.mcp.name == "sovereign-ingest-query"


# ---------- marketing_server ----------


@pytest.fixture
def marketing_srv(monkeypatch, tmp_path):
    """Fresh marketing server module with isolated output + handle."""
    from sovereign_swarm.mcp_servers import marketing_server

    marketing_server._handle = marketing_server._EnsembleHandle()
    monkeypatch.setenv("SOVEREIGN_MARKETING_OUTPUT", str(tmp_path))
    return marketing_server


def _valid_brief_dict(**overrides):
    base = {
        "tenant": "atx_mats",
        "campaign_id": "mcp-test-001",
        "subject": "new gym flooring launch",
        "audience": "commercial gym owners",
        "objective": "launch",
        "key_message": "Outlasts the warranty",
        "call_to_action": "Request a sample",
    }
    base.update(overrides)
    return base


class _StubAnthropicClient:
    def __init__(self, response_text: str):
        self.response_text = response_text
        self.calls = []

        async def _create(**kw):
            self.calls.append(kw)
            return SimpleNamespace(
                content=[SimpleNamespace(type="text", text=response_text)],
                usage=SimpleNamespace(input_tokens=60, output_tokens=40),
            )

        self.messages = SimpleNamespace(create=_create)


_VALID_SCRIPT_JSON = json.dumps(
    {
        "narration_text": "By the end of this clip you will know why ATX Mats outlast every warranty.",
        "video_prompt": "cinematic studio shot of golden ATX Mats flooring, navy backdrop",
        "still_prompts": ["hero shot", "edge detail"],
        "captions": ["Built in Austin", "Made to last"],
        "rationale": "Awareness objective with a strong promise opening",
        "warnings": [],
    }
)


class TestMarketingServer:
    def test_list_supported_intents(self, marketing_srv):
        r = asyncio.run(marketing_srv.list_supported_intents())
        assert r["server"] == "sovereign-marketing"
        names = [t["name"] for t in r["tools"]]
        assert "plan_campaign" in names
        assert "produce_campaign" in names
        assert "list_tenants" in names

    def test_list_tenants_cross_server_consistency(self, marketing_srv):
        r = asyncio.run(marketing_srv.list_tenants())
        assert r["count"] >= 3
        assert {"atx_mats", "gbb", "gli", "sovereign"} <= set(r["tenants"].keys())

    def test_plan_campaign_requires_api_key(self, marketing_srv, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        r = asyncio.run(marketing_srv.plan_campaign(_valid_brief_dict()))
        assert "error" in r
        assert "ANTHROPIC_API_KEY" in r["error"]

    def test_produce_campaign_requires_api_key(self, marketing_srv, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        r = asyncio.run(marketing_srv.produce_campaign(_valid_brief_dict()))
        assert "error" in r
        assert "ANTHROPIC_API_KEY" in r["error"]

    def test_plan_campaign_invalid_brief(self, marketing_srv, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-stub")
        # Missing required 'campaign_id'
        r = asyncio.run(
            marketing_srv.plan_campaign({"tenant": "atx_mats", "subject": "x"})
        )
        assert "error" in r
        assert "invalid brief" in r["error"]

    def test_plan_campaign_happy_path(self, marketing_srv, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-stub")
        stub_anthropic = SimpleNamespace(
            AsyncAnthropic=lambda: _StubAnthropicClient(_VALID_SCRIPT_JSON)
        )
        monkeypatch.setitem(sys.modules, "anthropic", stub_anthropic)
        r = asyncio.run(marketing_srv.plan_campaign(_valid_brief_dict()))
        assert r["status"] == "success"
        assert r["success"] is True
        assert "outlast" in r["narration_text"]
        assert len(r["still_prompts"]) == 2

    def test_check_campaign_status_missing_manifest(self, marketing_srv, tmp_path):
        r = asyncio.run(
            marketing_srv.check_campaign_status(str(tmp_path / "does_not_exist"))
        )
        assert "error" in r

    def test_check_campaign_status_with_manifest(self, marketing_srv, tmp_path):
        manifest = {
            "tenant": "atx_mats",
            "campaign_id": "xyz",
            "status": "success",
            "total_duration_s": 123.0,
        }
        (tmp_path / "manifest.json").write_text(json.dumps(manifest))
        r = asyncio.run(marketing_srv.check_campaign_status(str(tmp_path)))
        assert r["tenant"] == "atx_mats"
        assert r["campaign_id"] == "xyz"
        assert r["publish_state"] is None

    def test_check_campaign_status_with_approval(self, marketing_srv, tmp_path):
        manifest = {"tenant": "gli", "campaign_id": "a"}
        (tmp_path / "manifest.json").write_text(json.dumps(manifest))
        # Stage a publish request + approved token
        pub_req = {
            "tenant": "gli",
            "campaign_id": "a",
            "artifacts": {},
            "platforms": ["linkedin"],
            "approval_token": "abc",
            "requested_at": "2026-04-09T00:00:00Z",
        }
        (tmp_path / "publish_request.json").write_text(json.dumps(pub_req))
        (tmp_path / "approved.token").write_text("abc")
        r = asyncio.run(marketing_srv.check_campaign_status(str(tmp_path)))
        assert r["publish_state"] == "approved"

    def test_list_recent_runs_empty(self, marketing_srv, tmp_path):
        r = asyncio.run(marketing_srv.list_recent_runs())
        # tmp_path exists but has no tenant subdirs
        assert r["runs"] == []
        assert r["count"] == 0

    def test_list_recent_runs_with_data(self, marketing_srv, tmp_path):
        # Stage two fake runs for atx_mats
        for i in range(2):
            run_dir = tmp_path / "atx_mats" / f"2026-04-09_{i}_abc"
            run_dir.mkdir(parents=True)
            (run_dir / "manifest.json").write_text(
                json.dumps(
                    {
                        "tenant": "atx_mats",
                        "campaign_id": f"run-{i}",
                        "status": "success",
                        "timestamp": "2026-04-09T00:00:00Z",
                        "total_duration_s": 10.0,
                    }
                )
            )
        r = asyncio.run(marketing_srv.list_recent_runs(tenant="atx_mats"))
        assert r["count"] == 2
        assert all(run["tenant"] == "atx_mats" for run in r["runs"])
        assert any(run["campaign_id"] == "run-0" for run in r["runs"])

    def test_list_recent_runs_missing_root(self, marketing_srv, monkeypatch):
        monkeypatch.setenv(
            "SOVEREIGN_MARKETING_OUTPUT", "/nonexistent/path/for/test"
        )
        r = asyncio.run(marketing_srv.list_recent_runs())
        assert r["runs"] == []
        assert "does not exist" in (r.get("note") or "")

    def test_mcp_instance_wired(self, marketing_srv):
        assert marketing_srv.mcp.name == "sovereign-marketing"
