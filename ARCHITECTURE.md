# CreatorPulse: End-to-End YouTube Velocity & Analytics Pipeline

## 1. Project Overview & Objective

**CreatorPulse** is a production-grade data engineering pipeline that tracks social media content performance over time. 

### Why This Project Exists (The Core Engineering Problem)
The public YouTube Data API only returns **point-in-time lifetime counters** (e.g., *"Video X currently has 1,500,000 views"*). It does **not** provide historical day-by-day or hour-by-hour view trends.

To calculate **content velocity** (how fast a video is gaining views right now), **initial 48-hour launch traction**, and **engagement decay curves**, we must snapshot video metrics periodically. 

CreatorPulse solves this by allowing users to add any YouTube creator to a **Watchlist**, continuously snapshotting their video metrics, storing the time-series history in **Snowflake**, calculating velocity metrics using **dbt window functions**, orchestrating with **Apache Airflow**, and presenting interactive growth curves in a **Streamlit GUI**.

---

## 2. Technical Stack

* **Language & Ingestion:** Python (Google API Client / YouTube Data API v3)
* **Data Warehouse:** Snowflake (Internal stages & bulk `COPY INTO`)
* **Transformation & Modeling:** dbt (`dbt-snowflake` with staging, marts, window functions, and schema tests)
* **Workflow Orchestration:** Apache Airflow (Scheduled DAGs, retries, and idempotent loads)
* **User Interface:** Streamlit (Channel watchlist management & visual velocity dashboard)
* **Version Control:** Git & GitHub

---

## 3. Architecture Overview

```text
               ┌────────────────────────────────────────────────────────┐
               │              Streamlit GUI                             │
               │  - Add YouTube channels to Watchlist                   │
               │  - View Video Growth Curves & Velocity Leaderboards    │
               └──────────▲──────────────────────────────────▲──────────┘
                          │ (reads)                          │ (adds channel)
                          │                                  ▼
               ┌──────────┴───────────────┐     ┌───────────────────────┐
               │ dbt Analytics Marts      │     │ RAW.WATCHLIST         │
               │ - fct_video_velocity     │     │ (channel_id, handle)  │
               │ - mart_channel_trends    │     └───────────┬───────────┘
               └──────────▲───────────────┘                 │
                          │                                 │ (reads active channels)
               ┌──────────┴───────────────┐                 ▼
               │ Snowflake Raw Layer      │     ┌───────────────────────┐
               │ - RAW.VIDEO_SNAPSHOTS    │◄────┤ Airflow Orchestration │
               └──────────────────────────┘     │ - Python Ingestion    │
                                                │ - YouTube API v3      │
                                                │ - COPY INTO Snowflake │
                                                │ - dbt run & dbt test  │
                                                └───────────────────────┘
```

---

## 4. Ingestion Layer: Python & YouTube Data API v3

### Setup:
* YouTube Data API v3 key via Google Cloud Console (Free tier).

### API Quota Strategy (High-Value Interview Talking Point):
* YouTube limits free accounts to **10,000 units/day**.
* A `search` endpoint call costs **100 units** (expensive and inefficient).
* Fetching a channel's **"Uploads" playlist** costs **1 unit**, and batch fetching 50 videos via `videos.list` costs **1 unit**.
* *Design Decision:* Ingestion resolves the channel's `uploads_playlist_id`, fetches the latest 10–20 video IDs, and batch-fetches their statistics in a single call.

### Extracted Snapshot Schema:
Each video snapshot contains:
```json
{
  "snapshot_id": "c1a2b3... (hash of video_id + extracted_at)",
  "video_id": "dQw4w9WgXcQ",
  "channel_id": "UCuAXFkgsw1L7xaCfnd5JJOw",
  "channel_title": "Rick Astley",
  "video_title": "Never Gonna Give You Up",
  "published_at": "2009-10-25T06:57:33Z",
  "view_count": 1450000000,
  "like_count": 16000000,
  "comment_count": 2100000,
  "extracted_at": "2026-09-24T12:00:00Z"
}
```

### Ingestion Output:
* Validated records are written to a local `.jsonl` or `.parquet` staging file.

---

## 5. Storage Layer: Snowflake

### Database & Schema Setup:
* Database: `CREATOR_PULSE_DEV`
* Schema: `RAW`
* Stage: `@RAW.STAGE_YOUTUBE`

### Tables:

#### 1. `RAW.WATCHLIST` (Managed via GUI / Ingestion)
```sql
CREATE TABLE RAW.WATCHLIST (
    channel_id VARCHAR PRIMARY KEY,
    channel_handle VARCHAR NOT NULL,
    channel_title VARCHAR,
    thumbnail_url VARCHAR,
    added_at TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
    is_active BOOLEAN DEFAULT TRUE
);
```

#### 2. `RAW.VIDEO_SNAPSHOTS` (Append-Only Time-Series Table)
```sql
CREATE TABLE RAW.VIDEO_SNAPSHOTS (
    snapshot_id VARCHAR PRIMARY KEY,
    video_id VARCHAR NOT NULL,
    channel_id VARCHAR NOT NULL,
    channel_title VARCHAR,
    video_title VARCHAR,
    published_at TIMESTAMP_NTZ,
    view_count INTEGER,
    like_count INTEGER,
    comment_count INTEGER,
    extracted_at TIMESTAMP_NTZ NOT NULL,
    loaded_at TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP()
);
```

#### Bulk Loading Pattern:
Python stages the file via `PUT` and executes:
```sql
COPY INTO RAW.VIDEO_SNAPSHOTS (snapshot_id, video_id, channel_id, channel_title, video_title, published_at, view_count, like_count, comment_count, extracted_at)
FROM @RAW.STAGE_YOUTUBE
FILE_FORMAT = (TYPE = 'JSON');
```

---

## 6. Transformation Layer: dbt & Window Functions

### 1. Staging (`models/staging/stg_video_snapshots.sql`)
* Explicitly cast data types (e.g. `to_timestamp_ntz(extracted_at)`).
* Handle null likes/comments (if a creator disables comments, default to `0`).
* Deduplicate identical snapshot timestamps using `QUALIFY ROW_NUMBER() OVER (...) = 1`.

### 2. Fact Table (`models/marts/fct_video_velocity.sql`)
Uses SQL **Window Functions** to compare consecutive snapshots for each video:
```sql
SELECT
    video_id,
    channel_id,
    video_title,
    published_at,
    extracted_at,
    view_count,
    -- Window function: look at previous snapshot
    LAG(view_count) OVER (PARTITION BY video_id ORDER BY extracted_at) AS prev_view_count,
    LAG(extracted_at) OVER (PARTITION BY video_id ORDER BY extracted_at) AS prev_extracted_at,
    
    -- Metrics
    view_count - COALESCE(prev_view_count, view_count) AS delta_views,
    DATEDIFF('hour', prev_extracted_at, extracted_at) AS hours_between_snapshots,
    (view_count - prev_view_count) / NULLIF(DATEDIFF('hour', prev_extracted_at, extracted_at), 0) AS hourly_velocity,
    DATEDIFF('hour', published_at, extracted_at) AS video_age_hours
FROM {{ ref('stg_video_snapshots') }}
```

### 3. Analytics Mart (`models/marts/mart_channel_performance.sql`)
Aggregates performance benchmarks per channel:
* **Initial 48-Hour Velocity:** Total views gained during the first 48 hours post-upload.
* **Engagement Rate:** `(likes + comments) / views * 100`.
* **Top Velocity Video:** The single video that experienced the highest hourly acceleration.

### 4. dbt Tests (`models/schema.yml`):
* `not_null` & `unique` on `snapshot_id` and `video_id`.
* `relationships`: Foreign key check between `fct_video_velocity.channel_id` and `RAW.WATCHLIST.channel_id`.
* Accepted range test: `delta_views >= 0`.

---

## 7. Orchestration Layer: Apache Airflow

### DAG: `creator_pulse_pipeline`
* **Schedule:** Every 6 hours (e.g., `0 */6 * * *`) or daily (`0 0 * * *`).
* **Tasks & Flow:**
  ```text
  fetch_watchlist_and_ingest_youtube
                  ↓
       copy_to_snowflake_raw
                  ↓
               dbt_run
                  ↓
               dbt_test
  ```
* **Error Handling & Idempotency:**
  * Tasks include automatic retries (1–2 retries with 5-minute backoff).
  * `snapshot_id` guarantees that re-running a failed Airflow task for the same execution window will not insert duplicate records into Snowflake.

---

## 8. Presentation Layer: Streamlit GUI

### App Structure (`streamlit_app/app.py`):
1. **Sidebar: Watchlist Manager**
   * Input box: Enter a channel handle (e.g. `@mkbhd`, `@veritasium`).
   * "Track Channel" button: Calls the YouTube API to resolve channel details, saves it to `RAW.WATCHLIST`.
   * Table displaying all currently tracked channels and active status.
2. **Main Dashboard: Creator Velocity Insights**
   * **Creator Selector:** Dropdown to filter by any tracked creator.
   * **KPI Metric Cards:**
     * *Fastest Growing Video Right Now (Views/Hour)*
     * *Average 48-Hour Launch Velocity*
     * *Average Engagement Rate*
   * **Growth Curves (Interactive Line Chart):**
     * X-axis: `video_age_hours`
     * Y-axis: `view_count`
     * Allows comparing how their last 5 uploads perform against each other over time.
   * **Velocity Decay Chart (Bar Chart):**
     * Shows how hourly views drop off after upload day 1, 2, 7, and 14.

---

## 9. Interview Talking Points (Why This Stands Out)

1. **State-over-Time vs. Point-in-Time:** Explain why an on-demand API call fails to measure velocity and why a historical warehouse (Snowflake) + scheduler (Airflow) is required.
2. **API Quota Optimization:** Explain how you avoided 100-unit `search` calls by leveraging the `uploads` playlist and batch `videos.list` calls to stay within free daily quotas.
3. **Advanced SQL Window Functions:** Discuss how you used `LAG()` partitioned by `video_id` to compute hourly view velocity and growth curves.
4. **Snowflake Bulk Staging:** Explain why you used file staging + `COPY INTO` instead of slow, expensive row-level `INSERT` statements.
5. **Airflow Idempotency:** Explain how your pipeline safely handles task retries and backfills without corrupting time-series snapshots.

---

## 10. Step-by-Step Implementation Roadmap

- [X] **Phase 1: YouTube API Ingestion**
  - Set up free YouTube Data API key.
  - Write Python script to resolve a channel handle and fetch the latest 10 video stats.
- [ ] **Phase 2: Snowflake Warehouse Setup**
  - Create database, schema, internal stage, and raw tables (`WATCHLIST`, `VIDEO_SNAPSHOTS`).
- [ ] **Phase 3: Python Bulk Loader**
  - Implement staging and Snowflake `COPY INTO` logic.
- [ ] **Phase 4: dbt Transformations**
  - Initialize dbt project with Snowflake connection.
  - Build `stg_video_snapshots` and `fct_video_velocity` with `LAG()` window calculations.
  - Add schema tests and run `dbt test`.
- [ ] **Phase 5: Airflow Orchestration**
  - Build DAG with task dependencies, retries, and scheduling.
- [ ] **Phase 6: Streamlit GUI**
  - Build the interactive web dashboard for channel input and velocity visualization.
