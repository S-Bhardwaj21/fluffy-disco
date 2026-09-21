import json
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

def _now():
    return datetime.utcnow()

def _action_id():
    return f"ACT-{uuid.uuid4().hex[:12].upper()}"

def _decision_id():
    return f"DEC-{uuid.uuid4().hex[:12].upper()}"

def _evaluation_id():
    return f"POL-{uuid.uuid4().hex[:12].upper()}"

def _as_float(value):
    if value is None:
        return None
    return float(value)

def _reasoning_value(reasoning_result,key,default=None):
    if isinstance(reasoning_result,dict):
        return reasoning_result.get(key,default)
    return getattr(reasoning_result,key,default)

def persist_evidence_pack(conn,evidence_pack):
    exception=evidence_pack["exception"]
    evidence_pack_id=f"EVP-{uuid.uuid4().hex[:12].upper()}"
    entity_context=evidence_pack.get("entity_context") or {}
    financial=evidence_pack.get("financial_evidence") or {}
    timeline=evidence_pack.get("timeline_evidence") or []
    communications=evidence_pack.get("relevant_communications") or []
    policies=evidence_pack.get("policy_evidence") or []
    impact=evidence_pack.get("impact_evidence") or {}
    summary=impact.get("summary","")
    if not isinstance(summary,str):
        summary=json.dumps(summary,default=str)
    cur=conn.cursor()
    try:
        cur.execute(
            """INSERT INTO EVIDENCE_PACKS
            (EVIDENCE_PACK_ID,EXCEPTION_ID,CREATED_AT,ENTITY_CONTEXT,FINANCIAL_EVIDENCE,TIMELINE_EVIDENCE,COMMUNICATION_EVIDENCE,POLICY_EVIDENCE,IMPACT_EVIDENCE,EVIDENCE_SUMMARY)
            SELECT %s,%s,%s,PARSE_JSON(%s),PARSE_JSON(%s),PARSE_JSON(%s),PARSE_JSON(%s),PARSE_JSON(%s),PARSE_JSON(%s),%s""",
            (
                evidence_pack_id,
                exception["EXCEPTION_ID"],
                _now(),
                json.dumps(entity_context,default=str),
                json.dumps(financial,default=str),
                json.dumps(timeline,default=str),
                json.dumps(communications,default=str),
                json.dumps(policies,default=str),
                json.dumps(impact,default=str),
                summary
            )
        )
        return evidence_pack_id
    finally:
        cur.close()

def persist_decision(conn,evidence_pack,reasoning_result,policy_result):
    exception_id=evidence_pack["exception"]["EXCEPTION_ID"]
    decision_id=_decision_id()
    llm_outcome=_reasoning_value(reasoning_result,"outcome","")
    authorized_outcome=policy_result["allowed_outcome"]
    confidence=_as_float(_reasoning_value(reasoning_result,"confidence",0))
    if confidence is not None and confidence<=1:
        confidence*=100
    cur=conn.cursor()
    try:
        cur.execute(
            """INSERT INTO RESOLUTION_DECISIONS
            (DECISION_ID,EXCEPTION_ID,DECIDED_AT,ROOT_CAUSE,IMPACT_SUMMARY,RECOMMENDED_ACTION,OUTCOME,CONFIDENCE,POLICY_CHECK,EVIDENCE_SUFFICIENCY,DECISION_EXPLANATION,LLM_OUTCOME,AUTHORIZED_OUTCOME)
            SELECT %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s""",
            (
                decision_id,
                exception_id,
                _now(),
                _reasoning_value(reasoning_result,"root_cause",""),
                _reasoning_value(reasoning_result,"impact_summary",""),
                _reasoning_value(reasoning_result,"recommended_action",""),
                authorized_outcome,
                confidence,
                policy_result["authorization_basis"],
                _reasoning_value(reasoning_result,"evidence_sufficiency",""),
                _reasoning_value(reasoning_result,"decision_explanation",""),
                llm_outcome,
                authorized_outcome
            )
        )
        return decision_id
    finally:
        cur.close()

def persist_policy_evaluation(conn,evidence_pack,policy_result):
    exception_id=evidence_pack["exception"]["EXCEPTION_ID"]
    evaluation_ids=[]
    cur=conn.cursor()
    try:
        for evaluation in policy_result.get("policy_evaluations",[]):
            evaluation_id=_evaluation_id()
            cur.execute(
                """INSERT INTO POLICY_EVALUATIONS
                (EVALUATION_ID,EXCEPTION_ID,POLICY_ID,EVALUATED_AT,RESULT,REASON,EVIDENCE_USED)
                SELECT %s,%s,%s,%s,%s,%s,PARSE_JSON(%s)""",
                (
                    evaluation_id,
                    exception_id,
                    evaluation["policy_id"],
                    _now(),
                    evaluation["result"],
                    evaluation["reason"],
                    json.dumps(evaluation["evidence"])
                )
            )
            evaluation_ids.append(evaluation_id)
        return evaluation_ids
    finally:
        cur.close()

def _build_action(evidence_pack,policy_result):
    exception=evidence_pack["exception"]
    exception_id=exception["EXCEPTION_ID"]
    exception_type=exception["EXCEPTION_TYPE"]
    outcome=policy_result["allowed_outcome"]
    entity=evidence_pack.get("entity_context") or {}
    invoice=entity.get("invoice") or {}
    purchase_order=entity.get("purchase_order") or {}
    amendments=evidence_pack.get("contract_amendments") or []
    if outcome=="AUTO_RESOLVE" and exception_type in {"INVOICE_PO_MISMATCH","CONTRACT_PRICE_DRIFT"}:
        amendment=None
        invoice_amount=_as_float(invoice.get("TOTAL_AMOUNT"))
        po_amount=_as_float(purchase_order.get("TOTAL_AMOUNT"))
        for candidate in amendments:
            new_value=_as_float(candidate.get("NEW_VALUE"))
            if new_value is None:
                continue
            if exception_type=="INVOICE_PO_MISMATCH" and invoice_amount is not None and abs(new_value-invoice_amount)<=0.01:
                amendment=candidate
                break
            if exception_type=="CONTRACT_PRICE_DRIFT" and po_amount is not None:
                old_value=_as_float(candidate.get("OLD_VALUE"))
                if old_value is not None and abs(old_value-po_amount)<=0.01:
                    amendment=candidate
                    break
        if amendment:
            return {
                "action_type":"UPDATE_PO_TO_APPROVED_PRICE",
                "payload":{
                    "po_id":purchase_order.get("PO_ID"),
                    "previous_amount":po_amount,
                    "approved_amount":_as_float(amendment.get("NEW_VALUE")),
                    "amendment_id":amendment.get("AMENDMENT_ID")
                }
            }
    if outcome=="AUTO_RESOLVE" and exception_type=="SHIPMENT_DELAY":
        shipment_evidence=(evidence_pack.get("financial_evidence") or {}).get("shipment_evidence") or []
        shipment=shipment_evidence[0] if shipment_evidence else {}
        return {
            "action_type":"CLOSE_SHIPMENT_EXCEPTION",
            "payload":{
                "shipment_id":shipment.get("shipment_id"),
                "delay_days":shipment.get("delay_days"),
                "reason":"Delay is within policy tolerance and documented revised commitment exists."
            }
        }
    if outcome=="ESCALATE":
        return {
            "action_type":"ESCALATE_FOR_HUMAN_REVIEW",
            "payload":{
                "exception_type":exception_type,
                "severity":exception.get("SEVERITY"),
                "reason":policy_result["authorization_basis"]
            }
        }
    return {
        "action_type":"REQUEST_ADDITIONAL_EVIDENCE",
        "payload":{
            "exception_type":exception_type,
            "missing_evidence":policy_result.get("blocking_reasons",[]),
            "reason":policy_result["authorization_basis"]
        }
    }

def execute_action(conn,evidence_pack,policy_result,dry_run=True):
    exception=evidence_pack["exception"]
    exception_id=exception["EXCEPTION_ID"]
    action=_build_action(evidence_pack,policy_result)
    action_id=_action_id()
    action_type=action["action_type"]
    payload=action["payload"]
    execution_status="DRY_RUN" if dry_run else "EXECUTED"
    verification_status="PENDING"
    if not dry_run and action_type=="UPDATE_PO_TO_APPROVED_PRICE":
        po_id=payload["po_id"]
        approved_amount=payload["approved_amount"]
        if not po_id or approved_amount is None:
            raise ValueError("Missing PO or approved amount for autonomous update.")
        cur=conn.cursor()
        try:
            cur.execute(
                """UPDATE PURCHASE_ORDERS
                SET TOTAL_AMOUNT=%s
                WHERE PO_ID=%s""",
                (approved_amount,po_id)
            )
            if cur.rowcount!=1:
                raise RuntimeError(f"Expected exactly one PO update, got {cur.rowcount}.")
        finally:
            cur.close()
    cur=conn.cursor()
    try:
        cur.execute(
            """INSERT INTO RESOLUTION_ACTIONS
            (ACTION_ID,EXCEPTION_ID,ACTION_TYPE,ACTION_PAYLOAD,EXECUTED_AT,EXECUTION_STATUS,VERIFICATION_STATUS,VERIFICATION_DETAILS)
            SELECT %s,%s,%s,PARSE_JSON(%s),%s,%s,%s,%s""",
            (
                action_id,
                exception_id,
                action_type,
                json.dumps(payload,default=str),
                _now(),
                execution_status,
                verification_status,
                "Action created; verification pending."
            )
        )
    finally:
        cur.close()
    return {
        "action_id":action_id,
        "action_type":action_type,
        "payload":payload,
        "execution_status":execution_status,
        "verification_status":verification_status
    }

def verify_action(conn,evidence_pack,policy_result,action_result,dry_run=True):
    exception=evidence_pack["exception"]
    exception_id=exception["EXCEPTION_ID"]
    action_type=action_result["action_type"]
    payload=action_result["payload"]
    verified=False
    details=""
    cur=conn.cursor()
    try:
        if dry_run:
            verified=True
            details="Dry-run verification: action structure and authorization were validated without mutating operational data."
        elif action_type=="UPDATE_PO_TO_APPROVED_PRICE":
            cur.execute(
                """SELECT TOTAL_AMOUNT FROM PURCHASE_ORDERS WHERE PO_ID=%s""",
                (payload["po_id"],)
            )
            row=cur.fetchone()
            actual=float(row[0]) if row else None
            verified=actual is not None and abs(actual-float(payload["approved_amount"]))<=0.01
            details=f"Verified PO {payload['po_id']} amount={actual}; expected={payload['approved_amount']}."
        elif action_type=="CLOSE_SHIPMENT_EXCEPTION":
            shipment_id=payload["shipment_id"]
            cur.execute(
                """SELECT STATUS,ACTUAL_DATE,PROMISED_DATE FROM SHIPMENTS WHERE SHIPMENT_ID=%s""",
                (shipment_id,)
            )
            row=cur.fetchone()
            verified=bool(row and str(row[0]).upper()=="DELIVERED" and row[1] is not None)
            details=f"Verified shipment {shipment_id}: status={row[0] if row else None}, actual_date={row[1] if row else None}, promised_date={row[2] if row else None}."
        elif action_type=="ESCALATE_FOR_HUMAN_REVIEW":
            verified=True
            details="Verified escalation action was persisted for human review."
        elif action_type=="REQUEST_ADDITIONAL_EVIDENCE":
            verified=True
            details="Verified evidence-request action was persisted."
    finally:
        cur.close()
    verification_status="VERIFIED" if verified else "FAILED"
    cur=conn.cursor()
    try:
        cur.execute(
            """UPDATE RESOLUTION_ACTIONS
            SET VERIFICATION_STATUS=%s,VERIFICATION_DETAILS=%s
            WHERE ACTION_ID=%s""",
            (verification_status,details,action_result["action_id"])
        )
    finally:
        cur.close()
    return {
        "verified":verified,
        "verification_status":verification_status,
        "details":details
    }

def determine_final_status(action_result,verification_result):
    if not verification_result["verified"]:
        return "OPEN"
    action_type=action_result["action_type"]
    if action_type=="ESCALATE_FOR_HUMAN_REVIEW":
        return "ESCALATED"
    if action_type=="REQUEST_ADDITIONAL_EVIDENCE":
        return "PENDING_EVIDENCE"
    return "RESOLVED"

def update_exception_status(conn,exception_id,status):
    cur=conn.cursor()
    try:
        cur.execute(
            """UPDATE EXCEPTIONS SET STATUS=%s WHERE EXCEPTION_ID=%s""",
            (status,exception_id)
        )
    finally:
        cur.close()

def write_audit_log(conn,evidence_pack,reasoning_result,policy_result,action_result,verification_result):
    exception=evidence_pack["exception"]
    exception_id=exception["EXCEPTION_ID"]
    audit_id=f"AUD-{uuid.uuid4().hex[:12].upper()}"
    stage="VERIFY"
    action=action_result["action_type"]
    decision=policy_result["allowed_outcome"]
    reason=policy_result["authorization_basis"]
    evidence=json.dumps({
        "policy_checks":policy_result.get("passed_checks",[]),
        "failed_checks":policy_result.get("failed_checks",[]),
        "verification":verification_result
    },default=str)
    cur=conn.cursor()
    try:
        cur.execute(
            """INSERT INTO EXCEPTION_AUDIT_LOG
            (AUDIT_ID,EXCEPTION_ID,TIMESTAMP,STAGE,AGENT,ACTION,DECISION,REASON,EVIDENCE)
            SELECT %s,%s,%s,%s,%s,%s,%s,%s,%s""",
            (
                audit_id,
                exception_id,
                _now(),
                stage,
                "exception-resolver",
                action,
                decision,
                reason,
                evidence
            )
        )
    finally:
        cur.close()
    return audit_id