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
    div[data-testid="stSidebar"] button[kind="secondary"] {
        padding: 2px 8px;
        font-size: 0.8rem;
    }
</style>
""", unsafe_allow_html=True)


# ---------------------------------------------------------
# Cached Snowflake Data Access
# ---------------------------------------------------------
@st.cache_data(ttl=30)
def get_channel_metrics():
    """Fetches channel-level summary KPIs for active creators."""
    conn = load_snowflake.get_snowflake_connection()
    try:
        query = """
        SELECT 
            m.channel_id,
            m.channel_title,
            w.channel_handle,
            m.total_tracked_videos,
            m.total_views,
            m.total_likes,
            m.total_comments,
            m.engagement_rate,
            m.max_hourly_velocity,
            m.avg_hourly_velocity,
            m.latest_snapshot_at
        FROM RAW.MART_CHANNEL_PERFORMANCE m
        INNER JOIN RAW.WATCHLIST w ON m.channel_id = w.channel_id
        WHERE w.is_active = TRUE
        ORDER BY m.total_views DESC;
        """
        df = pd.read_sql(query, conn)
        df.columns = [col.upper() for col in df.columns]
        if not df.empty:
            df["DISPLAY_NAME"] = df["CHANNEL_TITLE"] + " (" + df["CHANNEL_HANDLE"] + ")"
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
            hours_between_snapshots,
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
def get_watchlist(active_only=True):
    """Fetches creators from the Watchlist table."""
    conn = load_snowflake.get_snowflake_connection()
    try:
        where_clause = "WHERE is_active = TRUE" if active_only else ""
        query = f"SELECT channel_id, channel_handle, channel_title, added_at, is_active FROM RAW.WATCHLIST {where_clause} ORDER BY added_at DESC;"
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


def deactivate_channel(channel_id):
    """Soft-deletes (deactivates) a creator in the Snowflake Watchlist."""
    conn = load_snowflake.get_snowflake_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(f"UPDATE RAW.WATCHLIST SET is_active = FALSE WHERE channel_id = '{channel_id}';")
        conn.commit()
        cursor.close()
    finally:
        conn.close()


# ---------------------------------------------------------
# Sidebar: Watchlist & Pipeline Controls
# ---------------------------------------------------------
with st.sidebar:
    st.title("⚡ CreatorPulse")
    st.markdown("---")
    
    st.subheader("📋 Track New Creator")
    new_handle = st.text_input("YouTube Handle", placeholder="@mkbhd or @penguinz0")
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
                    
                    # Run dbt to rebuild the analytics marts with the new creator
                    with st.spinner("Rebuilding dbt marts..."):
                        import subprocess
                        dbt_bin = os.path.join(PROJECT_ROOT, ".venv", "bin", "dbt")
                        transform_dir = os.path.join(PROJECT_ROOT, "transform")
                        subprocess.run(
                            [dbt_bin, "run", "--profiles-dir", "."],
                            cwd=transform_dir,
                            env=dict(os.environ),
                            check=True
                        )
                    
                    st.cache_data.clear()
                    st.rerun()
                except Exception as e:
                    st.error(f"Error adding channel: {e}")
        else:
            st.warning("Please enter a valid channel handle.")

    st.markdown("---")
    st.subheader("👥 Active Watchlist")
    watchlist_df = get_watchlist(active_only=True)
    if not watchlist_df.empty:
        for _, row in watchlist_df.iterrows():
            c_info, c_btn = st.columns([4, 1])
            c_info.markdown(f"**{row['CHANNEL_TITLE']}**  \n<span style='color: #718096; font-size: 0.85rem;'>{row['CHANNEL_HANDLE']}</span>", unsafe_allow_html=True)
            if c_btn.button("✖", key=f"untrack_{row['CHANNEL_ID']}", help=f"Stop tracking {row['CHANNEL_TITLE']}"):
                deactivate_channel(row['CHANNEL_ID'])
                st.cache_data.clear()
                st.rerun()
    else:
        st.caption("No creators currently active.")

    st.markdown("---")
    st.subheader("⚙️ Pipeline Controls")
    
    if st.button("🚀 Take Snapshot Now", use_container_width=True, help="Scrapes fresh metrics from YouTube for all active creators, stages to Snowflake, and runs dbt."):
        with st.spinner("1/2 Fetching fresh snapshots from YouTube..."):
            try:
                import subprocess
                active_watchlist = get_watchlist(active_only=True)
                handles = active_watchlist["CHANNEL_HANDLE"].tolist() if not active_watchlist.empty else ["@mkbhd"]
                for handle in handles:
                    fetch_youtube.run_fetch_pipeline(handle=handle)
                    load_snowflake.run_load_pipeline()

                with st.spinner("2/2 Rebuilding dbt models & velocity tables..."):
                    dbt_bin = os.path.join(PROJECT_ROOT, ".venv", "bin", "dbt")
                    transform_dir = os.path.join(PROJECT_ROOT, "transform")
                    subprocess.run(
                        [dbt_bin, "run", "--profiles-dir", "."],
                        cwd=transform_dir,
                        env=dict(os.environ),
                        check=True
                    )
                
                st.success("🎉 New snapshot captured and velocity models updated!")
                st.cache_data.clear()
                st.rerun()
            except Exception as e:
                st.error(f"Pipeline execution failed: {e}")

    if st.button("🔄 Refresh View Only", use_container_width=True, help="Re-queries Snowflake without scraping YouTube."):
        st.cache_data.clear()
        st.rerun()
        

# ---------------------------------------------------------
# Main Dashboard View
# ---------------------------------------------------------
st.title("📊 CreatorPulse Dashboard")

channel_df = get_channel_metrics()

if channel_df.empty:
    st.info("No active creators found in your Watchlist. Add a channel in the sidebar to start tracking!")
    st.stop()

# Creator Selection Dropdown with Name + Handle
creator_display_list = channel_df["DISPLAY_NAME"].tolist()
selected_display = st.selectbox("Select Creator to Inspect:", options=creator_display_list)

# Filter channel metrics
current_creator_row = channel_df[channel_df["DISPLAY_NAME"] == selected_display].iloc[0]
channel_id = current_creator_row["CHANNEL_ID"]

# ---------------------------------------------------------
# Top Metric Cards (Executive Overview)
# ---------------------------------------------------------
total_views = current_creator_row["TOTAL_VIEWS"]
engagement_rate = current_creator_row["ENGAGEMENT_RATE"]
max_vel = current_creator_row["MAX_HOURLY_VELOCITY"]
avg_vel = current_creator_row["AVG_HOURLY_VELOCITY"]
total_videos = current_creator_row["TOTAL_TRACKED_VIDEOS"]
last_updated = current_creator_row["LATEST_SNAPSHOT_AT"]

col1, col2, col3, col4, col5 = st.columns(5)

with col1:
    st.metric(
        label="Total Tracked Views",
        value=f"{total_views:,.0f} views" if pd.notnull(total_views) else "0 views",
        help="Cumulative views across all tracked uploads."
    )

with col2:
    st.metric(
        label="Audience Engagement",
        value=f"{engagement_rate:.2f}%" if pd.notnull(engagement_rate) else "0.00%",
        help="Ratio of interactions: (Total Likes + Total Comments) / Total Views * 100"
    )

with col3:
    vel_display = f"{max_vel:,.0f} views/hr" if pd.notnull(max_vel) and max_vel > 0 else "Calibrating..."
    st.metric(
        label="Peak Velocity Observed",
        value=vel_display,
        help="Fastest hourly view gain recorded across snapshot intervals (Δviews / Δhours)."
    )

with col4:
    avg_vel_display = f"{avg_vel:,.0f} views/hr" if pd.notnull(avg_vel) and avg_vel > 0 else "Calibrating..."
    st.metric(
        label="Avg Channel Velocity",
        value=avg_vel_display,
        help="Average rate of view accumulation across all snapshot intervals (Δviews / Δhours)."
    )

with col5:
    st.metric(
        label="Active Tracked Videos",
        value=f"{total_videos} videos",
        help="Number of recent video uploads actively tracked."
    )

st.markdown("---")

# ---------------------------------------------------------
# Visualizations: Growth Curves & Velocity
# ---------------------------------------------------------
velocity_df = get_video_velocities(channel_id=channel_id)

tab1, tab2, tab3 = st.tabs(["📈 Video Growth Curves", "⚡ Hourly Velocity Spikes", "🔍 Raw Data Explorer"])

with tab1:
    st.subheader("Time-Series Video Growth Curves")
    st.caption("Cumulative view count trajectory across consecutive snapshot intervals.")
    
    if not velocity_df.empty:
        chart = alt.Chart(velocity_df).mark_line(point=True).encode(
            x=alt.X("EXTRACTED_AT:T", title="Snapshot Time (UTC)"),
            y=alt.Y("VIEW_COUNT:Q", title="Total Views (cumulative)"),
            color=alt.Color("VIDEO_TITLE:N", legend=alt.Legend(title="Video Title", orient="bottom")),
            tooltip=[
                alt.Tooltip("VIDEO_TITLE:N", title="Video"),
                alt.Tooltip("VIEW_COUNT:Q", title="Total Views", format=","),
                alt.Tooltip("DELTA_VIEWS:Q", title="Δ Views Gained", format="+,"),
                alt.Tooltip("HOURLY_VELOCITY:Q", title="Hourly Velocity (views/hr)", format=",.1f"),
                alt.Tooltip("EXTRACTED_AT:T", title="Snapshot Time (UTC)", format="%Y-%m-%d %H:%M")
            ]
        ).properties(
            height=420
        ).interactive()
        
        st.altair_chart(chart, use_container_width=True)
    else:
        st.info("No velocity history available yet.")

with tab2:
    st.subheader("Current Video Velocity (Views / Hour)")
    st.caption("Real-time view accumulation rate (Δviews / Δhours) based on the latest snapshot interval.")
    
    # Filter to latest snapshot for each video to show current velocity
    latest_velocities = velocity_df.sort_values("EXTRACTED_AT").groupby("VIDEO_ID").last().reset_index()
    valid_velocities = latest_velocities[latest_velocities["HOURLY_VELOCITY"].notnull()]
    
    if not valid_velocities.empty:
        bar_chart = alt.Chart(valid_velocities).mark_bar(cornerRadiusTopLeft=6, cornerRadiusTopRight=6).encode(
            x=alt.X("HOURLY_VELOCITY:Q", title="Hourly Velocity (views / hour)"),
            y=alt.Y("VIDEO_TITLE:N", sort="-x", title="Video Title"),
            color=alt.Color("HOURLY_VELOCITY:Q", scale=alt.Scale(scheme="goldorange"), legend=None),
            tooltip=[
                alt.Tooltip("VIDEO_TITLE:N", title="Video"),
                alt.Tooltip("HOURLY_VELOCITY:Q", title="Hourly Velocity (views/hr)", format=",.1f"),
                alt.Tooltip("DELTA_VIEWS:Q", title="Views Gained (Δviews)", format="+,"),
                alt.Tooltip("VIEW_COUNT:Q", title="Total Views", format=","),
                alt.Tooltip("HOURS_BETWEEN_SNAPSHOTS:Q", title="Interval Elapsed (hrs)", format=",.2f")
            ]
        ).properties(
            height=320
        )
        st.altair_chart(bar_chart, use_container_width=True)
    else:
        st.info("Velocity requires at least 2 snapshot intervals to compute deltas. As snapshots accumulate, bars will render here automatically!")

with tab3:
    st.subheader("Raw Snapshot & Mart Data (Auditing Layer)")
    st.caption("Live records from `RAW.FCT_VIDEO_VELOCITY` with standardized metrics.")
    
    if not velocity_df.empty:
        display_cols = [
            "VIDEO_TITLE", "VIEW_COUNT", "PREV_VIEW_COUNT", 
            "DELTA_VIEWS", "HOURS_BETWEEN_SNAPSHOTS", "HOURLY_VELOCITY", "VIDEO_AGE_HOURS", "EXTRACTED_AT"
        ]
        st.dataframe(
            velocity_df[display_cols].sort_values("EXTRACTED_AT", ascending=False),
            use_container_width=True,
            hide_index=True,
            column_config={
                "VIDEO_TITLE": st.column_config.TextColumn("Video Title"),
                "VIEW_COUNT": st.column_config.NumberColumn("Total Views", format="%d views"),
                "PREV_VIEW_COUNT": st.column_config.NumberColumn("Prior Views", format="%d views"),
                "DELTA_VIEWS": st.column_config.NumberColumn("Δ Views Gained", format="+%d views"),
                "HOURS_BETWEEN_SNAPSHOTS": st.column_config.NumberColumn("Interval", format="%.2f hrs"),
                "HOURLY_VELOCITY": st.column_config.NumberColumn("Hourly Velocity", format="%.1f views/hr"),
                "VIDEO_AGE_HOURS": st.column_config.NumberColumn("Video Age", format="%d hrs"),
                "EXTRACTED_AT": st.column_config.DatetimeColumn("Snapshot Time (UTC)", format="YYYY-MM-DD HH:mm:ss"),
            }
        )
    else:
        st.write("No snapshot rows found.")
