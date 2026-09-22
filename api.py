from fastapi import FastAPI,HTTPException
from fastapi.middleware.cors import CORSMiddleware
from src.core.snowflake_client import get_connection
from src.tools.evidence_pack import build_evidence_pack
from src.analysis_engine import (
    discover_impact_propagation,
    detect_state_divergence,
    simulate_counterfactual,
    scan_state_divergences,
)

app=FastAPI(title="Autonomous Exception Resolver API",version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

CASES={
    "EXC-0001":"Invoice mismatch — approved amendment",
    "EXC-0002":"Invoice mismatch — disputed variance",
    "EXC-0003":"Contract price drift — stale ERP value",
    "EXC-0004":"Duplicate invoice",
    "EXC-0005":"Shipment delay — within tolerance",
    "EXC-0006":"Shipment delay — downstream impact",
    "EXC-0007":"Payment terms conflict",
    "EXC-0008":"Order data conflict",
}

def query_one(conn,sql,params=()):
    cur=conn.cursor()
    try:
        cur.execute(sql,params)
        row=cur.fetchone()
        if row is None:
            return None
        columns=[d[0] for d in cur.description]
        return dict(zip(columns,row))
    finally:
        cur.close()

def query_all(conn,sql,params=()):
    cur=conn.cursor()
    try:
        cur.execute(sql,params)
        rows=cur.fetchall()
        columns=[d[0] for d in cur.description]
        return [dict(zip(columns,row)) for row in rows]
    finally:
        cur.close()

def json_safe(value):
    if value is None:
        return None
    if isinstance(value,dict):
        return {str(k).lower():json_safe(v) for k,v in value.items()}
    if isinstance(value,(list,tuple)):
        return [json_safe(v) for v in value]
    if hasattr(value,"isoformat"):
        return value.isoformat()
    try:
        import decimal
        if isinstance(value,decimal.Decimal):
            return float(value)
    except Exception:
        pass
    return value

def get_exception(conn,exception_id):
    return query_one(
        conn,
        """SELECT *
           FROM EXCEPTION_RESOLVER.ENTERPRISE.EXCEPTIONS
           WHERE EXCEPTION_ID=%s
           LIMIT 1""",
        (exception_id,),
    )

def get_decision(conn,exception_id):
    return query_one(
        conn,
        """SELECT *
           FROM EXCEPTION_RESOLVER.ENTERPRISE.RESOLUTION_DECISIONS
           WHERE EXCEPTION_ID=%s
           ORDER BY DECIDED_AT DESC
           LIMIT 1""",
        (exception_id,),
    )

def get_action(conn,exception_id):
    return query_one(
        conn,
        """SELECT *
           FROM EXCEPTION_RESOLVER.ENTERPRISE.RESOLUTION_ACTIONS
           WHERE EXCEPTION_ID=%s
           ORDER BY EXECUTED_AT DESC
           LIMIT 1""",
        (exception_id,),
    )

def get_policy_evaluations(conn,exception_id):
    return query_all(
        conn,
        """SELECT *
           FROM EXCEPTION_RESOLVER.ENTERPRISE.POLICY_EVALUATIONS
           WHERE EXCEPTION_ID=%s
           ORDER BY EVALUATED_AT DESC""",
        (exception_id,),
    )

def get_audit(conn,exception_id):
    return query_all(
        conn,
        """SELECT *
           FROM EXCEPTION_RESOLVER.ENTERPRISE.EXCEPTION_AUDIT_LOG
           WHERE EXCEPTION_ID=%s
           ORDER BY TIMESTAMP ASC""",
        (exception_id,),
    )

@app.get("/api/health")
def health():
    return {"status":"ok","service":"autonomous-exception-resolver"}

@app.get("/api/exceptions")
def list_exceptions():
    conn=get_connection()
    try:
        rows=query_all(
            conn,
            """SELECT *
               FROM EXCEPTION_RESOLVER.ENTERPRISE.EXCEPTIONS
               ORDER BY DETECTED_AT DESC, EXCEPTION_ID"""
        )
        return {
            "exceptions":json_safe(rows),
            "count":len(rows),
        }
    finally:
        conn.close()

@app.get("/api/analysis/state-divergences")
def state_divergences():
    conn=get_connection()
    try:
        results=scan_state_divergences(conn)
        return json_safe({
            "divergences":results,
            "count":len(results),
        })
    finally:
        conn.close()

@app.get("/api/exceptions/{exception_id}")
def get_exception_investigation(exception_id:str):
    exception_id=exception_id.upper().strip()
    conn=get_connection()
    try:
        exception=get_exception(conn,exception_id)
        if exception is None:
            raise HTTPException(status_code=404,detail=f"Exception {exception_id} not found")

        evidence=build_evidence_pack(exception_id,connection=conn) or {}
        decision=get_decision(conn,exception_id)
        action=get_action(conn,exception_id)
        policy_evaluations=get_policy_evaluations(conn,exception_id)
        audit=get_audit(conn,exception_id)

        impact=None
        try:
            impact=discover_impact_propagation(conn,exception_id)
        except Exception:
            impact=None

        state_divergence=None
        try:
            state_divergence=detect_state_divergence(conn,exception_id)
        except Exception:
            state_divergence=None

        counterfactual=None
        try:
            counterfactual=simulate_counterfactual(conn,exception_id)
        except Exception:
            counterfactual=None

        return json_safe({
            "exception":exception,
            "case_label":CASES.get(exception_id),
            "entity_context":evidence.get("entity_context") or {},
            "evidence":{
                "summary":evidence.get("evidence_summary"),
                "financial":evidence.get("financial_evidence") or {},
                "timeline":evidence.get("timeline_evidence") or [],
                "communications":evidence.get("relevant_communications") or [],
                "contract_amendments":evidence.get("contract_amendments") or [],
                "erp":evidence.get("relevant_erp_evidence") or [],
                "policy":evidence.get("policy_evidence") or {},
            },
            "impact":{
                "evidence":evidence.get("impact_evidence") or {},
                "propagation":impact,
            },
            "state_divergence":state_divergence,
            "counterfactual":counterfactual,
            "decision":decision,
            "policy_evaluations":policy_evaluations,
            "action":action,
            "verification":{
                "status":action.get("VERIFICATION_STATUS") if action else None,
                "details":action.get("VERIFICATION_DETAILS") if action else None,
            },
            "audit":audit,
        })
    finally:
        conn.close()
@app.get("/")
def root():
    return {
        "service":"Autonomous Enterprise Exception Resolution Engine",
        "status":"online",
        "health":"/api/health"
    }