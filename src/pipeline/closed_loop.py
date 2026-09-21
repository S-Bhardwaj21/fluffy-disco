import json
from src.core.snowflake_client import get_connection
from src.tools.evidence_pack import build_evidence_pack
from src.agents.reasoner import run_reasoner
from src.core.policy_gate import evaluate_policy_gate
from src.core.action_engine import (
    persist_evidence_pack,
    persist_decision,
    persist_policy_evaluation,
    execute_action,
    verify_action,
    determine_final_status,
    update_exception_status,
    write_audit_log,
)

def run_exception(exception_id,connection=None,dry_run=True):
    conn=connection or get_connection()
    owns_connection=connection is None
    try:
        print(f"\n{'='*70}")
        print(f"PROCESSING {exception_id}")
        print(f"{'='*70}")
        print("[1/8] BUILD EVIDENCE")
        evidence_pack=build_evidence_pack(exception_id,connection=conn)
        print(f"      Evidence pack built: {exception_id}")
        print("[2/8] LLM REASONING")
        reasoning=run_reasoner(evidence_pack,connection=conn)
        print(f"      LLM outcome: {reasoning.outcome}")
        print(f"      Confidence: {reasoning.confidence:.1f}")
        print("[3/8] POLICY GATE")
        policy=evaluate_policy_gate(evidence_pack,reasoning)
        print(f"      Authorized outcome: {policy['allowed_outcome']}")
        print(f"      Overridden: {policy['llm_recommendation_overridden']}")
        print("[4/8] PERSIST EVIDENCE")
        evidence_id=persist_evidence_pack(conn,evidence_pack)
        print(f"      Evidence ID: {evidence_id}")
        print("[5/8] PERSIST DECISION")
        decision_id=persist_decision(conn,evidence_pack,reasoning,policy)
        print(f"      Decision ID: {decision_id}")
        print("[6/8] POLICY EVALUATION")
        evaluation_ids=persist_policy_evaluation(conn,evidence_pack,policy)
        print(f"      Policies evaluated: {len(evaluation_ids)}")
        print("[7/8] EXECUTE ACTION")
        action=execute_action(conn,evidence_pack,policy,dry_run=dry_run)
        print(f"      Action: {action['action_type']}")
        print(f"      Execution: {action['execution_status']}")
        print("[8/8] VERIFY + AUDIT")
        verification=verify_action(conn,evidence_pack,policy,action,dry_run=dry_run)
        status=determine_final_status(action,verification)
        update_exception_status(conn,exception_id,status)
        audit_id=write_audit_log(conn,evidence_pack,reasoning,policy,action,verification)
        print(f"      Verification: {verification['verification_status']}")
        print(f"      Final status: {status}")
        print(f"      Audit ID: {audit_id}")
        conn.commit()
        return {
            "exception_id":exception_id,
            "llm_outcome":reasoning.outcome,
            "confidence":reasoning.confidence,
            "allowed_outcome":policy["allowed_outcome"],
            "overridden":policy["llm_recommendation_overridden"],
            "evidence_id":evidence_id,
            "decision_id":decision_id,
            "evaluation_ids":evaluation_ids,
            "action":action,
            "verification":verification,
            "final_status":status,
            "audit_id":audit_id,
        }
    except Exception:
        conn.rollback()
        raise
    finally:
        if owns_connection:
            conn.close()

def run_flagship_cases(dry_run=True):
    conn=get_connection()
    results=[]
    try:
        for exception_id in [
            "EXC-0001",
            "EXC-0002",
            "EXC-0003",
            "EXC-0004",
            "EXC-0005",
            "EXC-0006",
            "EXC-0007",
            "EXC-0008",
        ]:
            results.append(run_exception(exception_id,connection=conn,dry_run=dry_run))
        return results
    finally:
        conn.close()

if __name__=="__main__":
    results=run_flagship_cases(dry_run=True)
    print("\n\nFLAGSHIP SUMMARY")
    print(json.dumps([
        {
            "exception_id":r["exception_id"],
            "llm_outcome":r["llm_outcome"],
            "allowed_outcome":r["allowed_outcome"],
            "action":r["action"]["action_type"],
            "verification":r["verification"]["verification_status"],
            "final_status":r["final_status"],
        }
        for r in results
    ],indent=2))