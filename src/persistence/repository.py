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

Every incident is stored with its full reviewer packet. When a human reviewer
acts (approve / reject / escalate), the decision is recorded on the incident
AND appended as a separate audit record, so the human half of the governance
loop is as traceable as the automated half: who decided what, when, and why.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Protocol

# Valid human decisions at the review gate.
HUMAN_DECISIONS = ("approved", "rejected", "escalated")


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _new_incident_record(packet: dict) -> dict:
    """Build the persisted record from a reviewer packet."""
    return {
        "id": str(uuid.uuid4()),
        "type": "incident",  # single-container design: type discriminates records
        "created_at": _now(),
        "route": packet.get("route"),
        "risk_score": packet.get("risk_score"),
        "risk_band": packet.get("risk_band"),
        "requires_human_approval": packet.get("requires_human_approval"),
        "policy_version": packet.get("policy_version"),
        "hard_overrides": packet.get("hard_overrides", []),
        "reviewer_packet": packet,
        "status": "pending_review" if packet.get("requires_human_approval") else "auto_logged",
        "human_decision": None,
        "decided_by": None,
        "decided_at": None,
    }


class IncidentRepository(Protocol):
    """Anything that can persist and retrieve incidents and audit records."""

    def save(self, packet: dict) -> dict: ...

    def get(self, incident_id: str) -> dict | None: ...

    def list_pending(self) -> list[dict]: ...

    def list_all(self) -> list[dict]: ...

    def record_decision(
        self, incident_id: str, decision: str, reviewer: str, note: str
    ) -> dict | None: ...

    def list_audit(self, incident_id: str) -> list[dict]: ...


class InMemoryIncidentRepository:
    """In-process store. No external dependency; resets on restart."""

    def __init__(self) -> None:
        self._incidents: dict[str, dict] = {}
        self._audit: list[dict] = []

    def save(self, packet: dict) -> dict:
        record = _new_incident_record(packet)
        self._incidents[record["id"]] = record
        return record

    def get(self, incident_id: str) -> dict | None:
        return self._incidents.get(incident_id)

    def list_pending(self) -> list[dict]:
        return [r for r in self._incidents.values() if r["status"] == "pending_review"]

    def list_all(self) -> list[dict]:
        return sorted(self._incidents.values(), key=lambda r: r["created_at"], reverse=True)

    def record_decision(
        self, incident_id: str, decision: str, reviewer: str, note: str
    ) -> dict | None:
        incident = self._incidents.get(incident_id)
        if incident is None:
            return None
        incident["status"] = decision
        incident["human_decision"] = decision
        incident["decided_by"] = reviewer
        incident["decided_at"] = _now()
        self._audit.append(
            {
                "id": str(uuid.uuid4()),
                "type": "audit",
                "incident_id": incident_id,
                "decision": decision,
                "reviewer": reviewer,
                "note": note,
                "decided_at": incident["decided_at"],
                "policy_version": incident.get("policy_version"),
            }
        )
        return incident

    def list_audit(self, incident_id: str) -> list[dict]:
        return [a for a in self._audit if a["incident_id"] == incident_id]


class CosmosIncidentRepository:
    """
    Cosmos DB-backed store. Single container, type-discriminated records
    (incidents and audit records share one container with a `type` field),
    which is the agreed v1 data design. Managed Identity via
    DefaultAzureCredential - no keys in code.
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
        q = "SELECT * FROM c WHERE c.type = 'incident' AND c.status = 'pending_review'"
        return list(self._container.query_items(query=q, enable_cross_partition_query=True))

    def list_all(self) -> list[dict]:
        q = "SELECT * FROM c WHERE c.type = 'incident' ORDER BY c.created_at DESC"
        return list(self._container.query_items(query=q, enable_cross_partition_query=True))

    def record_decision(
        self, incident_id: str, decision: str, reviewer: str, note: str
    ) -> dict | None:
        incident = self.get(incident_id)
        if incident is None:
            return None
        incident["status"] = decision
        incident["human_decision"] = decision
        incident["decided_by"] = reviewer
        incident["decided_at"] = _now()
        self._container.upsert_item(incident)
        self._container.upsert_item(
            {
                "id": str(uuid.uuid4()),
                "type": "audit",
                "incident_id": incident_id,
                "decision": decision,
                "reviewer": reviewer,
                "note": note,
                "decided_at": incident["decided_at"],
                "policy_version": incident.get("policy_version"),
            }
        )
        return incident

    def list_audit(self, incident_id: str) -> list[dict]:
        q = "SELECT * FROM c WHERE c.type = 'audit' AND c.incident_id = @id"
        params = [{"name": "@id", "value": incident_id}]
        return list(
            self._container.query_items(
                query=q, parameters=params, enable_cross_partition_query=True
            )
        )
