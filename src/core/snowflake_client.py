import os
import snowflake.connector
from dotenv import load_dotenv
load_dotenv()
def get_connection():
    return snowflake.connector.connect(
        account=os.environ["SNOWFLAKE_ACCOUNT"],
        user=os.environ["SNOWFLAKE_USER"],
        authenticator=os.getenv("SNOWFLAKE_AUTHENTICATOR","externalbrowser"),
        role=os.getenv("SNOWFLAKE_ROLE","ACCOUNTADMIN"),
        warehouse=os.getenv("SNOWFLAKE_WAREHOUSE","COMPUTE_WH"),
        database=os.getenv("SNOWFLAKE_DATABASE","EXCEPTION_RESOLVER"),
        schema=os.getenv("SNOWFLAKE_SCHEMA","ENTERPRISE"),
    )