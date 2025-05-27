import requests
import asyncio
from typing import Dict

class Poster:
    def __init__(self, base_url: str, token: str):
        self.base_url = base_url
        self.token = token

    def get_headers(self) -> Dict[str, str]:
        return {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.token}"
        }

    async def post_single(self, post_data: dict) -> bool:
        """Post a single post to the API. Returns True on success, False on failure."""
        url = f"{self.base_url}/api/posts"
        headers = self.get_headers()
        def do_post():
            return requests.post(url, headers=headers, json=post_data, allow_redirects=True)
        resp = await asyncio.to_thread(do_post)
        if resp.status_code in (200, 201):
            print(f"Posted to API: {post_data.get('url')}")
            return True
        else:
            print(f"Failed to post to API: {resp.status_code} {resp.text}")
            print(f"Request URL: {url}")
            print(f"Request Headers: {headers}")
            print(f"Request Payload: {post_data}")
            return False

    async def post_thread(self, thread_data: dict) -> bool:
        """Post a thread to the API. Returns True on success, False on failure."""
        url = f"{self.base_url}/api/threads"
        headers = self.get_headers()
        def do_post():
            return requests.post(url, headers=headers, json=thread_data, allow_redirects=True)
        resp = await asyncio.to_thread(do_post)
        if resp.status_code in (200, 201):
            print(f"Posted thread to API: {thread_data.get('thread_title')}")
            return True
        else:
            print(f"Failed to post thread to API: {resp.status_code} {resp.text}")
            print(f"Request URL: {url}")
            print(f"Request Headers: {headers}")
            print(f"Request Payload: {thread_data}")
            return False 