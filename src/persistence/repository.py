"""
Incident persistence.

A repository interface with two implementations:

  - InMemoryIncidentRepository: no external dependency, used for tests and local
    development. The API runs fully without Azure.
  - CosmosIncidentRepository: persists to Azure Cosmos DB, used in deployment.

Both satisfy the same IncidentRepository protocol, so the API depends on the
interface, never on Cosmos directly. Cosmos was capacity-constrained at build
time (see ADR-002); this seam lets the system run and be tested now, and swap
to Cosmos the moment it is stable, with no change to the API layer.

Every incident is stored with its full reviewer packet and the governance
decision, so the record is a complete, auditable trail: what was detected, what
was cited, how it scored, how it was routed, and which policy version decided.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Protocol


def _new_incident_record(packet: dict) -> dict:
    """Build the persisted record from a reviewer packet."""
    return {
        "id": str(uuid.uuid4()),
        "type": "incident",  # single-container design: type discriminates records
        "created_at": datetime.now(UTC).isoformat(),
        "route": packet.get("route"),
        "risk_score": packet.get("risk_score"),
        "risk_band": packet.get("risk_band"),
        "requires_human_approval": packet.get("requires_human_approval"),
        "policy_version": packet.get("policy_version"),
        "hard_overrides": packet.get("hard_overrides", []),
        "reviewer_packet": packet,
        "status": "pending_review" if packet.get("requires_human_approval") else "auto_logged",
    }


class IncidentRepository(Protocol):
    """Anything that can persist and retrieve incident records."""

    def save(self, packet: dict) -> dict: ...

    def get(self, incident_id: str) -> dict | None: ...

    def list_pending(self) -> list[dict]: ...


class InMemoryIncidentRepository:
    """In-process store. No external dependency; resets on restart."""

    def __init__(self) -> None:
        self._store: dict[str, dict] = {}

    def save(self, packet: dict) -> dict:
        record = _new_incident_record(packet)
        self._store[record["id"]] = record
        return record

    def get(self, incident_id: str) -> dict | None:
        return self._store.get(incident_id)

    def list_pending(self) -> list[dict]:
        return [r for r in self._store.values() if r["status"] == "pending_review"]


class CosmosIncidentRepository:
    """
    Cosmos DB-backed store. Single container, type-discriminated records
    (incidents, audit records, agent outputs all share one container with a
    `type` field), which is the agreed v1 data design.

    Uses Managed Identity via DefaultAzureCredential — no keys in code. Import
    of the Cosmos SDK is deferred to construction so the module loads (and the
    in-memory path stays usable) even where azure-cosmos is not installed.
    """

    def __init__(self, endpoint: str, database: str, container: str) -> None:
        from azure.cosmos import CosmosClient
        from azure.identity import DefaultAzureCredential

        client = CosmosClient(url=endpoint, credential=DefaultAzureCredential())
        db = client.get_database_client(database)
        self._container = db.get_container_client(container)

    def save(self, packet: dict) -> dict:
        record = _new_incident_record(packet)
        self._container.upsert_item(record)
        return record

    def get(self, incident_id: str) -> dict | None:
        from azure.cosmos import exceptions

        try:
            return self._container.read_item(item=incident_id, partition_key=incident_id)
        except exceptions.CosmosResourceNotFoundError:
            return None

    def list_pending(self) -> list[dict]:
        query = "SELECT * FROM c WHERE c.type = 'incident' AND c.status = 'pending_review'"
        return list(self._container.query_items(query=query, enable_cross_partition_query=True))
