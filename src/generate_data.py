from pathlib import Path
from datetime import datetime,date,timedelta
import csv,random
from faker import Faker

SEED=42
random.seed(SEED)
fake=Faker()
fake.seed_instance(SEED)

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"data"/"generated"
OUT.mkdir(parents=True,exist_ok=True)

N_SUPPLIERS=120
N_CONTRACTS=150
N_POS=5000
N_COMMUNICATIONS=2200

def money(a,b):
    return round(random.uniform(a,b),2)

def dt(d):
    return datetime.combine(d,datetime.min.time()).strftime("%Y-%m-%d %H:%M:%S")

def write_csv(name,rows,fields):
    with open(OUT/name,"w",newline="",encoding="utf-8") as f:
        w=csv.DictWriter(f,fieldnames=fields)
        w.writeheader()
        w.writerows(rows)

suppliers=[]
for i in range(1,N_SUPPLIERS+1):
    suppliers.append({
        "SUPPLIER_ID":f"SUP-{i:04d}",
        "SUPPLIER_NAME":fake.company(),
        "CATEGORY":random.choice(["Electronics","Industrial","Packaging","Chemicals","Machinery","Logistics","Components","IT Hardware"]),
        "COUNTRY":random.choice(["India","USA","Germany","Japan","Singapore","UK","France"]),
        "RISK_LEVEL":random.choices(["LOW","MEDIUM","HIGH"],weights=[65,28,7])[0],
        "STATUS":random.choices(["ACTIVE","ON_HOLD"],weights=[95,5])[0]
    })

contracts=[]
contracts_by_supplier={}

# Guarantee at least one contract for every supplier.
for i,supplier in enumerate(suppliers,1):
    start=date(2025,1,1)+timedelta(days=random.randint(0,500))
    contract={
        "CONTRACT_ID":f"CON-{i:04d}",
        "SUPPLIER_ID":supplier["SUPPLIER_ID"],
        "CONTRACT_START":start.isoformat(),
        "CONTRACT_END":(start+timedelta(days=730)).isoformat(),
        "CURRENCY":random.choice(["USD","EUR","INR","GBP"]),
        "PAYMENT_TERMS":random.choice(["NET30","NET45","NET60","NET90"]),
        "STATUS":"ACTIVE"
    }
    contracts.append(contract)
    contracts_by_supplier.setdefault(supplier["SUPPLIER_ID"],[]).append(contract)

# Create the remaining contracts across suppliers.
for i in range(N_SUPPLIERS+1,N_CONTRACTS+1):
    supplier=random.choice(suppliers)
    start=date(2025,1,1)+timedelta(days=random.randint(0,500))
    contract={
        "CONTRACT_ID":f"CON-{i:04d}",
        "SUPPLIER_ID":supplier["SUPPLIER_ID"],
        "CONTRACT_START":start.isoformat(),
        "CONTRACT_END":(start+timedelta(days=730)).isoformat(),
        "CURRENCY":random.choice(["USD","EUR","INR","GBP"]),
        "PAYMENT_TERMS":random.choice(["NET30","NET45","NET60","NET90"]),
        "STATUS":"ACTIVE"
    }
    contracts.append(contract)
    contracts_by_supplier.setdefault(supplier["SUPPLIER_ID"],[]).append(contract)

amendments=[]
communications=[]
erp_events=[]
ground_truth=[]
exceptions=[]

pos=[]
invoices=[]
orders=[]
shipments=[]

customers=[f"CUST-{i:05d}" for i in range(1,2501)]
base_date=date(2026,1,1)

for i in range(1,N_POS+1):
    supplier=random.choice(suppliers)
    supplier_contracts=contracts_by_supplier[supplier["SUPPLIER_ID"]]
    contract=random.choice(supplier_contracts)
    po_date=base_date+timedelta(days=random.randint(0,240))
    amount=money(500,150000)
    po_id=f"PO-{i:06d}"
    pos.append({
        "PO_ID":po_id,
        "SUPPLIER_ID":supplier["SUPPLIER_ID"],
        "CONTRACT_ID":contract["CONTRACT_ID"],
        "PO_DATE":po_date.isoformat(),
        "CURRENCY":contract["CURRENCY"],
        "TOTAL_AMOUNT":amount,
        "STATUS":"OPEN"
    })
    invoice_date=po_date+timedelta(days=random.randint(3,35))
    invoices.append({
        "INVOICE_ID":f"INV-{i:06d}",
        "PO_ID":po_id,
        "SUPPLIER_ID":supplier["SUPPLIER_ID"],
        "INVOICE_DATE":invoice_date.isoformat(),
        "CURRENCY":contract["CURRENCY"],
        "TOTAL_AMOUNT":amount,
        "STATUS":"RECEIVED"
    })
    for j in range(random.randint(1,4)):
        order_id=f"ORD-{i:06d}-{j+1}"
        order_date=po_date+timedelta(days=random.randint(0,10))
        order_amount=round(amount/random.randint(1,4),2)
        orders.append({
            "ORDER_ID":order_id,
            "PO_ID":po_id,
            "CUSTOMER_ID":random.choice(customers),
            "ORDER_DATE":order_date.isoformat(),
            "ORDER_AMOUNT":order_amount,
            "STATUS":"OPEN"
        })
        promised=order_date+timedelta(days=random.randint(7,30))
        actual=promised+timedelta(days=random.choice([0,0,0,1,2]))
        shipments.append({
            "SHIPMENT_ID":f"SHP-{i:06d}-{j+1}",
            "ORDER_ID":order_id,
            "SUPPLIER_ID":supplier["SUPPLIER_ID"],
            "PROMISED_DATE":promised.isoformat(),
            "ACTUAL_DATE":actual.isoformat(),
            "STATUS":"DELIVERED" if actual<=date(2026,9,1) else "IN_TRANSIT"
        })
    erp_events.append({
        "EVENT_ID":f"EVT-{i:07d}",
        "EVENT_TIMESTAMP":dt(datetime.combine(po_date,datetime.min.time())),
        "ENTITY_TYPE":"PURCHASE_ORDER",
        "ENTITY_ID":po_id,
        "EVENT_TYPE":"PO_CREATED",
        "DESCRIPTION":f"Purchase order {po_id} created in ERP"
    })

def add_amendment(amendment_id,contract,date_,old,new,reason,field="UNIT_PRICE"):
    amendments.append({
        "AMENDMENT_ID":amendment_id,
        "CONTRACT_ID":contract,
        "AMENDMENT_DATE":dt(date_),
        "FIELD_CHANGED":field,
        "OLD_VALUE":str(old),
        "NEW_VALUE":str(new),
        "REASON":reason
    })

def add_comm(comm_id,supplier,date_,subject,content,channel="EMAIL"):
    communications.append({
        "COMMUNICATION_ID":comm_id,
        "SUPPLIER_ID":supplier,
        "COMMUNICATION_DATE":dt(date_),
        "CHANNEL":channel,
        "SUBJECT":subject,
        "CONTENT":content
    })

def add_event(event_id,date_,entity_type,entity_id,event_type,description):
    erp_events.append({
        "EVENT_ID":event_id,
        "EVENT_TIMESTAMP":dt(date_),
        "ENTITY_TYPE":entity_type,
        "ENTITY_ID":entity_id,
        "EVENT_TYPE":event_type,
        "DESCRIPTION":description
    })

def add_exception(eid,etype,entity_type,entity_id,severity,description,truth,reason):
    exceptions.append({
        "EXCEPTION_ID":eid,
        "DETECTED_AT":dt(datetime(2026,9,10)+timedelta(days=random.randint(0,7))),
        "EXCEPTION_TYPE":etype,
        "ENTITY_TYPE":entity_type,
        "ENTITY_ID":entity_id,
        "SEVERITY":severity,
        "STATUS":"OPEN",
        "DESCRIPTION":description
    })
    ground_truth.append({
        "EXCEPTION_ID":eid,
        "TRUE_OUTCOME":truth,
        "TRUE_REASON":reason
    })

story_pos={}

# STORY 1: legitimate invoice mismatch.
po=pos[10]
inv=invoices[10]
contract=next(c for c in contracts if c["CONTRACT_ID"]==po["CONTRACT_ID"])
old=inv["TOTAL_AMOUNT"]
new=round(old*1.08,2)
inv["TOTAL_AMOUNT"]=new
am_date=date.fromisoformat(po["PO_DATE"])+timedelta(days=5)
add_amendment("AMD-0001",contract["CONTRACT_ID"],am_date,old,new,"Supplier price revision approved")
add_comm("COM-0001",po["SUPPLIER_ID"],am_date-timedelta(days=1),"Approved pricing update",f"Following our commercial review, the revised price for {po['PO_ID']} is {new} {po['CURRENCY']}. The change is effective for open orders.")
add_comm("COM-0001B",po["SUPPLIER_ID"],am_date+timedelta(days=2),"ERP synchronization follow-up",f"Please note that the amended pricing for contract {contract['CONTRACT_ID']} may not yet be visible in the ERP purchase order.")
add_event("EVT-STORY-001",am_date,"CONTRACT",contract["CONTRACT_ID"],"AMENDMENT_APPROVED","Contract amendment approved; ERP PO was not updated.")
add_exception("EXC-0001","INVOICE_PO_MISMATCH","INVOICE",inv["INVOICE_ID"],"MEDIUM","Invoice exceeds PO amount by 8%.","AUTO_RESOLVE","Contract amendment and supplier communication establish that the invoice reflects the approved revised price while the PO is stale.")

# STORY 2: suspicious mismatch with contradictory evidence.
po=pos[20]
inv=invoices[20]
inv["TOTAL_AMOUNT"]=round(inv["TOTAL_AMOUNT"]*1.17,2)
add_comm("COM-0002",po["SUPPLIER_ID"],date.fromisoformat(po["PO_DATE"])+timedelta(days=7),"Pricing question",f"We have not approved any price change for {po['PO_ID']}. Please continue billing against the existing purchase order.")
add_comm("COM-0002B",po["SUPPLIER_ID"],date.fromisoformat(po["PO_DATE"])+timedelta(days=8),"Invoice dispute",f"The invoice submitted for {po['PO_ID']} appears higher than our agreed amount. We cannot confirm the revised price referenced in the invoice.")
add_exception("EXC-0002","INVOICE_PO_MISMATCH","INVOICE",inv["INVOICE_ID"],"HIGH","Invoice amount materially exceeds PO amount with no approved amendment.","ESCALATE","No approved amendment exists and supplier communication contradicts the invoice amount.")

# STORY 3: ERP stale after contract amendment.
po=pos[30]
inv=invoices[30]
old=inv["TOTAL_AMOUNT"]
new=round(old*1.05,2)
inv["TOTAL_AMOUNT"]=new
am_date=date.fromisoformat(po["PO_DATE"])+timedelta(days=3)
add_amendment("AMD-0003",po["CONTRACT_ID"],am_date,old,new,"Annual negotiated price adjustment")
add_comm("COM-0003",po["SUPPLIER_ID"],am_date,"Annual pricing adjustment",f"The annual negotiated adjustment under contract {po['CONTRACT_ID']} has been approved. New price basis is {new} {po['CURRENCY']}.")
add_event("EVT-STORY-003",am_date,"CONTRACT",po["CONTRACT_ID"],"AMENDMENT_APPROVED","Approved annual pricing adjustment.")
add_event("EVT-STORY-004",am_date+timedelta(days=1),"PURCHASE_ORDER",po["PO_ID"],"UPDATE_FAILED","ERP synchronization failed; PO retained previous amount.")
add_exception("EXC-0003","CONTRACT_PRICE_DRIFT","PURCHASE_ORDER",po["PO_ID"],"MEDIUM","PO price differs from current contract price.","AUTO_RESOLVE","Current contract amendment supersedes the stale ERP PO price.")

# STORY 4: duplicate invoice.
po=pos[40]
inv=invoices[40]
duplicate={
    "INVOICE_ID":"INV-DUP-0004",
    "PO_ID":inv["PO_ID"],
    "SUPPLIER_ID":inv["SUPPLIER_ID"],
    "INVOICE_DATE":inv["INVOICE_DATE"],
    "CURRENCY":inv["CURRENCY"],
    "TOTAL_AMOUNT":inv["TOTAL_AMOUNT"],
    "STATUS":"RECEIVED"
}
invoices.append(duplicate)
add_comm("COM-0004",po["SUPPLIER_ID"],date(2026,8,20),"Invoice submission",f"Please process invoice {duplicate['INVOICE_ID']} against purchase order {po['PO_ID']}.")
add_event("EVT-STORY-005",date(2026,8,20),"INVOICE",duplicate["INVOICE_ID"],"RECEIVED","Invoice received with same PO and amount as an existing invoice.")
add_exception("EXC-0004","DUPLICATE_INVOICE","INVOICE",duplicate["INVOICE_ID"],"HIGH","Invoice duplicates an existing invoice by supplier, PO and amount.","ESCALATE","Duplicate payment risk requires review before payment.")

# STORY 5: shipment delay with documented explanation.
order=orders[100]
ship=next(s for s in shipments if s["ORDER_ID"]==order["ORDER_ID"])
ship["ACTUAL_DATE"]=(date.fromisoformat(ship["PROMISED_DATE"])+timedelta(days=5)).isoformat()
add_comm("COM-0005",ship["SUPPLIER_ID"],date(2026,8,10),"Revised delivery commitment",f"Shipment {ship['SHIPMENT_ID']} will arrive five days later due to a documented carrier delay. No change to the customer allocation is expected.")
add_comm("COM-0005B",ship["SUPPLIER_ID"],date(2026,8,11),"Carrier confirmation",f"Carrier reference confirms the revised delivery estimate for shipment {ship['SHIPMENT_ID']}.")
add_exception("EXC-0005","SHIPMENT_DELAY","SHIPMENT",ship["SHIPMENT_ID"],"MEDIUM","Shipment is five days beyond committed delivery date.","AUTO_RESOLVE","Supplier provided a documented revised commitment and downstream exposure remains below the escalation threshold.")

# STORY 6: shipment delay with major downstream impact.
order=orders[200]
ship=next(s for s in shipments if s["ORDER_ID"]==order["ORDER_ID"])
ship["ACTUAL_DATE"]=(date.fromisoformat(ship["PROMISED_DATE"])+timedelta(days=18)).isoformat()
add_comm("COM-0006",ship["SUPPLIER_ID"],date(2026,8,12),"Delivery delay notice",f"Shipment {ship['SHIPMENT_ID']} is delayed due to production constraints. Current estimate is eighteen days beyond the committed date.")
add_exception("EXC-0006","SHIPMENT_DELAY","SHIPMENT",ship["SHIPMENT_ID"],"HIGH","Shipment is materially late and affects downstream customer commitments.","ESCALATE","Delay exceeds tolerance and downstream customer impact requires human intervention.")

# STORY 7: payment policy violation.
po=pos[70]
inv=invoices[70]
contract=next(c for c in contracts if c["CONTRACT_ID"]==po["CONTRACT_ID"])
contract["PAYMENT_TERMS"]="NET30"
add_comm("COM-0007",po["SUPPLIER_ID"],date(2026,8,15),"Payment terms",f"Our invoice requests accelerated payment for {inv['INVOICE_ID']}, but the active contract remains on NET30 terms.")
add_exception("EXC-0007","PAYMENT_POLICY_VIOLATION","INVOICE",inv["INVOICE_ID"],"HIGH","Payment terms conflict with the active contract policy.","ESCALATE","Invoice payment terms violate the governing contract and require approval.")

# STORY 8: conflicting order data.
order=orders[300]
add_comm("COM-0008",shipments[300]["SUPPLIER_ID"],date(2026,8,25),"Customer quantity change",f"Customer requested a quantity change for order {order['ORDER_ID']}. Please confirm the final authorized quantity before fulfillment.")
add_event("EVT-STORY-008A",datetime(2026,8,25),"ORDER",order["ORDER_ID"],"CUSTOMER_UPDATE","Customer requested quantity change.")
add_event("EVT-STORY-008B",datetime(2026,8,26),"ORDER",order["ORDER_ID"],"ERP_UPDATE","ERP retained previous quantity.")
add_exception("EXC-0008","ORDER_DATA_CONFLICT","ORDER",order["ORDER_ID"],"MEDIUM","Customer and ERP records contain conflicting order state.","REQUEST_EVIDENCE","The available records disagree and do not establish the authoritative final state.")

# BACKGROUND COMMUNICATIONS.
subjects=[
    "Purchase order confirmation","Invoice submission","Delivery update","Order status",
    "Payment reminder","Contract review","Shipping documentation","Quantity confirmation",
    "Forecast update","Account reconciliation","Monthly statement","Delivery schedule",
    "Pricing discussion","Quality documentation","General account update"
]

templates=[
    "Please confirm receipt of purchase order {po}.",
    "Invoice {inv} has been submitted for processing against {po}.",
    "Please provide an updated delivery estimate for the current order.",
    "Attached is the latest shipping documentation for your records.",
    "Please confirm the current outstanding balance for our account.",
    "We are reviewing the current contract terms and will follow up if clarification is required.",
    "Please confirm whether the requested quantity remains unchanged.",
    "The shipment remains on the previously communicated schedule.",
    "Please send the latest forecast for the upcoming delivery period.",
    "Our accounts team is reconciling recent transactions.",
    "Please confirm the expected delivery date and carrier reference.",
    "We are reviewing pricing for the next purchasing cycle.",
    "Please provide the required quality documentation for the shipment."
]

for i in range(1,N_COMMUNICATIONS-len(communications)+1):
    supplier=random.choice(suppliers)
    po=random.choice(pos)
    inv=next(x for x in invoices if x["PO_ID"]==po["PO_ID"])
    communication_date=datetime.combine(date.fromisoformat(po["PO_DATE"])+timedelta(days=random.randint(1,80)),datetime.min.time())
    subject=random.choice(subjects)
    content=random.choice(templates).format(po=po["PO_ID"],inv=inv["INVOICE_ID"])
    add_comm(f"COM-{i+100:04d}",supplier["SUPPLIER_ID"],communication_date,subject,content,random.choice(["EMAIL","EMAIL","PORTAL","PHONE_NOTE"]))

# BACKGROUND EXCEPTIONS.
exception_types=[
    "INVOICE_PO_MISMATCH",
    "CONTRACT_PRICE_DRIFT",
    "DUPLICATE_INVOICE",
    "PAYMENT_POLICY_VIOLATION",
    "SHIPMENT_DELAY",
    "ORDER_DATA_CONFLICT"
]

for idx in range(9,109):
    eid=f"EXC-{idx:04d}"
    etype=random.choice(exception_types)
    po=random.choice(pos)
    inv=next(i for i in invoices if i["PO_ID"]==po["PO_ID"])
    if etype=="INVOICE_PO_MISMATCH":
        delta=random.choice([-0.12,-0.08,0.07,0.11,0.19])
        inv["TOTAL_AMOUNT"]=round(inv["TOTAL_AMOUNT"]*(1+delta),2)
        truth=random.choice(["AUTO_RESOLVE","ESCALATE","REQUEST_EVIDENCE"])
        reason="Background mismatch requiring evidence review."
        entity_type,entity_id="INVOICE",inv["INVOICE_ID"]
        desc=f"Invoice amount differs from PO amount by {abs(delta)*100:.0f}%."
    elif etype=="CONTRACT_PRICE_DRIFT":
        truth=random.choice(["AUTO_RESOLVE","ESCALATE"])
        reason="PO price differs from active contract terms."
        entity_type,entity_id="PURCHASE_ORDER",po["PO_ID"]
        desc="Purchase order price differs from current contractual pricing."
    elif etype=="DUPLICATE_INVOICE":
        truth="ESCALATE"
        reason="Potential duplicate payment."
        entity_type,entity_id="INVOICE",inv["INVOICE_ID"]
        desc="Invoice shares supplier, PO and amount with another invoice."
    elif etype=="PAYMENT_POLICY_VIOLATION":
        truth="ESCALATE"
        reason="Payment conflicts with governing policy."
        entity_type,entity_id="INVOICE",inv["INVOICE_ID"]
        desc="Invoice payment conditions violate policy."
    elif etype=="SHIPMENT_DELAY":
        ship=random.choice(shipments)
        truth=random.choice(["AUTO_RESOLVE","ESCALATE"])
        reason="Shipment timing requires downstream impact analysis."
        entity_type,entity_id="SHIPMENT",ship["SHIPMENT_ID"]
        desc="Shipment missed committed delivery date."
    else:
        order=random.choice(orders)
        truth=random.choice(["REQUEST_EVIDENCE","ESCALATE"])
        reason="Conflicting order records require evidence reconciliation."
        entity_type,entity_id="ORDER",order["ORDER_ID"]
        desc="Order records contain conflicting state."
    add_exception(eid,etype,entity_type,entity_id,random.choice(["LOW","MEDIUM","HIGH"]),desc,truth,reason)

policies=[
    {"POLICY_ID":"POL-001","POLICY_NAME":"Invoice Variance","POLICY_TEXT":"Invoices within 5 percent of an approved PO may be automatically reconciled when supporting contractual evidence exists.","VERSION":"3.1","EFFECTIVE_DATE":"2026-01-01"},
    {"POLICY_ID":"POL-002","POLICY_NAME":"Duplicate Payment","POLICY_TEXT":"Potential duplicate invoices must never be automatically paid or resolved without verification.","VERSION":"2.4","EFFECTIVE_DATE":"2026-01-01"},
    {"POLICY_ID":"POL-003","POLICY_NAME":"Shipment Escalation","POLICY_TEXT":"Delays exceeding 10 days or affecting a committed customer order require human escalation.","VERSION":"4.0","EFFECTIVE_DATE":"2026-01-01"},
    {"POLICY_ID":"POL-004","POLICY_NAME":"Contract Authority","POLICY_TEXT":"Approved contract amendments supersede stale ERP values when amendment effective date precedes invoice or shipment commitment.","VERSION":"5.2","EFFECTIVE_DATE":"2026-01-01"},
    {"POLICY_ID":"POL-005","POLICY_NAME":"Evidence Sufficiency","POLICY_TEXT":"Conflicting or incomplete evidence must not be resolved automatically. Additional evidence or human review is required.","VERSION":"1.8","EFFECTIVE_DATE":"2026-01-01"}
]

audit=[]
for e in exceptions:
    audit.append({
        "AUDIT_ID":f"AUD-{e['EXCEPTION_ID']}",
        "EXCEPTION_ID":e["EXCEPTION_ID"],
        "TIMESTAMP":e["DETECTED_AT"],
        "STAGE":"DETECTION",
        "AGENT":"exception_detector",
        "ACTION":"CREATE_EXCEPTION",
        "DECISION":"OPEN",
        "REASON":"Rule-based exception detected.",
        "EVIDENCE":e["DESCRIPTION"]
    })

write_csv("suppliers.csv",suppliers,list(suppliers[0].keys()))
write_csv("contracts.csv",contracts,list(contracts[0].keys()))
write_csv("contract_amendments.csv",amendments,["AMENDMENT_ID","CONTRACT_ID","AMENDMENT_DATE","FIELD_CHANGED","OLD_VALUE","NEW_VALUE","REASON"])
write_csv("purchase_orders.csv",pos,list(pos[0].keys()))
write_csv("invoices.csv",invoices,list(invoices[0].keys()))
write_csv("orders.csv",orders,list(orders[0].keys()))
write_csv("shipments.csv",shipments,list(shipments[0].keys()))
write_csv("supplier_communications.csv",communications,["COMMUNICATION_ID","SUPPLIER_ID","COMMUNICATION_DATE","CHANNEL","SUBJECT","CONTENT"])
write_csv("erp_events.csv",erp_events,["EVENT_ID","EVENT_TIMESTAMP","ENTITY_TYPE","ENTITY_ID","EVENT_TYPE","DESCRIPTION"])
write_csv("policies.csv",policies,list(policies[0].keys()))
write_csv("exceptions.csv",exceptions,list(exceptions[0].keys()))
write_csv("ground_truth.csv",ground_truth,["EXCEPTION_ID","TRUE_OUTCOME","TRUE_REASON"])
write_csv("exception_audit_log.csv",audit,list(audit[0].keys()))

print(f"Generated {len(suppliers)} suppliers")
print(f"Generated {len(contracts)} contracts")
print(f"Generated {len(pos)} purchase orders")
print(f"Generated {len(invoices)} invoices")
print(f"Generated {len(orders)} orders")
print(f"Generated {len(shipments)} shipments")
print(f"Generated {len(communications)} supplier communications")
print(f"Generated {len(erp_events)} ERP events")
print(f"Generated {len(exceptions)} initial exceptions")
print(f"Generated {len(ground_truth)} hidden evaluation labels")
print(f"Output: {OUT}")

