WITH
snapshots AS (
    SELECT * FROM {{ ref('stg_video_snapshots')}}
),
snapshots_with_lags AS(
    
)
compute_velocities AS(

)

SELECT * FROM compute_velocities