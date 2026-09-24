def aggregate_views(events):
    """events example:
            [
            {"user_id": 101, "platform": "youtube", "views": 120},
            {"user_id": 102, "platform": "tiktok", "views": 80},
            {"user_id": 101, "platform": "youtube", "views": 50},
            {"user_id": 103, "platform": "instagram", "views": 200},
            {"user_id": 104, "platform": "tiktok", "views": 70},
            {"user_id": 102, "platform": "tiktok", "views": 30},
        ]
        """
    platform_views = dict()
    for event in events:
        platform = event["platform"]
        views = event["views"]
        platform_views[platform] = platform_views.get(platform, 0) + views
    return platform_views

events = [
    {"user_id": 101, "platform": "youtube", "views": 120},
    {"user_id": 102, "platform": "tiktok", "views": 80},
    {"user_id": 101, "platform": "youtube", "views": 50},
    {"user_id": 103, "platform": "instagram", "views": 200},
    {"user_id": 104, "platform": "tiktok", "views": 70},
    {"user_id": 102, "platform": "tiktok", "views": 30},
]
print('hellow world')
print(aggregate_views(events))