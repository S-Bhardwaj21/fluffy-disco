from pathlib import Path
from src.core.snowflake_client import get_connection

BASE=Path("data/generated")
TABLES={
    "suppliers.csv":"SUPPLIERS",
    "contracts.csv":"CONTRACTS",
    "contract_amendments.csv":"CONTRACT_AMENDMENTS",
    "purchase_orders.csv":"PURCHASE_ORDERS",
    "invoices.csv":"INVOICES",
    "orders.csv":"ORDERS",
    "shipments.csv":"SHIPMENTS",
    "supplier_communications.csv":"SUPPLIER_COMMUNICATIONS",
    "erp_events.csv":"ERP_EVENTS",
    "policies.csv":"POLICIES",
    "exceptions.csv":"EXCEPTIONS",
    "exception_audit_log.csv":"EXCEPTION_AUDIT_LOG",
}

def main():
    conn=get_connection()
    cur=conn.cursor()
    try:
        for filename,table in TABLES.items():
            path=BASE/filename
            print(f"Loading {filename} -> {table}")
            cur.execute(f"TRUNCATE TABLE {table}")
            cur.execute(f"PUT 'file://{path.resolve().as_posix()}' @EXCEPTION_STAGE OVERWRITE=TRUE AUTO_COMPRESS=FALSE")
            cur.execute(f"COPY INTO {table} FROM @EXCEPTION_STAGE/{filename} FILE_FORMAT=(FORMAT_NAME='CSV_FORMAT') ON_ERROR='ABORT_STATEMENT'")
            print(f"  OK")
        conn.commit()
        print("RELOAD COMPLETE")
    finally:
        cur.close()
        conn.close()

if __name__=="__main__":
    main()