from pprint import pprint
from src.core.snowflake_client import get_connection
from src.analysis_engine import discover_impact_propagation,simulate_counterfactual,detect_state_divergence,scan_state_divergences,cluster_root_causes
connection=get_connection()
try:
    print("\n=== IMPACT PROPAGATION ===")
    impact=discover_impact_propagation(connection,"EXC-0003")
    pprint({
        "contracts":len(impact["contracts"]),
        "amendments":len(impact["amendments"]),
        "purchase_orders":len(impact["purchase_orders"]),
        "orders":len(impact["orders"]),
        "invoices":len(impact["invoices"]),
        "shipments":len(impact["shipments"]),
        "related_exceptions":len(impact["related_exceptions"]),
    })
    print("\n=== COUNTERFACTUAL ANALYSIS ===")
    pprint(simulate_counterfactual(connection,"EXC-0003"))
    print("\n=== STATE DIVERGENCE ANALYSIS ===")
    pprint(detect_state_divergence(connection,"EXC-0003"))
    print("\n=== ENTERPRISE STATE DIVERGENCE SCAN ===")
    divergences=scan_state_divergences(connection)
    print(f"TOTAL DIVERGENCES: {len(divergences)}")
    for item in divergences:
        print(f"\n{item['po_id']} | {item['amendment_id']} | {item['propagation_status']}")
        print(f"  authoritative: {item['new_value']}")
        print(f"  operational:   {item['current_value']}")
        print(f"  downstream:    {item['downstream_exposure']}")
    print("\n=== ROOT-CAUSE CLUSTERING ===")
    clusters=cluster_root_causes(connection)
    print(f"TOTAL CLUSTERS: {len(clusters)}")
finally:
    connection.close()