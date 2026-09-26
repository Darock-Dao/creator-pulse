import os
import snowflake.connector
from dotenv import load_dotenv

load_dotenv()

def get_snowflake_connection():
    """Establishes and returns a connection to the Snowflake warehouse."""
    conn = snowflake.connector.connect(
        account=os.getenv("SNOWFLAKE_ACCOUNT"),
        user=os.getenv("SNOWFLAKE_USER"),
        password=os.getenv("SNOWFLAKE_PASSWORD"),
        warehouse=os.getenv("SNOWFLAKE_WAREHOUSE"),
        database=os.getenv("SNOWFLAKE_DATABASE"),
        schema=os.getenv("SNOWFLAKE_SCHEMA"),
        role=os.getenv("SNOWFLAKE_ROLE")
    )
    return conn

if __name__ == "__main__":
    print("Testing Snowflake connection...")
    try:
        conn = get_snowflake_connection()
        cursor = conn.cursor()
        
        # Test query to verify active session details
        cursor.execute("SELECT CURRENT_VERSION(), CURRENT_WAREHOUSE(), CURRENT_DATABASE(), CURRENT_ROLE();")
        version, warehouse, database, role = cursor.fetchone()
        
        print("\n✅ Successfully connected to Snowflake!")
        print(f"Snowflake Version: {version}")
        print(f"Active Warehouse:  {warehouse}")
        print(f"Active Database:   {database}")
        print(f"Active Role:       {role}")
        
        cursor.close()
        conn.close()
    except Exception as e:
        print(f"\n❌ Connection failed: {e}")
