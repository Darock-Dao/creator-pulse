"""Fetches creator data from YouTube using YouTube's Data API V3.
"""
import os

from dotenv import load_dotenv
import googleapiclient.discovery
import googleapiclient.errors

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
    pass
