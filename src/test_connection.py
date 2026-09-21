from src.core.snowflake_client import get_connection

conn=get_connection()
print("CONNECTED:",conn.is_valid())
conn.close()