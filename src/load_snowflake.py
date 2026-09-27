import os
import snowflake.connector
from dotenv import load_dotenv
import json

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

def save_to_jsonl(snapshots, destination_file_path):
    """Input: A list of snapshot dictionaries 
                and a destination file path (e.g., data/staged/snapshots.jsonl).

        Job: Iterate through the dictionaries and write
            each one as a single JSON line using json.dumps(record) + '\n'."""

    directory = os.path.dirname(destination_file_path)
    if directory:
        os.makedirs(directory, exist_ok=True)

    with open(destination_file_path, "w", encoding="utf-8") as f:
        for snapshot in snapshots:
            f.write(json.dumps(snapshot) + "\n")

def stage_file(conn, file_path, stage_name):
    """Input: The active Snowflake connection/cursor, 
        the local .jsonl file path, and the stage name (@RAW.STAGE_YOUTUBE).

        Job: Execute the Snowflake PUT file:///absolute/path/to/file.jsonl 
        @RAW.STAGE_YOUTUBE AUTO_COMPRESS=TRUE; command to push the file to the cloud."""
    pass

def copy_into_table(conn, target_table, stage_name):
    """Input: The active Snowflake connection/cursor, 
            the target table (RAW.VIDEO_SNAPSHOTS), 
            and the stage name (@RAW.STAGE_YOUTUBE).

        Job: Execute the COPY INTO RAW.VIDEO_SNAPSHOTS 
        (...) FROM @RAW.STAGE_YOUTUBE ... 
        command to parse the JSON and populate the table columns."""
    pass

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
