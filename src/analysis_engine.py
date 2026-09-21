from typing import Any
from datetime import date,datetime

def _rows(connection,query,params=()):
    cursor=connection.cursor()
    try:
        cursor.execute(query,params)
        columns=[d[0].lower() for d in cursor.description]
        return [dict(zip(columns,row)) for row in cursor.fetchall()]
    finally:
        cursor.close()

def _query(connection,query,params=()):
    return _rows(connection,query,params)

def _safe_float(value):
    try:
        return float(value)
    except (TypeError,ValueError):
        return None

def _compare_dates(left,right):
    if left is None or right is None:
        return None
    if isinstance(left,datetime):
        left=left.date()
    elif not isinstance(left,date):
        try:
            left=datetime.fromisoformat(str(left)).date()
        except (TypeError,ValueError):
            return None
    if isinstance(right,datetime):
        right=right.date()
    elif not isinstance(right,date):
        try:
            right=datetime.fromisoformat(str(right)).date()
        except (TypeError,ValueError):
            return None
    return left<right

def _get_exception(connection,exception_id):
    rows=_query(connection,"""
        SELECT *
        FROM EXCEPTION_RESOLVER.ENTERPRISE.EXCEPTIONS
        WHERE EXCEPTION_ID=%s
    """,(exception_id,))
    return rows[0] if rows else None

def _resolve_entity(connection,entity_type,entity_id):
    entity_type=(entity_type or "").upper()
    if entity_type in {"PURCHASE_ORDER","PO"}:
        rows=_query(connection,"""
            SELECT *
            FROM EXCEPTION_RESOLVER.ENTERPRISE.PURCHASE_ORDERS
            WHERE PO_ID=%s
        """,(entity_id,))
        return rows[0] if rows else None
    if entity_type=="ORDER":
        rows=_query(connection,"""
            SELECT *
            FROM EXCEPTION_RESOLVER.ENTERPRISE.ORDERS
            WHERE ORDER_ID=%s
        """,(entity_id,))
        return rows[0] if rows else None
    if entity_type=="INVOICE":
        rows=_query(connection,"""
            SELECT *
            FROM EXCEPTION_RESOLVER.ENTERPRISE.INVOICES
            WHERE INVOICE_ID=%s
        """,(entity_id,))
        return rows[0] if rows else None
    if entity_type=="SHIPMENT":
        rows=_query(connection,"""
            SELECT *
            FROM EXCEPTION_RESOLVER.ENTERPRISE.SHIPMENTS
            WHERE SHIPMENT_ID=%s
        """,(entity_id,))
        return rows[0] if rows else None
    return None

def _related_exception_ids(connection,entity_ids):
    entity_ids=[str(x) for x in entity_ids if x]
    if not entity_ids:
        return []
    placeholders=",".join(["%s"]*len(entity_ids))
    return _query(connection,f"""
        SELECT EXCEPTION_ID,EXCEPTION_TYPE,ENTITY_TYPE,ENTITY_ID,STATUS
        FROM EXCEPTION_RESOLVER.ENTERPRISE.EXCEPTIONS
        WHERE ENTITY_ID IN ({placeholders})
    """,tuple(entity_ids))

def discover_impact_propagation(connection,exception_id):
    exception=_get_exception(connection,exception_id)
    if not exception:
        raise ValueError(f"Exception not found: {exception_id}")
    entity_type=exception.get("entity_type")
    entity_id=exception.get("entity_id")
    entity=_resolve_entity(connection,entity_type,entity_id)
    contracts=[]
    amendments=[]
    purchase_orders=[]
    orders=[]
    invoices=[]
    shipments=[]
    related_ids=[]
    if entity_type in {"PURCHASE_ORDER","PO"} and entity:
        purchase_orders=[entity]
        contract_id=entity.get("contract_id")
        if contract_id:
            contracts=_query(connection,"""
                SELECT *
                FROM EXCEPTION_RESOLVER.ENTERPRISE.CONTRACTS
                WHERE CONTRACT_ID=%s
            """,(contract_id,))
            amendments=_query(connection,"""
                SELECT *
                FROM EXCEPTION_RESOLVER.ENTERPRISE.CONTRACT_AMENDMENTS
                WHERE CONTRACT_ID=%s
                ORDER BY AMENDMENT_DATE
            """,(contract_id,))
        po_id=entity.get("po_id")
        if po_id:
            orders=_query(connection,"""
                SELECT *
                FROM EXCEPTION_RESOLVER.ENTERPRISE.ORDERS
                WHERE PO_ID=%s
            """,(po_id,))
            invoices=_query(connection,"""
                SELECT *
                FROM EXCEPTION_RESOLVER.ENTERPRISE.INVOICES
                WHERE PO_ID=%s
            """,(po_id,))
            order_ids=[row.get("order_id") for row in orders]
            if order_ids:
                placeholders=",".join(["%s"]*len(order_ids))
                shipments=_query(connection,f"""
                    SELECT *
                    FROM EXCEPTION_RESOLVER.ENTERPRISE.SHIPMENTS
                    WHERE ORDER_ID IN ({placeholders})
                """,tuple(order_ids))
        related_ids=[entity_id,po_id,contract_id]
        related_ids.extend(row.get("order_id") for row in orders)
        related_ids.extend(row.get("invoice_id") for row in invoices)
        related_ids.extend(row.get("shipment_id") for row in shipments)
    elif entity_type=="ORDER" and entity:
        orders=[entity]
        po_id=entity.get("po_id")
        if po_id:
            po_rows=_query(connection,"""
                SELECT *
                FROM EXCEPTION_RESOLVER.ENTERPRISE.PURCHASE_ORDERS
                WHERE PO_ID=%s
            """,(po_id,))
            purchase_orders.extend(po_rows)
            if po_rows:
                contract_id=po_rows[0].get("contract_id")
                if contract_id:
                    contracts=_query(connection,"""
                        SELECT *
                        FROM EXCEPTION_RESOLVER.ENTERPRISE.CONTRACTS
                        WHERE CONTRACT_ID=%s
                    """,(contract_id,))
                    amendments=_query(connection,"""
                        SELECT *
                        FROM EXCEPTION_RESOLVER.ENTERPRISE.CONTRACT_AMENDMENTS
                        WHERE CONTRACT_ID=%s
                        ORDER BY AMENDMENT_DATE
                    """,(contract_id,))
            invoices=_query(connection,"""
                SELECT *
                FROM EXCEPTION_RESOLVER.ENTERPRISE.INVOICES
                WHERE PO_ID=%s
            """,(po_id,))
        shipments=_query(connection,"""
            SELECT *
            FROM EXCEPTION_RESOLVER.ENTERPRISE.SHIPMENTS
            WHERE ORDER_ID=%s
        """,(entity_id,))
        related_ids=[entity_id,po_id]
        related_ids.extend(row.get("invoice_id") for row in invoices)
        related_ids.extend(row.get("shipment_id") for row in shipments)
    elif entity_type=="INVOICE" and entity:
        invoices=[entity]
        po_id=entity.get("po_id")
        if po_id:
            purchase_orders=_query(connection,"""
                SELECT *
                FROM EXCEPTION_RESOLVER.ENTERPRISE.PURCHASE_ORDERS
                WHERE PO_ID=%s
            """,(po_id,))
            orders=_query(connection,"""
                SELECT *
                FROM EXCEPTION_RESOLVER.ENTERPRISE.ORDERS
                WHERE PO_ID=%s
            """,(po_id,))
            if purchase_orders:
                contract_id=purchase_orders[0].get("contract_id")
                if contract_id:
                    contracts=_query(connection,"""
                        SELECT *
                        FROM EXCEPTION_RESOLVER.ENTERPRISE.CONTRACTS
                        WHERE CONTRACT_ID=%s
                    """,(contract_id,))
                    amendments=_query(connection,"""
                        SELECT *
                        FROM EXCEPTION_RESOLVER.ENTERPRISE.CONTRACT_AMENDMENTS
                        WHERE CONTRACT_ID=%s
                        ORDER BY AMENDMENT_DATE
                    """,(contract_id,))
            order_ids=[row.get("order_id") for row in orders]
            if order_ids:
                placeholders=",".join(["%s"]*len(order_ids))
                shipments=_query(connection,f"""
                    SELECT *
                    FROM EXCEPTION_RESOLVER.ENTERPRISE.SHIPMENTS
                    WHERE ORDER_ID IN ({placeholders})
                """,tuple(order_ids))
        related_ids=[entity_id,po_id]
        related_ids.extend(row.get("order_id") for row in orders)
        related_ids.extend(row.get("shipment_id") for row in shipments)
    elif entity_type=="SHIPMENT" and entity:
        shipments=[entity]
        order_id=entity.get("order_id")
        if order_id:
            orders=_query(connection,"""
                SELECT *
                FROM EXCEPTION_RESOLVER.ENTERPRISE.ORDERS
                WHERE ORDER_ID=%s
            """,(order_id,))
            if orders:
                po_id=orders[0].get("po_id")
                if po_id:
                    purchase_orders=_query(connection,"""
                        SELECT *
                        FROM EXCEPTION_RESOLVER.ENTERPRISE.PURCHASE_ORDERS
                        WHERE PO_ID=%s
                    """,(po_id,))
                    invoices=_query(connection,"""
                        SELECT *
                        FROM EXCEPTION_RESOLVER.ENTERPRISE.INVOICES
                        WHERE PO_ID=%s
                    """,(po_id,))
                    if purchase_orders:
                        contract_id=purchase_orders[0].get("contract_id")
                        if contract_id:
                            contracts=_query(connection,"""
                                SELECT *
                                FROM EXCEPTION_RESOLVER.ENTERPRISE.CONTRACTS
                                WHERE CONTRACT_ID=%s
                            """,(contract_id,))
                            amendments=_query(connection,"""
                                SELECT *
                                FROM EXCEPTION_RESOLVER.ENTERPRISE.CONTRACT_AMENDMENTS
                                WHERE CONTRACT_ID=%s
                                ORDER BY AMENDMENT_DATE
                            """,(contract_id,))
        related_ids=[entity_id,order_id]
        related_ids.extend(row.get("po_id") for row in orders)
        related_ids.extend(row.get("invoice_id") for row in invoices)
    related_exceptions=_related_exception_ids(connection,related_ids)
    related_exceptions=[r for r in related_exceptions if r["exception_id"]!=exception_id]
    return {
        "exception_id":exception_id,
        "contracts":contracts,
        "amendments":amendments,
        "purchase_orders":purchase_orders,
        "orders":orders,
        "invoices":invoices,
        "shipments":shipments,
        "related_exceptions":related_exceptions,
    }

def _find_authoritative_amendment(analysis,entity):
    amendments=analysis.get("amendments",[])
    current_amount=_safe_float(entity.get("total_amount")) if entity else None
    candidates=[]
    for amendment in amendments:
        field=(amendment.get("field_changed") or "").upper()
        old_value=_safe_float(amendment.get("old_value"))
        new_value=_safe_float(amendment.get("new_value"))
        if field=="UNIT_PRICE" and new_value is not None:
            candidates.append({
                "amendment":amendment,
                "old_value":old_value,
                "new_value":new_value,
                "matches_current":current_amount is not None and old_value is not None and abs(current_amount-old_value)<0.01,
            })
    matching=[c for c in candidates if c["matches_current"]]
    if matching:
        return matching[-1]
    return candidates[-1] if candidates else None

def detect_state_divergence(connection,exception_id):
    exception=_get_exception(connection,exception_id)
    if not exception:
        raise ValueError(f"Exception not found: {exception_id}")
    entity_type=exception.get("entity_type")
    entity_id=exception.get("entity_id")
    entity=_resolve_entity(connection,entity_type,entity_id)
    if not entity:
        return {
            "exception_id":exception_id,
            "status":"NO_ENTITY",
            "divergence_detected":False,
            "reason":"Exception entity could not be resolved.",
        }
    analysis=discover_impact_propagation(connection,exception_id)
    if entity_type not in {"PURCHASE_ORDER","PO"}:
        return {
            "exception_id":exception_id,
            "status":"NOT_APPLICABLE",
            "divergence_detected":False,
            "reason":"State divergence analysis currently targets purchase-order state against contract amendments.",
        }
    authoritative=_find_authoritative_amendment(analysis,entity)
    if not authoritative:
        return {
            "exception_id":exception_id,
            "status":"NO_AUTHORITY",
            "divergence_detected":False,
            "reason":"No applicable contract amendment establishes an authoritative replacement value.",
        }
    amendment=authoritative["amendment"]
    expected_amount=authoritative["new_value"]
    actual_amount=_safe_float(entity.get("total_amount"))
    amendment_date=amendment.get("amendment_date")
    po_date=entity.get("po_date")
    contract_id=entity.get("contract_id")
    po_id=entity.get("po_id")
    po_created_before_amendment=_compare_dates(po_date,amendment_date)
    events=_query(connection,"""
        SELECT *
        FROM EXCEPTION_RESOLVER.ENTERPRISE.ERP_EVENTS
        WHERE ENTITY_TYPE IN ('PURCHASE_ORDER','PO')
          AND ENTITY_ID=%s
        ORDER BY EVENT_TIMESTAMP
    """,(po_id,))
    relevant_events=[]
    for event in events:
        event_time=event.get("event_timestamp")
        if amendment_date is None or event_time is None:
            relevant_events.append(event)
            continue
        event_date=event_time.date() if hasattr(event_time,"date") else event_time
        authority_date=amendment_date.date() if hasattr(amendment_date,"date") else amendment_date
        if event_date>=authority_date:
            relevant_events.append(event)
    failure_events=[
        event for event in relevant_events
        if any(token in (
            (event.get("event_type") or "").upper()+" "+
            (event.get("description") or "").upper()
        ) for token in ("FAIL","ERROR","UPDATE_FAILED","SYNC_FAILED"))
    ]
    aligned=(
        actual_amount is not None and
        expected_amount is not None and
        abs(actual_amount-expected_amount)<0.01
    )
    divergence_detected=not aligned
    divergence_event=failure_events[0] if divergence_detected and failure_events else None
    downstream={
        "contracts":len(analysis.get("contracts",[])),
        "amendments":len(analysis.get("amendments",[])),
        "purchase_orders":len(analysis.get("purchase_orders",[])),
        "orders":len(analysis.get("orders",[])),
        "invoices":len(analysis.get("invoices",[])),
        "shipments":len(analysis.get("shipments",[])),
        "related_exceptions":len(analysis.get("related_exceptions",[])),
    }
    return {
        "exception_id":exception_id,
        "status":"DIVERGED" if divergence_detected else "ALIGNED",
        "divergence_detected":divergence_detected,
        "authoritative_state":{
            "contract_id":contract_id,
            "amendment_id":amendment.get("amendment_id"),
            "field":amendment.get("field_changed"),
            "previous_value":authoritative["old_value"],
            "authorized_value":expected_amount,
            "effective_date":amendment_date,
            "reason":amendment.get("reason"),
        },
        "operational_state":{
            "po_id":po_id,
            "actual_value":actual_amount,
            "currency":entity.get("currency"),
            "po_date":po_date,
        },
        "temporal_validation":{
            "po_created_before_amendment":po_created_before_amendment,
            "po_date":po_date,
            "amendment_date":amendment_date,
        },
        "divergence":{
            "expected_value":expected_amount,
            "actual_value":actual_amount,
            "difference":round(expected_amount-actual_amount,2) if expected_amount is not None and actual_amount is not None else None,
            "divergence_event":divergence_event,
            "erp_events_after_authority_change":relevant_events,
        },
        "downstream_exposure":downstream,
        "interpretation":"The authoritative contract amendment and operational PO state are compared deterministically. No Snowflake data was mutated.",
    }

def simulate_counterfactual(connection,exception_id):
    analysis=discover_impact_propagation(connection,exception_id)
    exception=_get_exception(connection,exception_id)
    if not exception:
        raise ValueError(f"Exception not found: {exception_id}")
    entity=_resolve_entity(connection,exception.get("entity_type"),exception.get("entity_id"))
    if not entity:
        return {"exception_id":exception_id,"error":"Entity not found"}
    current_amount=_safe_float(entity.get("total_amount"))
    authoritative=_find_authoritative_amendment(analysis,entity)
    approved_amount=authoritative["new_value"] if authoritative else None
    amendment_id=authoritative["amendment"].get("amendment_id") if authoritative else None
    proposed_action=None
    alignment_restored=None
    if approved_amount is not None:
        currently_aligned=current_amount is not None and abs(current_amount-approved_amount)<0.01
        if not currently_aligned:
            proposed_action={
                "action_type":"UPDATE_PO_TO_APPROVED_PRICE",
                "po_id":entity.get("po_id"),
                "current_amount":current_amount,
                "projected_amount":approved_amount,
                "amendment_id":amendment_id,
            }
            projected_amount=approved_amount
            alignment_restored=current_amount is not None and abs(projected_amount-approved_amount)<0.01
        else:
            projected_amount=current_amount
            alignment_restored=True
    else:
        projected_amount=current_amount
    return {
        "exception_id":exception_id,
        "exception_type":exception.get("exception_type"),
        "current_state":{
            "entity_id":entity.get("po_id") or entity.get("order_id") or entity.get("invoice_id") or entity.get("shipment_id"),
            "current_amount":current_amount,
            "approved_amount":approved_amount,
        },
        "no_action":{
            "state_change":False,
            "remaining_related_records":{
                "contracts":len(analysis.get("contracts",[])),
                "amendments":len(analysis.get("amendments",[])),
                "purchase_orders":len(analysis.get("purchase_orders",[])),
                "orders":len(analysis.get("orders",[])),
                "invoices":len(analysis.get("invoices",[])),
                "shipments":len(analysis.get("shipments",[])),
                "related_exceptions":len(analysis.get("related_exceptions",[])),
            },
            "alignment_restored":(
                abs(current_amount-approved_amount)<0.01
                if current_amount is not None and approved_amount is not None
                else None
            ),
        },
        "proposed_action":{
            "action":proposed_action,
            "alignment_restored":alignment_restored,
            "projected_amount":projected_amount,
        },
        "interpretation":"Deterministic scenario analysis. No Snowflake data was mutated.",
    }

def cluster_root_causes(connection):
    exceptions=_query(connection,"""
        SELECT EXCEPTION_ID,EXCEPTION_TYPE,ENTITY_TYPE,ENTITY_ID
        FROM EXCEPTION_RESOLVER.ENTERPRISE.EXCEPTIONS
        ORDER BY EXCEPTION_ID
    """)
    groups={}
    for exception in exceptions:
        key=(exception.get("entity_type"),exception.get("entity_id"))
        groups.setdefault(key,[]).append(exception)
    clusters=[]
    for key,members in groups.items():
        if len(members)>1:
            clusters.append({
                "entity_type":key[0],
                "entity_id":key[1],
                "exception_count":len(members),
                "exceptions":members,
            })
    return clusters

def scan_state_divergences(connection):
    amendments=_query(connection,"""
        SELECT *
        FROM EXCEPTION_RESOLVER.ENTERPRISE.CONTRACT_AMENDMENTS
        WHERE FIELD_CHANGED='UNIT_PRICE'
        ORDER BY AMENDMENT_DATE
    """)
    results=[]
    for amendment in amendments:
        contract_id=amendment.get("contract_id")
        amendment_date=amendment.get("amendment_date")
        old_value=_safe_float(amendment.get("old_value"))
        new_value=_safe_float(amendment.get("new_value"))
        if not contract_id or old_value is None or new_value is None:
            continue
        purchase_orders=_query(connection,"""
            SELECT *
            FROM EXCEPTION_RESOLVER.ENTERPRISE.PURCHASE_ORDERS
            WHERE CONTRACT_ID=%s
              AND PO_DATE<%s
              AND ABS(TOTAL_AMOUNT-%s)<0.01
              AND STATUS='OPEN'
            ORDER BY PO_DATE
        """,(contract_id,amendment_date,old_value))
        for po in purchase_orders:
            po_id=po.get("po_id")
            events=_query(connection,"""
                SELECT *
                FROM EXCEPTION_RESOLVER.ENTERPRISE.ERP_EVENTS
                WHERE ENTITY_TYPE='PURCHASE_ORDER'
                  AND ENTITY_ID=%s
                  AND EVENT_TIMESTAMP>=%s
                ORDER BY EVENT_TIMESTAMP
            """,(po_id,amendment_date))
            failure_events=[
                event for event in events
                if any(token in (
                    (event.get("event_type") or "").upper()+" "+
                    (event.get("description") or "").upper()
                ) for token in ("FAIL","ERROR","UPDATE_FAILED","SYNC_FAILED"))
            ]
            successful_update_events=[
                event for event in events
                if any(token in (
                    (event.get("event_type") or "").upper()+" "+
                    (event.get("description") or "").upper()
                ) for token in ("UPDATED","UPDATE_SUCCESS","SYNC_SUCCESS"))
            ]
            if successful_update_events:
                propagation_status="ALIGNED_AFTER_UPDATE"
            elif failure_events:
                propagation_status="EXPLICIT_PROPAGATION_FAILURE"
            else:
                propagation_status="NO_PROPAGATION_EVIDENCE"
            orders=_query(connection,"""
                SELECT ORDER_ID
                FROM EXCEPTION_RESOLVER.ENTERPRISE.ORDERS
                WHERE PO_ID=%s
            """,(po_id,))
            invoices=_query(connection,"""
                SELECT INVOICE_ID
                FROM EXCEPTION_RESOLVER.ENTERPRISE.INVOICES
                WHERE PO_ID=%s
            """,(po_id,))
            results.append({
                "amendment_id":amendment.get("amendment_id"),
                "contract_id":contract_id,
                "amendment_date":amendment_date,
                "old_value":old_value,
                "new_value":new_value,
                "po_id":po_id,
                "po_date":po.get("po_date"),
                "po_status":po.get("status"),
                "current_value":_safe_float(po.get("total_amount")),
                "propagation_status":propagation_status,
                "erp_events":events,
                "downstream_exposure":{
                    "orders":len(orders),
                    "invoices":len(invoices),
                },
            })
    return results