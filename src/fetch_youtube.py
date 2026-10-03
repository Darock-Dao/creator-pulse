"""Fetches creator data from YouTube using YouTube's Data API V3.
"""
import warnings
warnings.filterwarnings("ignore", category=FutureWarning)
import os
from datetime import datetime, timezone
from dotenv import load_dotenv
import googleapiclient.discovery
import googleapiclient.errors
import hashlib
import json

load_dotenv()

api_key = os.getenv("YOUTUBE_API_KEY")
youtube = googleapiclient.discovery.build("youtube", "v3", developerKey=api_key)

def get_channel_details(youtube, handle):
    """Takes a channel handle (e.g., "@mkbhd").
        Calls channels().list(forHandle=handle, part="snippet,contentDetails").
        Returns:
        channel_id (e.g. UC...)
        channel_title (e.g. Marques Brownlee)
        uploads_playlist_id (e.g. UU...)"""

    request = youtube.channels().list(
        part="snippet,contentDetails,statistics",
        forHandle=handle
    )
    response = request.execute()

    items = response.get("items", [])
    if not items:
        return None
    channel = items[0]
    return {
        "channel_id": channel["id"],
        "channel_title": channel["snippet"]["title"],
        "uploads_playlist_id": channel["contentDetails"]["relatedPlaylists"]["uploads"]
    }

def get_recent_video_ids(youtube, uploads_playlist_id, max_results=10):
    """Calls playlistItems().list(playlistId=uploads_playlist_id, 
                                    maxResults=max_results, 
                                    part="contentDetails").
        Extracts and returns a list of video ID strings: ['dQw4w9WgXcQ', ...]."""

    request = youtube.playlistItems().list(
        part="contentDetails",
        playlistId=uploads_playlist_id,
        maxResults=max_results
    )

    response = request.execute()
    items = response.get("items", [])
    return [item["contentDetails"]["videoId"] for item in items]


def get_video_snapshots(youtube, video_ids, channel_info):
    """Calls videos().list(id=",".join(video_ids), part="snippet,statistics").
        Returns clean, structured dictionary objects representing each video snapshot."""
    request = youtube.videos().list(
        part="snippet,statistics",
        id=",".join(video_ids)
    )

    response = request.execute()
    items = response.get("items", [])
    formatted_items = []
    extracted_at = datetime.now(timezone.utc).isoformat()
    for item in items:
        stats = item.get("statistics", {})
        formatted_items.append(
            {
                "snapshot_id": hashlib.md5(f"{item['id']}_{extracted_at}".encode()).hexdigest(),
                "video_id": item["id"],
                "channel_id": item["snippet"]["channelId"],
                "channel_title": item["snippet"]["channelTitle"],
                "video_title": item["snippet"]["title"],
                "published_at": item["snippet"]["publishedAt"],
                "view_count": int(stats.get("viewCount", 0)),
                "like_count": int(stats.get("likeCount", 0)),
                "comment_count": int(stats.get("commentCount", 0)),
                "extracted_at": extracted_at
            }
        )
    return formatted_items

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

def run_fetch_pipeline(handle="@mkbhd", destination_file="data/staged/snapshots.jsonl"):
    channel_details = get_channel_details(youtube, handle)
    if not channel_details:
        raise ValueError(f"Could not resolve channel details for handle: {handle}")

    recent_video_ids = get_recent_video_ids(youtube, channel_details["uploads_playlist_id"], max_results=5)
    recent_video_snapshots = get_video_snapshots(youtube, recent_video_ids, channel_details)
    
    # Use destination_file parameter here:
    save_to_jsonl(recent_video_snapshots, destination_file)

def test_getting_snapshots():
    test_handle = "@mkbhd"
    print(f"1. Fetching channel details for {test_handle}...")
    channel_info = get_channel_details(youtube, test_handle)
    print("Channel Info:", channel_info)

    if channel_info:
        uploads_id = channel_info["uploads_playlist_id"]
        print(f"\n2. Fetching recent video IDs from uploads playlist: {uploads_id}...")
        video_ids = get_recent_video_ids(youtube, uploads_id, max_results=5)
        print("Recent Video IDs:", video_ids)
        print(f"Total videos fetched: {len(video_ids)}")

    if channel_info and video_ids:
        video_snapshots = get_video_snapshots(youtube, video_ids, channel_info)
        print("Recent Video snaphots:", video_snapshots)

if __name__ == "__main__":
    pass
