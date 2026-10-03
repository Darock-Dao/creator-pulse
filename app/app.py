import os
import sys
from datetime import datetime
import pandas as pd
import streamlit as st
import altair as alt
from dotenv import load_dotenv

# Ensure project root is in sys.path so we can import src modules
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

load_dotenv(os.path.join(PROJECT_ROOT, ".env"))

from src import load_snowflake, fetch_youtube

# ---------------------------------------------------------
# Page Configuration & Styling
# ---------------------------------------------------------
st.set_page_config(
    page_title="CreatorPulse | Velocity & Growth Intelligence",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom sleek CSS
st.markdown("""
<style>
    .metric-card {
        background-color: #1E232F;
        border: 1px solid #2D3748;
        border-radius: 10px;
        padding: 16px;
        margin-bottom: 12px;
    }
    .stMetric label {
        font-size: 0.9rem !important;
        color: #A0AEC0 !important;
    }
    .stMetric div[data-testid="stMetricValue"] {
        font-size: 1.8rem !important;
        font-weight: 700 !important;
    }
</style>
""", unsafe_allow_html=True)


# ---------------------------------------------------------
# Cached Snowflake Data Access
# ---------------------------------------------------------
@st.cache_data(ttl=30)
def get_channel_metrics():
    """Fetches channel-level summary KPIs from the analytics mart."""
    conn = load_snowflake.get_snowflake_connection()
    try:
        query = """
        SELECT 
            channel_id,
            channel_title,
            total_tracked_videos,
            total_views,
            total_likes,
            total_comments,
            engagement_rate,
            max_hourly_velocity,
            avg_hourly_velocity,
            latest_snapshot_at
        FROM RAW.MART_CHANNEL_PERFORMANCE
        ORDER BY total_views DESC;
        """
        df = pd.read_sql(query, conn)
        df.columns = [col.upper() for col in df.columns]
        return df
    finally:
        conn.close()


@st.cache_data(ttl=30)
def get_video_velocities(channel_id=None):
    """Fetches time-series snapshot and velocity data from fact table."""
    conn = load_snowflake.get_snowflake_connection()
    try:
        where_clause = f"WHERE channel_id = '{channel_id}'" if channel_id else ""
        query = f"""
        SELECT 
            snapshot_id,
            video_id,
            channel_id,
            channel_title,
            video_title,
            published_at,
            view_count,
            prev_view_count,
            delta_views,
            hourly_velocity,
            video_age_hours,
            extracted_at
        FROM RAW.FCT_VIDEO_VELOCITY
        {where_clause}
        ORDER BY extracted_at ASC;
        """
        df = pd.read_sql(query, conn)
        df.columns = [col.upper() for col in df.columns]
        if not df.empty:
            df['EXTRACTED_AT'] = pd.to_datetime(df['EXTRACTED_AT'])
            df['PUBLISHED_AT'] = pd.to_datetime(df['PUBLISHED_AT'])
        return df
    finally:
        conn.close()


@st.cache_data(ttl=30)
def get_watchlist():
    """Fetches active creators from the Watchlist table."""
    conn = load_snowflake.get_snowflake_connection()
    try:
        query = "SELECT channel_id, channel_handle, channel_title, added_at, is_active FROM RAW.WATCHLIST ORDER BY added_at DESC;"
        df = pd.read_sql(query, conn)
        df.columns = [col.upper() for col in df.columns]
        return df
    except Exception:
        return pd.DataFrame()
    finally:
        conn.close()


def add_channel_to_watchlist(handle):
    """Resolves a channel handle via YouTube API and adds it to Snowflake watchlist."""
    import googleapiclient.discovery
    api_key = os.getenv("YOUTUBE_API_KEY")
    youtube = googleapiclient.discovery.build("youtube", "v3", developerKey=api_key)
    
    channel_details = fetch_youtube.get_channel_details(youtube, handle)
    if not channel_details:
        raise ValueError(f"Could not find YouTube channel for handle '{handle}'")
    
    conn = load_snowflake.get_snowflake_connection()
    try:
        cursor = conn.cursor()
        upsert_query = f"""
        MERGE INTO RAW.WATCHLIST AS target
        USING (SELECT 
            '{channel_details['channel_id']}' AS channel_id,
            '{handle}' AS channel_handle,
            '{channel_details['channel_title'].replace("'", "''")}' AS channel_title
        ) AS source
        ON target.channel_id = source.channel_id
        WHEN MATCHED THEN
            UPDATE SET channel_handle = source.channel_handle, is_active = TRUE
        WHEN NOT MATCHED THEN
            INSERT (channel_id, channel_handle, channel_title, is_active)
            VALUES (source.channel_id, source.channel_handle, source.channel_title, TRUE);
        """
        cursor.execute(upsert_query)
        conn.commit()
        cursor.close()
    finally:
        conn.close()
        
    return channel_details


# ---------------------------------------------------------
# Sidebar: Watchlist & Pipeline Controls
# ---------------------------------------------------------
with st.sidebar:
    st.title("⚡ CreatorPulse")
    st.caption("Real-Time Social Velocity Pipeline")
    st.markdown("---")
    
    st.subheader("📋 Watchlist Manager")
    new_handle = st.text_input("Track New Creator", placeholder="@veritasium or @mkbhd")
    if st.button("➕ Add to Watchlist", use_container_width=True):
        if new_handle:
            clean_handle = new_handle.strip()
            if not clean_handle.startswith("@"):
                clean_handle = f"@{clean_handle}"
            with st.spinner(f"Resolving {clean_handle}..."):
                try:
                    info = add_channel_to_watchlist(clean_handle)
                    st.success(f"Added **{info['channel_title']}** to Watchlist!")
                    # Ingest initial snapshot for the new creator
                    fetch_youtube.run_fetch_pipeline(handle=clean_handle)
                    load_snowflake.run_load_pipeline()
                    st.cache_data.clear()
                    st.rerun()
                except Exception as e:
                    st.error(f"Error adding channel: {e}")
        else:
            st.warning("Please enter a valid channel handle.")

    st.markdown("---")
    st.subheader("⚙️ Data Refresh")
    if st.button("🔄 Refresh Dashboard Data", use_container_width=True):
        st.cache_data.clear()
        st.rerun()
        
    st.markdown("---")
    st.caption("Connected to **Snowflake** (RAW schema) and transformed with **dbt**.")


# ---------------------------------------------------------
# Main Dashboard View
# ---------------------------------------------------------
st.title("📊 Creator Velocity & Traction Intelligence")
st.markdown("Live social media velocity metrics calculated via **Snowflake window functions** and automated with **Airflow**.")

channel_df = get_channel_metrics()

if channel_df.empty:
    st.info("No creator data found in `RAW.MART_CHANNEL_PERFORMANCE`. Run your Airflow DAG or ingestion pipeline to populate data!")
    st.stop()

# Creator Selection Dropdown
creator_list = channel_df["CHANNEL_TITLE"].tolist()
selected_creator = st.selectbox("Select Creator to Inspect:", options=creator_list)

# Filter channel metrics
current_creator_row = channel_df[channel_df["CHANNEL_TITLE"] == selected_creator].iloc[0]
channel_id = current_creator_row["CHANNEL_ID"]

# ---------------------------------------------------------
# Top Metric Cards (Executive Overview)
# ---------------------------------------------------------
total_views = current_creator_row["TOTAL_VIEWS"]
engagement_rate = current_creator_row["ENGAGEMENT_RATE"]
max_vel = current_creator_row["MAX_HOURLY_VELOCITY"]
total_videos = current_creator_row["TOTAL_TRACKED_VIDEOS"]
last_updated = current_creator_row["LATEST_SNAPSHOT_AT"]

col1, col2, col3, col4 = st.columns(4)

with col1:
    st.metric(
        label="Total Tracked Views",
        value=f"{total_views:,.0f}" if pd.notnull(total_views) else "0"
    )

with col2:
    st.metric(
        label="Audience Engagement Rate",
        value=f"{engagement_rate:.2f}%" if pd.notnull(engagement_rate) else "0.00%",
        help="(Total Likes + Total Comments) / Total Views * 100"
    )

with col3:
    vel_display = f"{max_vel:,.0f} views/hr" if pd.notnull(max_vel) and max_vel > 0 else "Calibrating..."
    st.metric(
        label="Peak Velocity Observed",
        value=vel_display,
        help="Fastest hourly view gain recorded across snapshots."
    )

with col4:
    st.metric(
        label="Active Tracked Videos",
        value=f"{total_videos}"
    )

st.markdown("---")

# ---------------------------------------------------------
# Visualizations: Growth Curves & Velocity
# ---------------------------------------------------------
velocity_df = get_video_velocities(channel_id=channel_id)

tab1, tab2, tab3 = st.tabs(["📈 Video Growth Curves", "⚡ Hourly Velocity Spikes", "🔍 Raw Data Explorer"])

with tab1:
    st.subheader("Time-Series Video Growth Curves")
    st.caption("Tracks cumulative view count trajectory across consecutive snapshot intervals.")
    
    if not velocity_df.empty:
        # Altair multi-line interactive chart
        chart = alt.Chart(velocity_df).mark_line(point=True).encode(
            x=alt.X("EXTRACTED_AT:T", title="Snapshot Extracted Timestamp"),
            y=alt.Y("VIEW_COUNT:Q", title="Total Views"),
            color=alt.Color("VIDEO_TITLE:N", legend=alt.Legend(title="Video Title", orient="bottom")),
            tooltip=["VIDEO_TITLE:N", "VIEW_COUNT:Q", "DELTA_VIEWS:Q", "EXTRACTED_AT:T"]
        ).properties(
            height=420
        ).interactive()
        
        st.altair_chart(chart, use_container_width=True)
    else:
        st.info("No velocity history available yet.")

with tab2:
    st.subheader("Current Video Velocity (Views / Hour)")
    st.caption("Derived using `LAG(view_count)` partitioned by `video_id` in dbt.")
    
    # Filter to latest snapshot for each video to show current velocity
    latest_velocities = velocity_df.sort_values("EXTRACTED_AT").groupby("VIDEO_ID").last().reset_index()
    valid_velocities = latest_velocities[latest_velocities["HOURLY_VELOCITY"].notnull()]
    
    if not valid_velocities.empty:
        bar_chart = alt.Chart(valid_velocities).mark_bar(cornerRadiusTopLeft=6, cornerRadiusTopRight=6).encode(
            x=alt.X("HOURLY_VELOCITY:Q", title="Hourly Velocity (Views/Hour)"),
            y=alt.Y("VIDEO_TITLE:N", sort="-x", title="Video Title"),
            color=alt.Color("HOURLY_VELOCITY:Q", scale=alt.Scale(scheme="goldorange"), legend=None),
            tooltip=["VIDEO_TITLE:N", "HOURLY_VELOCITY:Q", "DELTA_VIEWS:Q", "VIEW_COUNT:Q"]
        ).properties(
            height=320
        )
        st.altair_chart(bar_chart, use_container_width=True)
    else:
        st.info("Velocity requires at least 2 snapshot intervals to compute deltas. As snapshots accumulate, bars will render here automatically!")

with tab3:
    st.subheader("Raw Snapshot & Mart Data (Auditing Layer)")
    st.caption("Live records from `RAW.FCT_VIDEO_VELOCITY` in Snowflake.")
    
    if not velocity_df.empty:
        display_cols = [
            "VIDEO_TITLE", "VIEW_COUNT", "PREV_VIEW_COUNT", 
            "DELTA_VIEWS", "HOURLY_VELOCITY", "VIDEO_AGE_HOURS", "EXTRACTED_AT"
        ]
        st.dataframe(
            velocity_df[display_cols].sort_values("EXTRACTED_AT", ascending=False),
            use_container_width=True,
            hide_index=True
        )
    else:
        st.write("No snapshot rows found.")
