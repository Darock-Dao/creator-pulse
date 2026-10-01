WITH video_velocities AS 
(
    SELECT * FROM {{ ref('fct_video_velocity')}}
),
latest_velocities AS
(
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
        hourly_velocity
    FROM video_velocities
    QUALIFY ROW_NUMBER() OVER 
        (PARTITION BY video_id 
        ORDER BY extracted_at DESC) = 1
),
channel_summary AS
(
    SELECT
        channel_id,
        channel_title,
        COUNT(DISTINCT video_id) AS total_tracked_videos,
        SUM(view_count) AS total_views,
        SUM(like_count) AS total_likes,
        SUM(comment_count) AS total_comments,
        ROUND((SUM(like_count) + SUM(comment_count)) / NULLIF(SUM(view_count), 0) * 100, 2) AS engagement_rate,
        ROUND(MAX(hourly_velocity), 2) AS max_hourly_velocity,
        ROUND(AVG(hourly_velocity), 2) AS avg_hourly_velocity,
        MAX(extracted_at) AS latest_snapshot_at
    FROM latest_velocities
    GROUP BY channel_id, channel_title
)

SELECT * FROM channel_summary