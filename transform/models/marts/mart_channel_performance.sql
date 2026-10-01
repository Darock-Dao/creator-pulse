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
)