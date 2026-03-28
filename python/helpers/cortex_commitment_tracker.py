import json
import os
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, date
from typing import Optional
from python.cortex.memory import get_agent_memory_subdir, abs_db_dir


_FILE = "cortex_commitments.json"


@dataclass
class Commitment:
    id: str
    text: str
    commitment_type: str
    status: str
    created_at: str
    due_date: Optional[str] = None

    def is_overdue(self) -> bool:
        if self.status != "pending" or not self.due_date:
            return False
        try:
            return date.today() > date.fromisoformat(self.due_date)
        except (ValueError, TypeError):
            return False


class CommitmentTracker:

    def __init__(self, commitments: list[Commitment] | None = None):
        self.commitments: list[Commitment] = commitments or []

    def add(
        self,
        text: str,
        due_date: Optional[str] = None,
        commitment_type: str = "promise",
    ) -> Commitment:
        c = Commitment(
            id=str(uuid.uuid4())[:8],
            text=text,
            commitment_type=commitment_type,
            status="pending",
            created_at=datetime.now().isoformat(),
            due_date=due_date,
        )
        self.commitments.append(c)
        return c

    def get_active(self) -> list[Commitment]:
        self._refresh_overdue()
        return [c for c in self.commitments if c.status in ("pending", "overdue")]

    def mark_done(self, commitment_id: str, venture_id: str = "", venture_name: str = "",
                  cortex_recommendation: str = "", autonomy_score: float = 0.5,
                  agent=None) -> None:
        """Mark commitment done and create an outcome checkin for Loop 2 attribution."""
        for c in self.commitments:
            if c.id == commitment_id:
                c.status = "done"
                # Trigger an outcome execution checkin (Loop 2 attribution)
                try:
                    from python.helpers.cortex_outcome_feedback import (
                        create_execution_checkin,
                        add_pending_checkin,
                    )
                    checkin = create_execution_checkin(
                        commitment_id=c.id,
                        commitment_description=c.text,
                        venture_id=venture_id or "unknown",
                        venture_name=venture_name or "unknown",
                        cortex_recommendation=cortex_recommendation or c.text,
                    )
                    if agent is not None:
                        add_pending_checkin(agent, checkin)
                except Exception:
                    pass
                break

    def format_for_prompt(self) -> str:
        active = self.get_active()
        if not active:
            return "No active commitments."
        lines = ["Active commitments:"]
        for c in active:
            due = f" (due: {c.due_date})" if c.due_date else ""
            flag = " [OVERDUE]" if c.status == "overdue" else ""
            lines.append(f"  [{c.id}] {c.text}{due}{flag}")
        return "\n".join(lines)

    def _refresh_overdue(self) -> None:
        for c in self.commitments:
            if c.is_overdue():
                c.status = "overdue"

    def to_dict(self) -> dict:
        return {
            "commitments": [asdict(c) for c in self.commitments],
            "updated": datetime.now().isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "CommitmentTracker":
        items = []
        for item in data.get("commitments", []):
            try:
                items.append(Commitment(**item))
            except Exception:
                pass
        return cls(commitments=items)

    @staticmethod
    def _data_path(agent) -> str:
        memory_dir = abs_db_dir(get_agent_memory_subdir(agent))
        return os.path.join(memory_dir, _FILE)

    @staticmethod
    def load(agent) -> "CommitmentTracker":
        try:
            path = CommitmentTracker._data_path(agent)
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    return CommitmentTracker.from_dict(json.load(f))
        except Exception:
            pass
        return CommitmentTracker()

    def save(self, agent) -> None:
        try:
            path = CommitmentTracker._data_path(agent)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(self.to_dict(), f, indent=2)
        except Exception:
            pass
