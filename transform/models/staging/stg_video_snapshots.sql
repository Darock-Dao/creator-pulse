SELECT 
    snapshot_id,
    video_id,
    channel_id,
    channel_title,
    video_title,
    published_at,
    view_count,
    COALESCE(like_count, 0) AS like_count,
    COALESCE(comment_count, 0) AS comment_count,
    extracted_at,
    loaded_at
FROM CREATOR_PULSE_DEV.RAW.VIDEO_SNAPSHOTS
QUALIFY ROW_NUMBER() OVER (
    PARTITION BY video_id, extracted_at 
    ORDER BY loaded_at DESC
) = 1