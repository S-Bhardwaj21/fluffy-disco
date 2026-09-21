from typing import Any
from src.core.snowflake_client import get_connection

_EXCEPTION_TERMS={
    "INVOICE_PO_MISMATCH":{"invoice","pricing","price","amendment","approved","approval","dispute","amount","po"},
    "CONTRACT_PRICE_DRIFT":{"contract","pricing","price","amendment","approved","approval","erp","stale","negotiated"},
    "DUPLICATE_INVOICE":{"invoice","duplicate","payment","reconciliation","amount"},
    "SHIPMENT_DELAY":{"delay","delayed","late","commitment","committed","promised","carrier","production","missed","revised"},
    "PAYMENT_POLICY_VIOLATION":{"payment","terms","contract","policy","approval","invoice"},
    "ORDER_DATA_CONFLICT":{"order","quantity","customer","erp","authorized","update","conflict"},
}

def _rows(cur,sql,params=()):
    cur.execute(sql,params)
    columns=[d[0] for d in cur.description]
    return [dict(zip(columns,row)) for row in cur.fetchall()]

def _single(cur,sql,params=()):
    rows=_rows(cur,sql,params)
    return rows[0] if rows else None

def _norm(value):
    return str(value or "").strip().lower()

def _tokens(*values):
    return {str(v).strip() for v in values if v is not None and str(v).strip()}

def _communication_relevance(row,entity_ids,exception_type,supplier_id=None):
    subject=_norm(row.get("SUBJECT"))
    content=_norm(row.get("CONTENT"))
    text=f"{subject} {content}"
    row_supplier=_norm(row.get("SUPPLIER_ID"))
    target_supplier=_norm(supplier_id)
    if not target_supplier or row_supplier!=target_supplier:
        return 0,0
    entity_ids={
        _norm(entity_id)
        for entity_id in entity_ids
        if _norm(entity_id)
    }
    if exception_type=="SHIPMENT_DELAY":
        explicit_matches=sum(
            1
            for entity_id in entity_ids
            if entity_id.startswith("shp-") or entity_id.startswith("ord-")
            if entity_id in text
        )
        if explicit_matches:
            return 3,explicit_matches
        strong_phrases={
            "shipment is delayed",
            "shipment is late",
            "shipment will arrive",
            "revised delivery commitment",
            "revised delivery estimate",
            "carrier delay",
            "production constraints",
            "beyond the committed date",
            "beyond the promised date",
            "missed the committed date",
            "missed the promised date",
        }
        strong_matches=sum(
            1
            for phrase in strong_phrases
            if phrase in text
        )
        if strong_matches>=2:
            return 2,strong_matches
        return 0,0
    if exception_type=="INVOICE_PO_MISMATCH":
        relevant_ids={
            entity_id
            for entity_id in entity_ids
            if entity_id.startswith("inv-") or entity_id.startswith("po-")
        }
        explicit_matches=sum(1 for entity_id in relevant_ids if entity_id in text)
        if explicit_matches:
            return 3,explicit_matches
    elif exception_type=="CONTRACT_PRICE_DRIFT":
        relevant_ids={
            entity_id
            for entity_id in entity_ids
            if entity_id.startswith("po-") or entity_id.startswith("con-")
        }
        explicit_matches=sum(1 for entity_id in relevant_ids if entity_id in text)
        if explicit_matches:
            return 3,explicit_matches
    elif exception_type=="DUPLICATE_INVOICE":
        relevant_ids={
            entity_id
            for entity_id in entity_ids
            if entity_id.startswith("inv-") or entity_id.startswith("po-")
        }
        explicit_matches=sum(1 for entity_id in relevant_ids if entity_id in text)
        if explicit_matches:
            return 3,explicit_matches
    elif exception_type=="PAYMENT_POLICY_VIOLATION":
        relevant_ids={
            entity_id
            for entity_id in entity_ids
            if entity_id.startswith("inv-") or entity_id.startswith("con-")
        }
        explicit_matches=sum(1 for entity_id in relevant_ids if entity_id in text)
        if explicit_matches:
            return 3,explicit_matches
    elif exception_type=="ORDER_DATA_CONFLICT":
        relevant_ids={
            entity_id
            for entity_id in entity_ids
            if entity_id.startswith("ord-")
        }
        explicit_matches=sum(1 for entity_id in relevant_ids if entity_id in text)
        if explicit_matches:
            return 3,explicit_matches
    patterns={
        "INVOICE_PO_MISMATCH":{
            "approved pricing",
            "price change",
            "revised price",
            "amended pricing",
            "price referenced",
            "billing against the existing purchase order",
            "invoice dispute",
        },
        "CONTRACT_PRICE_DRIFT":{
            "pricing adjustment",
            "negotiated adjustment",
            "new price basis",
            "amended pricing",
            "erp purchase order",
        },
        "DUPLICATE_INVOICE":{
            "duplicate invoice",
            "duplicate payment",
            "invoice already submitted",
        },
        "PAYMENT_POLICY_VIOLATION":{
            "accelerated payment",
            "payment terms",
            "active contract remains",
            "net30",
            "payment terms conflict",
        },
        "ORDER_DATA_CONFLICT":{
            "customer requested",
            "quantity change",
            "final authorized quantity",
            "erp retained",
            "erp update",
            "authorized quantity",
        },
    }
    matched=sum(
        1
        for pattern in patterns.get(exception_type,set())
        if pattern in text
    )
    if matched:
        return 2,matched
    return 0,0

def _relevant_communications(rows,entity_ids,exception_type,supplier_id=None):
    scored=[]
    for row in rows:
        score=_communication_relevance(
            row,
            entity_ids,
            exception_type,
            supplier_id,
        )
        if score[0]>0:
            scored.append((score,row))
    scored.sort(
        key=lambda x:(
            x[0][0],
            x[0][1],
            str(x[1].get("COMMUNICATION_DATE") or "")
        ),
        reverse=True
    )
    return [row for _,row in scored[:12]]

def _add_timeline(timeline,date,event_type,source_id,description):
    if date:
        timeline.append({
            "date":str(date),
            "event_type":event_type,
            "source_id":source_id,
            "description":description,
        })

def _safe_float(value):
    try:
        return float(value)
    except (TypeError,ValueError):
        return None

def _build_price_authority(amendments):
    price_authority=[]
    for amendment in amendments:
        old_value=_safe_float(amendment.get("OLD_VALUE"))
        new_value=_safe_float(amendment.get("NEW_VALUE"))
        field_changed=amendment.get("FIELD_CHANGED")
        if field_changed in ("UNIT_PRICE","PRICE","TOTAL_AMOUNT"):
            price_authority.append({
                "amendment_id":amendment.get("AMENDMENT_ID"),
                "amendment_date":amendment.get("AMENDMENT_DATE"),
                "field_changed":field_changed,
                "old_unit_price":old_value,
                "new_unit_price":new_value,
                "reason":amendment.get("REASON"),
            })
    return price_authority

def _calculate_invoice_variance(invoice,purchase_order):
    if not invoice or not purchase_order:
        return {
            "invoice_id":invoice.get("INVOICE_ID") if invoice else None,
            "invoice_amount":None,
            "po_amount":_safe_float(purchase_order.get("TOTAL_AMOUNT")) if purchase_order else None,
            "difference":round(difference,2) if difference is not None else None,
"difference_pct":round(difference_pct,2) if difference_pct is not None else None,
        }
    invoice_amount=_safe_float(invoice.get("TOTAL_AMOUNT"))
    po_amount=_safe_float(purchase_order.get("TOTAL_AMOUNT"))
    difference=(
        invoice_amount-po_amount
        if invoice_amount is not None and po_amount is not None
        else None
    )
    difference_pct=(
        difference/po_amount*100
        if difference is not None and po_amount
        else None
    )
    return {
        "invoice_id":invoice.get("INVOICE_ID"),
        "invoice_amount":invoice_amount,
        "po_amount":po_amount,
        "difference":difference,
        "difference_pct":difference_pct,
    }

def build_evidence_pack(exception_id:str,connection=None)->dict[str,Any]:
    own_connection=connection is None
    conn=connection or get_connection()
    try:
        cur=conn.cursor()
        exception=_single(
            cur,
            """
            SELECT EXCEPTION_ID,DETECTED_AT,EXCEPTION_TYPE,ENTITY_TYPE,
                   ENTITY_ID,SEVERITY,STATUS,DESCRIPTION
            FROM EXCEPTIONS
            WHERE EXCEPTION_ID=%s
            """,
            (exception_id,),
        )
        if not exception:
            raise ValueError(f"Exception not found: {exception_id}")

        exception_type=exception["EXCEPTION_TYPE"]
        entity_type=exception["ENTITY_TYPE"]
        entity_id=exception["ENTITY_ID"]

        invoice=None
        purchase_order=None
        contract=None
        shipment=None
        order=None
        duplicate_invoices=[]
        amendments=[]
        relevant_erp_evidence=[]
        communication_evidence=[]
        relevant_communications=[]
        linked_orders=[]
        linked_shipments=[]

        if entity_type=="INVOICE":
            invoice=_single(
                cur,
                "SELECT * FROM INVOICES WHERE INVOICE_ID=%s",
                (entity_id,),
            )
            if invoice:
                purchase_order=_single(
                    cur,
                    "SELECT * FROM PURCHASE_ORDERS WHERE PO_ID=%s",
                    (invoice.get("PO_ID"),),
                )
                if purchase_order:
                    contract=_single(
                        cur,
                        "SELECT * FROM CONTRACTS WHERE CONTRACT_ID=%s",
                        (purchase_order.get("CONTRACT_ID"),),
                    )
                    linked_orders=_rows(
                        cur,
                        "SELECT * FROM ORDERS WHERE PO_ID=%s ORDER BY ORDER_DATE,ORDER_ID",
                        (purchase_order.get("PO_ID"),),
                    )
                    linked_shipments=_rows(
                        cur,
                        """
                        SELECT s.*
                        FROM SHIPMENTS s
                        JOIN ORDERS o ON o.ORDER_ID=s.ORDER_ID
                        WHERE o.PO_ID=%s
                        ORDER BY s.PROMISED_DATE,s.SHIPMENT_ID
                        """,
                        (purchase_order.get("PO_ID"),),
                    )
                duplicate_invoices=_rows(
                    cur,
                    """
                    SELECT *
                    FROM INVOICES
                    WHERE SUPPLIER_ID=%s
                      AND PO_ID=%s
                      AND ABS(TOTAL_AMOUNT-%s)<0.01
                    ORDER BY INVOICE_DATE,INVOICE_ID
                    """,
                    (
                        invoice.get("SUPPLIER_ID"),
                        invoice.get("PO_ID"),
                        invoice.get("TOTAL_AMOUNT"),
                    ),
                )

        elif entity_type=="PURCHASE_ORDER":
            purchase_order=_single(
                cur,
                "SELECT * FROM PURCHASE_ORDERS WHERE PO_ID=%s",
                (entity_id,),
            )
            if purchase_order:
                contract=_single(
                    cur,
                    "SELECT * FROM CONTRACTS WHERE CONTRACT_ID=%s",
                    (purchase_order.get("CONTRACT_ID"),),
                )
                invoice=_single(
                    cur,
                    """
                    SELECT *
                    FROM INVOICES
                    WHERE PO_ID=%s
                    ORDER BY INVOICE_DATE DESC,INVOICE_ID DESC
                    LIMIT 1
                    """,
                    (entity_id,),
                )
                linked_orders=_rows(
                    cur,
                    "SELECT * FROM ORDERS WHERE PO_ID=%s ORDER BY ORDER_DATE,ORDER_ID",
                    (entity_id,),
                )
                linked_shipments=_rows(
                    cur,
                    """
                    SELECT s.*
                    FROM SHIPMENTS s
                    JOIN ORDERS o ON o.ORDER_ID=s.ORDER_ID
                    WHERE o.PO_ID=%s
                    ORDER BY s.PROMISED_DATE,s.SHIPMENT_ID
                    """,
                    (entity_id,),
                )

        elif entity_type=="SHIPMENT":
            shipment=_single(
                cur,
                "SELECT * FROM SHIPMENTS WHERE SHIPMENT_ID=%s",
                (entity_id,),
            )
            if shipment:
                order=_single(
                    cur,
                    "SELECT * FROM ORDERS WHERE ORDER_ID=%s",
                    (shipment.get("ORDER_ID"),),
                )
                if order:
                    purchase_order=_single(
                        cur,
                        "SELECT * FROM PURCHASE_ORDERS WHERE PO_ID=%s",
                        (order.get("PO_ID"),),
                    )
                    if purchase_order:
                        contract=_single(
                            cur,
                            "SELECT * FROM CONTRACTS WHERE CONTRACT_ID=%s",
                            (purchase_order.get("CONTRACT_ID"),)
                        )
                        invoice=_single(
                            cur,
                            """
                            SELECT *
                            FROM INVOICES
                            WHERE PO_ID=%s
                            ORDER BY INVOICE_DATE DESC,INVOICE_ID DESC
                            LIMIT 1
                            """,
                            (purchase_order.get("PO_ID"),),
                        )
                linked_orders=[order] if order else []
                linked_shipments=[shipment]

        elif entity_type=="ORDER":
            order=_single(
                cur,
                "SELECT * FROM ORDERS WHERE ORDER_ID=%s",
                (entity_id,),
            )
            if order:
                purchase_order=_single(
                    cur,
                    "SELECT * FROM PURCHASE_ORDERS WHERE PO_ID=%s",
                    (order.get("PO_ID"),),
                )
                if purchase_order:
                    contract=_single(
                        cur,
                        "SELECT * FROM CONTRACTS WHERE CONTRACT_ID=%s",
                        (purchase_order.get("CONTRACT_ID"),),
                    )
                    invoice=_single(
                        cur,
                        """
                        SELECT *
                        FROM INVOICES
                        WHERE PO_ID=%s
                        ORDER BY INVOICE_DATE DESC,INVOICE_ID DESC
                        LIMIT 1
                        """,
                        (purchase_order.get("PO_ID"),),
                    )
                linked_orders=[order]
                linked_shipments=_rows(
                    cur,
                    "SELECT * FROM SHIPMENTS WHERE ORDER_ID=%s ORDER BY PROMISED_DATE,SHIPMENT_ID",
                    (entity_id,),
                )

        if contract:
            amendments=_rows(
                cur,
                """
                SELECT *
                FROM CONTRACT_AMENDMENTS
                WHERE CONTRACT_ID=%s
                ORDER BY AMENDMENT_DATE,AMENDMENT_ID
                """,
                (contract.get("CONTRACT_ID"),),
            )

        linked_ids=_tokens(
            entity_id,
            invoice.get("INVOICE_ID") if invoice else None,
            purchase_order.get("PO_ID") if purchase_order else None,
            purchase_order.get("CONTRACT_ID") if purchase_order else None,
            shipment.get("SHIPMENT_ID") if shipment else None,
            shipment.get("ORDER_ID") if shipment else None,
            order.get("ORDER_ID") if order else None,
        )

        supplier_id=None
        if invoice:
            supplier_id=invoice.get("SUPPLIER_ID")
        elif purchase_order:
            supplier_id=purchase_order.get("SUPPLIER_ID")
        elif shipment:
            supplier_id=shipment.get("SUPPLIER_ID")
        elif order and purchase_order:
            supplier_id=purchase_order.get("SUPPLIER_ID")

        communication_evidence=_rows(
            cur,
            """
            SELECT *
            FROM SUPPLIER_COMMUNICATIONS
            WHERE COMMUNICATION_DATE<=(
                SELECT DETECTED_AT
                FROM EXCEPTIONS
                WHERE EXCEPTION_ID=%s
            )
            ORDER BY COMMUNICATION_DATE,COMMUNICATION_ID
            """,
            (exception_id,),
        )

        relevant_communications=_relevant_communications(
            communication_evidence,
            linked_ids,
            exception_type,
            supplier_id,
        )

        entity_event_ids=_tokens(
            entity_id,
            invoice.get("INVOICE_ID") if invoice else None,
            purchase_order.get("PO_ID") if purchase_order else None,
            order.get("ORDER_ID") if order else None,
            shipment.get("SHIPMENT_ID") if shipment else None,
        )

        if entity_event_ids:
            placeholders=",".join(["%s"]*len(entity_event_ids))
            relevant_erp_evidence=_rows(
                cur,
                f"""
                SELECT *
                FROM ERP_EVENTS
                WHERE EVENT_TIMESTAMP<=(
                    SELECT DETECTED_AT
                    FROM EXCEPTIONS
                    WHERE EXCEPTION_ID=%s
                )
                AND ENTITY_ID IN ({placeholders})
                ORDER BY EVENT_TIMESTAMP,EVENT_ID
                """,
                (exception_id,*entity_event_ids),
            )

        financial_evidence={}

        price_authority=_build_price_authority(amendments)

        if invoice and purchase_order:
            variance=_calculate_invoice_variance(
                invoice,
                purchase_order,
            )
            financial_evidence={
                **variance,
                "currency":invoice.get("CURRENCY"),
                "price_authority_evidence":price_authority,
                "duplicate_invoice_count":len(duplicate_invoices),
            }

            if purchase_order.get("PO_DATE") and price_authority:
                latest_amendment_date=price_authority[-1]["amendment_date"]
                financial_evidence["po_created_before_latest_price_amendment"]=bool(
                    latest_amendment_date and
                    str(purchase_order.get("PO_DATE"))[:10]<
                    str(latest_amendment_date)[:10]
                )

        elif purchase_order:
            latest_amendment_date=(
                price_authority[-1]["amendment_date"]
                if price_authority
                else None
            )
            financial_evidence={
                "po_amount":_safe_float(purchase_order.get("TOTAL_AMOUNT")),
                "currency":purchase_order.get("CURRENCY"),
                "price_authority_evidence":price_authority,
                "po_created_before_latest_price_amendment":bool(
                    latest_amendment_date and
                    purchase_order.get("PO_DATE") and
                    str(purchase_order.get("PO_DATE"))[:10]<
                    str(latest_amendment_date)[:10]
                ),
            }
            if invoice:
                financial_evidence.update(
                    _calculate_invoice_variance(
                        invoice,
                        purchase_order,
                    )
                )

        elif invoice:
            financial_evidence={
                "invoice_id":invoice.get("INVOICE_ID"),
                "invoice_amount":_safe_float(invoice.get("TOTAL_AMOUNT")),
                "currency":invoice.get("CURRENCY"),
                "price_authority_evidence":price_authority,
                "duplicate_invoice_count":len(duplicate_invoices),
            }

        if shipment:
            promised=shipment.get("PROMISED_DATE")
            actual=shipment.get("ACTUAL_DATE")
            delay_days=(actual-promised).days if promised and actual else None
            financial_evidence["shipment_evidence"]=[{
                "shipment_id":shipment.get("SHIPMENT_ID"),
                "order_id":shipment.get("ORDER_ID"),
                "promised_date":promised,
                "actual_date":actual,
                "delay_days":delay_days,
                "status":shipment.get("STATUS"),
            }]

        if order and entity_type=="ORDER":
            financial_evidence["order_evidence"]=[{
                "order_id":order.get("ORDER_ID"),
                "customer_id":order.get("CUSTOMER_ID"),
                "order_amount":_safe_float(order.get("ORDER_AMOUNT")),
                "status":order.get("STATUS"),
            }]

        timeline=[]

        for amendment in amendments:
            _add_timeline(
                timeline,
                amendment.get("AMENDMENT_DATE"),
                "CONTRACT_AMENDMENT",
                amendment.get("AMENDMENT_ID"),
                f"{amendment.get('FIELD_CHANGED')} changed from {amendment.get('OLD_VALUE')} to {amendment.get('NEW_VALUE')}: {amendment.get('REASON')}",
            )

        for communication in relevant_communications:
            _add_timeline(
                timeline,
                communication.get("COMMUNICATION_DATE"),
                "SUPPLIER_COMMUNICATION",
                communication.get("COMMUNICATION_ID"),
                f"{communication.get('SUBJECT')}: {communication.get('CONTENT')}",
            )

        for event in relevant_erp_evidence:
            _add_timeline(
                timeline,
                event.get("EVENT_TIMESTAMP"),
                "ERP_EVENT",
                event.get("EVENT_ID"),
                f"{event.get('EVENT_TYPE')}: {event.get('DESCRIPTION')}",
            )

        if invoice:
            _add_timeline(
                timeline,
                invoice.get("INVOICE_DATE"),
                "INVOICE",
                invoice.get("INVOICE_ID"),
                f"Invoice received for {invoice.get('TOTAL_AMOUNT')} {invoice.get('CURRENCY')}",
            )

        _add_timeline(
            timeline,
            exception.get("DETECTED_AT"),
            "EXCEPTION_DETECTED",
            exception_id,
            exception.get("DESCRIPTION"),
        )

        timeline.sort(
            key=lambda x:(str(x["date"]),x["event_type"],str(x["source_id"]))
        )

        evidence_pack={
            "exception":exception,
            "entity_context":{
                "invoice":invoice,
                "purchase_order":purchase_order,
                "contract":contract,
                "shipment":shipment,
                "order":order,
                "duplicate_invoices":duplicate_invoices,
            },
            "financial_evidence":financial_evidence,
            "contract_amendments":amendments,
            "timeline_evidence":timeline,
            "communication_evidence":communication_evidence,
            "relevant_communications":relevant_communications,
            "relevant_erp_evidence":relevant_erp_evidence,
            "policy_evidence":_rows(
                cur,
                "SELECT * FROM POLICIES ORDER BY POLICY_ID",
            ),
            "impact_evidence":{
                "orders":linked_orders,
                "shipments":linked_shipments,
                "summary":{
                    "order_count":len(linked_orders),
                    "order_amount_total":sum(
                        _safe_float(x.get("ORDER_AMOUNT")) or 0
                        for x in linked_orders
                    ),
                    "shipment_count":len(linked_shipments),
                },
            },
        }
        return evidence_pack
    finally:
        if own_connection:
            conn.close()