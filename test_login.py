#!/usr/bin/env python3
import asyncio
import aiohttp
from bot_config import ACCESS_TOKEN, HOMESERVER, USER_ID

async def test_matrix_connection():
    """Test Matrix server connectivity and access token validity."""
    print(f"Testing connection to: {HOMESERVER}")
    print(f"User ID: {USER_ID}")
    print(f"Access token length: {len(ACCESS_TOKEN) if ACCESS_TOKEN else 0}")
    print()
    
    # Test 1: Server connectivity
    print("1. Testing server connectivity...")
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{HOMESERVER}/_matrix/client/versions") as response:
                print(f"   Status: {response.status}")
                if response.status == 200:
                    data = await response.json()
                    print(f"   Versions: {data.get('versions', [])[:3]}...")
                else:
                    print(f"   Error: {await response.text()}")
    except Exception as e:
        print(f"   Connection error: {e}")
        return
    
    print()
    
    # Test 2: Access token validity
    print("2. Testing access token...")
    headers = {'Authorization': f'Bearer {ACCESS_TOKEN}'}
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{HOMESERVER}/_matrix/client/v3/account/whoami", headers=headers) as response:
                print(f"   Status: {response.status}")
                text = await response.text()
                print(f"   Response: {text}")
                
                if response.status == 200:
                    data = await response.json()
                    print(f"   Authenticated as: {data.get('user_id')}")
                elif response.status == 401:
                    print("   ❌ Access token is invalid or expired!")
                else:
                    print(f"   ❌ Unexpected error: {response.status}")
    except Exception as e:
        print(f"   Request error: {e}")

if __name__ == "__main__":
    asyncio.run(test_matrix_connection()) 