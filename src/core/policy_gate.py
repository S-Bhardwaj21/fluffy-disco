from datetime import date,datetime
from typing import Any

def _as_date(value):
    if isinstance(value,datetime):
        return value.date()
    if isinstance(value,date):
        return value
    if value is None:
        return None
    return date.fromisoformat(str(value)[:10])

def _as_float(value):
    if value is None:
        return None
    return float(value)

def evaluate_policy_gate(evidence_pack:dict[str,Any],reasoning_result:dict[str,Any]|Any)->dict[str,Any]:
    exception=evidence_pack["exception"]
    entity=evidence_pack.get("entity_context") or {}
    invoice=entity.get("invoice") or {}
    purchase_order=entity.get("purchase_order") or {}
    amendments=evidence_pack.get("contract_amendments") or []
    policies=evidence_pack.get("policy_evidence") or []
    financial=evidence_pack.get("financial_evidence") or {}
    communications=evidence_pack.get("relevant_communications") or []
    impact=evidence_pack.get("impact_evidence") or {}
    exception_type=exception.get("EXCEPTION_TYPE","")
    passed_checks=[]
    failed_checks=[]
    blocking_reasons=[]
    policy_ids_checked=[p["POLICY_ID"] for p in policies if p.get("POLICY_ID")]
    allowed_outcome="REQUEST_EVIDENCE"
    authorization_basis="Insufficient policy evidence for autonomous action."
    invoice_amount=_as_float(invoice.get("TOTAL_AMOUNT"))
    po_amount=_as_float(purchase_order.get("TOTAL_AMOUNT")) or _as_float(financial.get("po_amount"))
    difference_pct=None
    if invoice_amount is not None and po_amount not in (None,0):
        difference_pct=abs(invoice_amount-po_amount)/po_amount*100
    invoice_date=_as_date(invoice.get("INVOICE_DATE"))
    if exception_type=="INVOICE_PO_MISMATCH":
        matching_amendment=None
        for amendment in amendments:
            amendment_date=_as_date(amendment.get("AMENDMENT_DATE"))
            new_value=_as_float(amendment.get("NEW_VALUE"))
            if amendment_date and invoice_date and amendment_date<=invoice_date and new_value is not None and invoice_amount is not None and abs(new_value-invoice_amount)<=0.01:
                matching_amendment=amendment
                break
        if matching_amendment:
            passed_checks.append("Invoice amount matches an approved amendment effective before the invoice date.")
            passed_checks.append("POL-004 allows an effective approved amendment to supersede the stale ERP value.")
        else:
            failed_checks.append("No effective amendment matching the invoice amount was found.")
            blocking_reasons.append("Invoice variance lacks matching contractual amendment authority.")
        if difference_pct is not None and difference_pct<=5:
            passed_checks.append("Invoice variance is within the POL-001 5% auto-reconciliation threshold.")
        elif matching_amendment:
            passed_checks.append("Variance exceeds 5%, but approved amendment authority is established under POL-004.")
        else:
            failed_checks.append("Invoice variance exceeds the POL-001 threshold.")
            blocking_reasons.append("Invoice variance exceeds the automatic reconciliation threshold.")
        dispute_terms=("not approved","cannot confirm","dispute","disputed","no approval","not authorize","unauthorized")
        dispute_found=any(any(term in f'{c.get("SUBJECT","")} {c.get("CONTENT","")}'.lower() for term in dispute_terms) for c in communications)
        if dispute_found and not matching_amendment:
            failed_checks.append("Relevant communications contain an unresolved pricing dispute.")
            blocking_reasons.append("Unresolved pricing dispute exists.")
        elif matching_amendment:
            passed_checks.append("No conflicting communication overrides the matching amendment authority.")
        if matching_amendment and not dispute_found:
            allowed_outcome="AUTO_RESOLVE"
            authorization_basis="POL-004: effective approved amendment matches the invoice amount and supersedes the stale ERP value."
        else:
            allowed_outcome="ESCALATE"
            authorization_basis="Automatic resolution is blocked by insufficient contractual authority or unresolved dispute."
    elif exception_type=="CONTRACT_PRICE_DRIFT":
        matching_price_amendment=None
        po_date=_as_date(purchase_order.get("PO_DATE"))
        for amendment in amendments:
            amendment_date=_as_date(amendment.get("AMENDMENT_DATE"))
            old_value=_as_float(amendment.get("OLD_VALUE"))
            new_value=_as_float(amendment.get("NEW_VALUE"))
            if amendment_date and po_date and amendment_date>=po_date and new_value is not None:
                if po_amount is not None and old_value is not None and abs(old_value-po_amount)<=0.01:
                    matching_price_amendment=amendment
                    break
        if matching_price_amendment:
            passed_checks.append("An approved contract amendment establishes the updated price basis after the PO was created.")
            passed_checks.append("POL-004 identifies the approved amendment as authoritative over the stale ERP PO value.")
            allowed_outcome="AUTO_RESOLVE"
            authorization_basis="POL-004: approved contract amendment supersedes the stale ERP purchase-order price."
        else:
            failed_checks.append("No authoritative approved amendment establishing the updated price was found.")
            blocking_reasons.append("Contract price drift lacks sufficient amendment evidence.")
            allowed_outcome="ESCALATE"
            authorization_basis="Automatic price correction is blocked because authoritative amendment evidence is missing."
    elif exception_type=="DUPLICATE_INVOICE":
        failed_checks.append("POL-002 prohibits automatic resolution of potential duplicate invoices.")
        blocking_reasons.append("Duplicate payment risk requires verification.")
        allowed_outcome="ESCALATE"
        authorization_basis="POL-002: duplicate payment risk requires human verification."
    elif exception_type=="SHIPMENT_DELAY":
        shipment_evidence=financial.get("shipment_evidence") or []
        shipment_record=shipment_evidence[0] if shipment_evidence else {}
        delay_days=shipment_record.get("delay_days")
        if delay_days is not None:
            delay_days=int(delay_days)
        if delay_days is not None and delay_days<=10:
            passed_checks.append(f"Shipment delay is {delay_days} days, within the POL-003 escalation threshold.")
        elif delay_days is not None:
            failed_checks.append(f"Shipment delay is {delay_days} days, exceeding the POL-003 10-day threshold.")
            blocking_reasons.append("Shipment delay exceeds the automatic-resolution threshold.")
        documented_commitment=any("revised delivery" in f'{c.get("SUBJECT","")} {c.get("CONTENT","")}'.lower() or "carrier confirmation" in f'{c.get("SUBJECT","")} {c.get("CONTENT","")}'.lower() for c in communications)
        if documented_commitment:
            passed_checks.append("Supplier provided documented revised delivery evidence.")
        else:
            failed_checks.append("No documented revised delivery commitment was found.")
            blocking_reasons.append("Shipment delay lacks documented revised commitment.")
        downstream_orders=impact.get("orders") or []
        downstream_exposure=len(downstream_orders)
        if downstream_exposure>1:
            blocking_reasons.append(f"Shipment affects {downstream_exposure} downstream customer orders.")
        if delay_days is not None and delay_days>10:
            allowed_outcome="ESCALATE"
            authorization_basis="POL-003: shipment delay exceeds the 10-day escalation threshold."
        elif downstream_exposure>1:
            allowed_outcome="ESCALATE"
            authorization_basis="POL-003: shipment delay affects multiple downstream customer orders."
        elif delay_days is not None and delay_days<=10 and documented_commitment:
            allowed_outcome="AUTO_RESOLVE"
            authorization_basis="POL-003: delay is within tolerance, revised commitment is documented, and downstream exposure is limited."
        else:
            allowed_outcome="REQUEST_EVIDENCE"
            authorization_basis="Shipment evidence is insufficient for autonomous resolution."
    elif exception_type=="PAYMENT_POLICY_VIOLATION":
        policy_conflict=any("net30" in f'{c.get("SUBJECT","")} {c.get("CONTENT","")}'.lower() and "accelerated payment" in f'{c.get("SUBJECT","")} {c.get("CONTENT","")}'.lower() for c in communications)
        if policy_conflict:
            passed_checks.append("Communication explicitly documents payment terms conflicting with the requested payment timing.")
            failed_checks.append("Payment terms conflict with the active contract policy.")
            blocking_reasons.append("Contract payment terms require approval before payment.")
        else:
            failed_checks.append("No sufficient evidence establishes the payment-policy conflict.")
            blocking_reasons.append("Payment-policy conflict requires additional evidence.")
        allowed_outcome="ESCALATE"
        authorization_basis="POL-004/POL-005: contract payment terms must be honored and conflicting payment requests require review."
    elif exception_type=="ORDER_DATA_CONFLICT":
        customer_change=False
        erp_conflict=False
        for event in evidence_pack.get("timeline_evidence") or []:
            text=str(event.get("description","")).lower()
            if "customer requested" in text and "quantity" in text:
                customer_change=True
            if "erp retained" in text or "erp update" in text:
                erp_conflict=True
        for communication in communications:
            text=f'{communication.get("SUBJECT","")} {communication.get("CONTENT","")}'.lower()
            if "customer requested" in text and "quantity" in text:
                customer_change=True
        if customer_change and erp_conflict:
            passed_checks.append("Customer and ERP records contain conflicting order state.")
            blocking_reasons.append("Authoritative final order quantity has not been established.")
        else:
            blocking_reasons.append("Order conflict evidence is incomplete.")
        allowed_outcome="REQUEST_EVIDENCE"
        authorization_basis="POL-005: conflicting order evidence requires confirmation of the authoritative final state."
    llm_outcome=getattr(reasoning_result,"outcome",None) if not isinstance(reasoning_result,dict) else reasoning_result.get("outcome")
    policy_evaluations=[]
    for policy_id in policy_ids_checked:
        if policy_id=="POL-001":
            if difference_pct is None:
                result="REVIEW"
                reason="Invoice variance could not be calculated from the available financial evidence."
            elif difference_pct<=5:
                result="PASS"
                reason=f"Invoice variance is {difference_pct:.2f}%, within the 5% automatic reconciliation threshold."
            else:
                result="REVIEW"
                reason=f"Invoice variance is {difference_pct:.2f}%, exceeding the 5% automatic reconciliation threshold."
        elif policy_id=="POL-002":
            if exception_type=="DUPLICATE_INVOICE":
                result="REVIEW"
                reason="Potential duplicate invoice detected; POL-002 requires verification before resolution."
            else:
                result="NOT_APPLICABLE"
                reason="POL-002 applies to duplicate-invoice exceptions and is not applicable to this exception type."
        elif policy_id=="POL-003":
            if exception_type=="SHIPMENT_DELAY":
                result="PASS" if allowed_outcome=="AUTO_RESOLVE" else "REVIEW"
                reason=authorization_basis if "POL-003" in authorization_basis else "Shipment policy was evaluated for the detected shipment exception."
            else:
                result="NOT_APPLICABLE"
                reason="POL-003 applies to shipment-delay exceptions and is not applicable to this exception type."
        elif policy_id=="POL-004":
            if exception_type in ("INVOICE_PO_MISMATCH","CONTRACT_PRICE_DRIFT") and any("POL-004" in check for check in passed_checks):
                result="PASS"
                reason="An approved contract amendment provides authoritative pricing evidence over the stale ERP value."
            else:
                result="NOT_APPLICABLE"
                reason="No applicable contract-authority condition was triggered for this exception."
        elif policy_id=="POL-005":
            evidence_sufficiency=getattr(reasoning_result,"evidence_sufficiency",None) if not isinstance(reasoning_result,dict) else reasoning_result.get("evidence_sufficiency")
            if evidence_sufficiency=="SUFFICIENT":
                result="PASS"
                reason="Evidence is sufficient and no unresolved evidence conflict was identified."
            elif evidence_sufficiency=="CONFLICTING":
                result="REVIEW"
                reason="Evidence contains conflicting information requiring review."
            else:
                result="REVIEW"
                reason="Evidence is incomplete or insufficient for autonomous resolution."
        else:
            result="REVIEW"
            reason="Policy was included in the evaluation set but no policy-specific evaluation rule is defined."
        policy_evaluations.append({
            "policy_id":policy_id,
            "result":result,
            "reason":reason,
            "evidence":{
                "passed_checks":passed_checks,
                "failed_checks":failed_checks,
                "blocking_reasons":blocking_reasons
            }
        })
    return {
        "exception_id":exception.get("EXCEPTION_ID"),
        "allowed_outcome":allowed_outcome,
        "policy_ids_checked":policy_ids_checked,
        "passed_checks":passed_checks,
        "failed_checks":failed_checks,
        "blocking_reasons":blocking_reasons,
        "authorization_basis":authorization_basis,
        "llm_recommended_outcome":llm_outcome,
        "llm_recommendation_overridden":llm_outcome!=allowed_outcome,
        "policy_evaluations":policy_evaluations,
    }