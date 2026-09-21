import json
from src.core.models import ReasoningResult
from src.core.snowflake_client import get_connection

MODEL="claude-sonnet-4-6"
RESPONSE_SCHEMA={
    "type":"json",
    "schema":{
        "type":"object",
        "properties":{
            "root_cause":{"type":"string"},
            "impact_summary":{"type":"string"},
            "recommended_action":{"type":"string"},
            "outcome":{"type":"string","enum":["AUTO_RESOLVE","ESCALATE","REQUEST_EVIDENCE"]},
            "confidence":{"type":"number"},
            "evidence_sufficiency":{"type":"string","enum":["SUFFICIENT","INSUFFICIENT","CONFLICTING"]},
            "key_evidence":{"type":"array","items":{"type":"string"}},
            "missing_evidence":{"type":"array","items":{"type":"string"}},"decision_explanation":{"type":"string"}
        },
        "required":["root_cause","impact_summary","recommended_action","outcome","confidence","evidence_sufficiency","key_evidence","missing_evidence","decision_explanation"],
        "additionalProperties":False
    }
}

def _reasoning_evidence(evidence_pack):
    return {
        "exception":evidence_pack["exception"],
        "entity_context":evidence_pack["entity_context"],
        "financial_evidence":evidence_pack["financial_evidence"],
        "timeline_evidence":evidence_pack["timeline_evidence"],
        "relevant_communications":evidence_pack["relevant_communications"],
        "contract_amendments":evidence_pack["contract_amendments"],
        "relevant_erp_evidence":evidence_pack["relevant_erp_evidence"],
        "policy_evidence":evidence_pack["policy_evidence"],
        "impact_evidence":{"summary":evidence_pack["impact_evidence"]["summary"]}
    }

def build_reasoning_prompt(evidence_pack):
    evidence=_reasoning_evidence(evidence_pack)
    return f"""You are an enterprise exception investigator.
Analyze the supplied evidence and reconstruct what happened.
Do not invent facts.
Distinguish confirmed evidence from inference.
Never present an inference as a confirmed fact.
For every important conclusion, prefer specific evidence such as entity IDs, timestamps, amounts, status values, amendments, communications, or ERP events.

Assess:
1. Root cause
2. Business impact
3. Evidence sufficiency
4. Recommended action
5. Whether the case appears suitable for auto-resolution, escalation, or requesting more evidence
6. Specific evidence supporting the reasoning
7. Missing or contradictory evidence

IMPORTANT DISTINCTIONS:
- Separate confirmed relationships from possible downstream effects.
- If records are related to the exception but their own state has not been inspected, describe them as downstream records requiring validation, not as confirmed stale or incorrect records.
- Separate what is sufficient to resolve the current exception from what would be needed for broader investigation or remediation.
- Do not claim that a downstream system, order, shipment, invoice, or payment is incorrect unless the supplied evidence establishes that fact.
- Do not recommend actions that the supplied evidence does not justify.

ACTION BOUNDARY:
The system can autonomously execute only actions explicitly supported by the supplied evidence and the downstream policy gate.
Do not recommend autonomous payment approval, payment release, supplier communication, contract modification, or other financial/operational actions unless the supplied evidence and available action capability explicitly support that action.
For an invoice mismatch caused by a verified contract amendment, it is acceptable to recommend correcting the stale PO and then reconciling the invoice against the corrected PO. Do not equate invoice reconciliation with autonomous payment authorization.

The outcome is an investigation recommendation only. It is NOT authorization to execute an action. A separate deterministic policy gate has final authority over whether an action may be executed.

When recommending auto-resolution, identify the specific correction that is supported by the evidence and explain why the evidence is sufficient for that correction.
When evidence is incomplete, state exactly what is unknown and whether that uncertainty blocks resolution of the current exception or only requires follow-up investigation.

Use only the supplied evidence.

EVIDENCE:
{json.dumps(evidence,default=str)}
"""

def parse_reasoning_response(response_text):
    text=response_text.strip()
    if text.startswith("```"):
        text=text.replace("```json","",1).replace("```","").strip()
    data=json.loads(text)
    confidence=float(data["confidence"])
    if 0<=confidence<=1:
        confidence*=100
    data["confidence"]=confidence
    return ReasoningResult.model_validate(data)

def run_reasoner(evidence_pack,model=MODEL,connection=None):
    prompt=build_reasoning_prompt(evidence_pack)
    schema_json=json.dumps(RESPONSE_SCHEMA)
    conn=connection or get_connection()
    owns_connection=connection is None
    cur=conn.cursor()
    try:
        cur.execute(
            """SELECT AI_COMPLETE(
                model => %s,
                prompt => %s,
                model_parameters => PARSE_JSON(%s),
                response_format => PARSE_JSON(%s)
            )""",
            (model,prompt,json.dumps({"temperature":0}),schema_json)
        )
        result=cur.fetchone()[0]
        if isinstance(result,dict):
            result=json.dumps(result)
        return parse_reasoning_response(result)
    finally:
        cur.close()
        if owns_connection:
            conn.close()