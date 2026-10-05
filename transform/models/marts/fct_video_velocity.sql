WITH
snapshots AS (
    SELECT * FROM {{ ref('stg_video_snapshots')}}
),
snapshots_with_lags AS(
    SELECT 
        snapshot_id,
        video_id,
        channel_id,
        channel_title,
        video_title,
        published_at,
        view_count,
        like_count,
        comment_count,
        extracted_at,
        loaded_at,
        LAG(view_count) OVER 
            (PARTITION BY video_id 
            ORDER BY extracted_at) AS prev_view_count,
        LAG(extracted_at) OVER
            (PARTITION BY video_id 
            ORDER BY extracted_at) AS prev_extracted_at
    FROM snapshots
),
compute_velocities AS(
    SELECT
        snapshot_id,
        video_id,
        channel_id,
        channel_title,
        video_title,
        published_at,
        view_count,
        prev_view_count,
        prev_extracted_at,
        like_count,
        comment_count,
        extracted_at,
        loaded_at,
        view_count - COALESCE(prev_view_count, view_count) AS delta_views,
        ROUND(DATEDIFF('second', prev_extracted_at, extracted_at) / 3600.0, 4) AS hours_between_snapshots,
        ROUND((view_count - prev_view_count) / NULLIF(DATEDIFF('second', prev_extracted_at, extracted_at) / 3600.0, 0), 2) AS hourly_velocity,
        DATEDIFF('hour', published_at, extracted_at) AS video_age_hours
    FROM snapshots_with_lags
)

SELECT * FROM compute_velocities