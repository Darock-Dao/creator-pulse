import googleapiclient
import os
import snowflake.connector
from dotenv import load_dotenv
import json
import fetch_youtube

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
    """Writes a list of snapshot dictionaries to a JSON Lines (.jsonl) file.

    Args:
        snapshots (list[dict]): List of extracted video snapshot records.
        destination_file_path (str): Destination path for the .jsonl file.
    """
    directory = os.path.dirname(destination_file_path)
    if directory:
        os.makedirs(directory, exist_ok=True)

    with open(destination_file_path, "w", encoding="utf-8") as f:
        for snapshot in snapshots:
            f.write(json.dumps(snapshot) + "\n")

def stage_file(conn, file_path, stage_name):
    """Uploads a local .jsonl file to a Snowflake internal stage using the PUT command.

    Args:
        conn: Active Snowflake connection object.
        file_path (str): Path to the local .jsonl file.
        stage_name (str): Target Snowflake stage (e.g. '@RAW.STAGE_YOUTUBE').
    """
    abs_path = os.path.abspath(file_path)

    # Ensure stage_name starts with @
    target_stage = stage_name if stage_name.startswith("@") else f"@{stage_name}"

    with conn.cursor() as cursor:
        cursor.execute(f"PUT file://{abs_path} {target_stage} AUTO_COMPRESS=TRUE OVERWRITE=TRUE;")

def copy_into_table(conn, target_table, stage_name):
    """Loads staged JSON data from an internal stage into a Snowflake table.

    Args:
        conn: Active Snowflake connection object.
        target_table (str): Target table name (e.g. 'RAW.VIDEO_SNAPSHOTS').
        stage_name (str): Source stage containing the data files.
    """

    # Ensure stage_name starts with @
    target_stage = stage_name if stage_name.startswith("@") else f"@{stage_name}"

    query = f"""
    COPY INTO {target_table} (
        snapshot_id,
        video_id,
        channel_id,
        channel_title,
        video_title,
        published_at,
        view_count,
        like_count,
        comment_count,
        extracted_at
    )
        FROM (
           SELECT
               $1:snapshot_id::VARCHAR,
               $1:video_id::VARCHAR,
               $1:channel_id::VARCHAR,
               $1:channel_title::VARCHAR,
               $1:video_title::VARCHAR,
               $1:published_at::TIMESTAMP_NTZ,
               $1:view_count::INTEGER,
               $1:like_count::INTEGER,
               $1:comment_count::INTEGER,
               $1:extracted_at::TIMESTAMP_NTZ
            FROM {target_stage}
        )
        
        FILE_FORMAT = (FORMAT_NAME = 'RAW.JSON_FORMAT')
        ON_ERROR = 'CONTINUE';
    """

    with conn.cursor() as cursor:
        cursor.execute(query)
        results = cursor.fetchall()
        for row in results:
            print(f"File: {row[0]} | Status: {row[1]} | Rows Loaded: {row[3]}")

def test_snowflake_connection():
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

def test_bulk_data_loading():
    api_key = os.getenv("YOUTUBE_API_KEY")
    youtube = googleapiclient.discovery.build("youtube", "v3", developerKey=api_key)
    snowflake_conn = get_snowflake_connection()

    test_handle = "@mkbhd" #Marques Brownlee's handle
    channel_info = fetch_youtube.get_channel_details(youtube, test_handle)
    if channel_info:
        uploads_id = channel_info["uploads_playlist_id"]
        video_ids = fetch_youtube.get_recent_video_ids(youtube, uploads_id, max_results=5)

    if channel_info and video_ids:
        video_snapshots = fetch_youtube.get_video_snapshots(youtube, video_ids, channel_info)

        save_to_jsonl(video_snapshots, "data/staged/snapshots.jsonl")
        stage_file(snowflake_conn, "data/staged/snapshots.jsonl", "RAW.STAGE_YOUTUBE")
        copy_into_table(snowflake_conn, "RAW.VIDEO_SNAPSHOTS", "RAW.STAGE_YOUTUBE")

        print("\n🎉 Bulk load completed successfully!")
        snowflake_conn.close()

if __name__ == "__main__":
    test_bulk_data_loading()
