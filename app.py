import streamlit as st
from src.core.snowflake_client import get_connection
from src.tools.evidence_pack import build_evidence_pack

st.set_page_config(page_title="Autonomous Exception Resolver",page_icon="⚡",layout="wide")

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

@st.cache_resource
def get_app_connection():
    return get_connection()

def query_one(sql,params=()):
    conn=get_app_connection()
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

def query_all(sql,params=()):
    conn=get_app_connection()
    cur=conn.cursor()
    try:
        cur.execute(sql,params)
        rows=cur.fetchall()
        columns=[d[0] for d in cur.description]
        return [dict(zip(columns,row)) for row in rows]
    finally:
        cur.close()

def money(value):
    if value is None:
        return "—"
    try:
        return f"₹{float(value):,.2f}"
    except (TypeError,ValueError):
        return str(value)

def render_timeline(timeline):
    for item in timeline:
        date=item.get("date") or item.get("timestamp") or item.get("created_at") or "—"
        event=item.get("event") or item.get("type") or "Event"
        detail=item.get("details") or item.get("description") or item.get("message") or ""
        c1,c2=st.columns([1,4])
        with c1:
            st.markdown(f"**{date}**")
        with c2:
            st.markdown(f"**{event}**")
            if detail:
                st.caption(str(detail))

def render_case(exception_id):
    conn=get_app_connection()
    evidence=build_evidence_pack(exception_id,connection=conn)
    exception=evidence.get("exception") or {}
    entity=evidence.get("entity_context") or {}
    financial=evidence.get("financial_evidence") or {}
    impact=evidence.get("impact_evidence") or {}
    timeline=evidence.get("timeline_evidence") or []
    communications=evidence.get("relevant_communications") or []
    amendments=evidence.get("contract_amendments") or []
    erp=evidence.get("relevant_erp_evidence") or []
    policy=evidence.get("policy_evidence") or {}
    decision=query_one(
        """SELECT * FROM EXCEPTION_RESOLVER.ENTERPRISE.RESOLUTION_DECISIONS
           WHERE EXCEPTION_ID=%s
           ORDER BY DECIDED_AT DESC
           LIMIT 1""",
        (exception_id,)
    )
    action=query_one(
        """SELECT * FROM EXCEPTION_RESOLVER.ENTERPRISE.RESOLUTION_ACTIONS
           WHERE EXCEPTION_ID=%s
           ORDER BY EXECUTED_AT DESC
           LIMIT 1""",
        (exception_id,)
    )
    audit=query_one(
    """SELECT * FROM EXCEPTION_RESOLVER.ENTERPRISE.EXCEPTION_AUDIT_LOG
       WHERE EXCEPTION_ID=%s
       ORDER BY TIMESTAMP DESC
       LIMIT 1""",
    (exception_id,)
)
    status=exception.get("STATUS") or "OPEN"
    exception_type=exception.get("EXCEPTION_TYPE") or "UNKNOWN"
    severity=exception.get("SEVERITY") or "—"

    st.divider()
    c1,c2,c3,c4=st.columns(4)
    with c1:
        st.metric("Exception",exception_id)
    with c2:
        st.metric("Type",exception_type.replace("_"," ").title())
    with c3:
        st.metric("Severity",severity)
    with c4:
        st.metric("Status",status)

    st.divider()
    st.subheader("🕐 Reconstructed timeline")
    if timeline:
        render_timeline(timeline)
    else:
        st.caption("No timeline evidence available.")

    st.divider()
    left,right=st.columns(2)

    with left:
        st.subheader("🔎 Evidence")
        if amendments:
            st.success(f"✓ {len(amendments)} contract amendment(s)")
        if communications:
            st.success(f"✓ {len(communications)} relevant supplier communication(s)")
        if erp:
            st.success(f"✓ {len(erp)} relevant ERP event(s)")
        if timeline:
            st.success("✓ Cross-source timeline reconstructed")
        if not any([amendments,communications,erp,timeline]):
            st.info("No supporting evidence records found.")

    with right:
        st.subheader("📊 Business impact")
        summary=impact.get("summary") if isinstance(impact,dict) else impact
        if summary:
            st.write(summary)
        else:
            st.caption("No impact summary available.")

    st.divider()
    st.subheader("🧠 Evidence used by the investigator")

    tabs=st.tabs(["Entity context","Financial evidence","Communications","ERP evidence","Policy evidence"])

    with tabs[0]:
        st.json(entity)

    with tabs[1]:
        st.json(financial)

    with tabs[2]:
        st.json(communications)

    with tabs[3]:
        st.json(erp)

    with tabs[4]:
        st.json(policy)

    st.divider()
    st.subheader("🧠 Why did the system decide this?")

    if decision:
        explanation=decision.get("DECISION_EXPLANATION")
        if explanation:
            st.info(explanation)
        else:
            st.info("Decision explanation was not persisted.")
    else:
        st.info("No persisted decision exists for this exception yet.")

    st.divider()
    st.subheader("🛡️ Decision")

    if decision:
        c1,c2,c3,c4=st.columns(4)
        with c1:
            st.metric("LLM recommendation",decision.get("LLM_OUTCOME") or "—")
        with c2:
            confidence=decision.get("CONFIDENCE")
            st.metric("Confidence",f"{float(confidence):.0f}%" if confidence is not None else "—")
        with c3:
            st.metric("Policy gate",decision.get("AUTHORIZED_OUTCOME") or decision.get("OUTCOME") or "—")
        with c4:
            action_type=action.get("ACTION_TYPE") if action else None
            st.metric("Action",(action_type or "—").replace("_"," "))

    if action:
        st.caption(f"Execution: {action.get('EXECUTION_STATUS') or '—'}")
        st.caption(f"Verification: {action.get('VERIFICATION_STATUS') or '—'}")

    st.divider()
    st.subheader("✓ Closed-loop verification")

    if action:
        verification=action.get("VERIFICATION_STATUS")
        if verification=="VERIFIED":
            st.success("Post-action verification passed")
        else:
            st.warning(f"Verification status: {verification or 'PENDING'}")
    if audit:
        st.success("Audit record created")
    else:
        st.warning("No audit record found.")

    with st.expander("Raw persisted action"):
        if action:
            st.json(action)
        else:
            st.caption("No action record.")

st.title("⚡ Autonomous Exception Resolver")
st.caption("Enterprise Exception Investigation & Resolution")

with st.sidebar:
    st.header("Exception Investigator")
    selected=st.selectbox(
        "Select exception",
        list(CASES.keys()),
        format_func=lambda x:f"{x} · {CASES[x]}"
    )
    st.divider()
    st.caption("LIVE DATA")
    st.caption("Snowflake · EXCEPTION_RESOLVER")
    st.caption("No new LLM call is made when browsing cases.")

try:
    render_case(selected)
except Exception as exc:
    st.error(f"Unable to load {selected}: {exc}")
    st.exception(exc)