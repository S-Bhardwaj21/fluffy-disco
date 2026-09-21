from pydantic import BaseModel, Field
from typing import Literal

class ReasoningResult(BaseModel):
    root_cause: str
    impact_summary: str
    recommended_action: str
    outcome: Literal["AUTO_RESOLVE", "ESCALATE", "REQUEST_EVIDENCE"]
    confidence: float = Field(ge=0, le=100)
    evidence_sufficiency: Literal["SUFFICIENT", "INSUFFICIENT", "CONFLICTING"]
    key_evidence: list[str]
    missing_evidence: list[str]
    decision_explanation: str