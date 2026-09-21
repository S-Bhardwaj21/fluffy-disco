import os
import snowflake.connector
from dotenv import load_dotenv
load_dotenv()
def get_connection():
    authenticator=os.getenv("SNOWFLAKE_AUTHENTICATOR","externalbrowser")
    connection_kwargs={
        "account":os.environ["SNOWFLAKE_ACCOUNT"],
        "user":os.environ["SNOWFLAKE_USER"],
        "authenticator":authenticator,
        "role":os.getenv("SNOWFLAKE_ROLE","ACCOUNTADMIN"),
        "warehouse":os.getenv("SNOWFLAKE_WAREHOUSE","COMPUTE_WH"),
        "database":os.getenv("SNOWFLAKE_DATABASE","EXCEPTION_RESOLVER"),
        "schema":os.getenv("SNOWFLAKE_SCHEMA","ENTERPRISE"),
    }
    if authenticator=="SNOWFLAKE_JWT":
        connection_kwargs["private_key_file"]=os.environ["SNOWFLAKE_PRIVATE_KEY_FILE"]
        private_key_passphrase=os.getenv("SNOWFLAKE_PRIVATE_KEY_PASSPHRASE")
        if private_key_passphrase:
            connection_kwargs["private_key_file_pwd"]=private_key_passphrase
    return snowflake.connector.connect(**connection_kwargs)