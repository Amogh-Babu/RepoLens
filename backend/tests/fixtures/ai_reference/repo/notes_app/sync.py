import asyncio

import httpx

from notes_app.config import SYNC_URL
from notes_app.storage import NoteStore


async def push_notes(owner, client=None):
    store = NoteStore()
    notes = store.list_for(owner)
    own_client = client is None
    client = client or httpx.AsyncClient(timeout=10)
    try:
        response = await client.post(SYNC_URL, json={"owner": owner, "notes": notes})
        response.raise_for_status()
        return len(notes)
    finally:
        if own_client:
            await client.aclose()


async def push_all(owners):
    counts = await asyncio.gather(*(push_notes(owner) for owner in owners))
    return dict(zip(owners, counts))
