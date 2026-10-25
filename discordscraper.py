#!/bin/env .venv/bin/python3

# Immich importer driven by discordscraper.js.
#
# Reads one JSON array per line from stdin, each item being:
#
#   { "album": str, "url": str, "name": str, "originalName": str, "createdAt": int }
#
# Items arrive newest first. For every item the album is checked for an asset
# with a matching file name -- either the prefixed name or the original
# attachment name -- or a matching base64 SHA1 checksum: if any exists everything
# older is assumed to have been imported already and the rest of the batch is
# skipped, otherwise the file is downloaded from its url and uploaded to the
# album under the given (prefixed) name.
#
# createdAt is the source message timestamp (milliseconds since the epoch) and
# is used as the uploaded asset's created/modified date.
#
# Pass --full to keep going after finding a duplicate instead of stopping the
# batch at the first one. This pairs with the bot's --full channel-wide scan.

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import sys
from datetime import UTC, datetime
from typing import TypedDict, cast

import aiohttp
from immichpy.client.generated.models.bulk_ids_dto import BulkIdsDto
from immichpy.client.generated.models.create_album_dto import CreateAlbumDto

from shared import Client

FULL = "--full" in sys.argv[1:]


class AssetItem(TypedDict):
    album: str
    url: str
    name: str
    originalName: str
    createdAt: int


def item_time(item: AssetItem) -> datetime:
    created_at = item.get("createdAt")
    return datetime.fromtimestamp(created_at / 1000, tz=UTC)


def sha1_checksum(data: bytes) -> str:
    return base64.b64encode(hashlib.sha1(data).digest()).decode()


async def download(session: aiohttp.ClientSession, url: str) -> bytes:
    async with session.get(url) as response:
        response.raise_for_status()
        return await response.read()


async def get_album(client: Client, name: str):
    try:
        return await client.get_album(name)
    except ValueError:
        print(f"Creating album {name}")
        album = await client.albums.create_album(CreateAlbumDto(albumName=name))
        client.get_all_albums_cached.cache_clear()
        return album


async def process(
    client: Client, session: aiohttp.ClientSession, items: list[AssetItem], full: bool
) -> None:
    if not items:
        return

    album_name = items[0]["album"]
    album = await get_album(client, album_name)
    album_assets = await client.get_all_assets(album.id)

    existing_names = {asset.original_file_name: asset.id for asset in album_assets}
    existing_checksums = {asset.checksum: asset.id for asset in album_assets}

    uploaded = 0
    for item in items:
        name = item["name"]
        original_name = item["originalName"]
        found = existing_names.get(name)
        if found is None:
            found = existing_names.get(original_name)
        if found is not None:
            print(f"Already have {name} ({found})")
            if not full:
                print(f"Skipping the rest of {album_name}")
                break
            continue

        data = await download(session, item["url"])
        checksum = sha1_checksum(data)
        found = existing_checksums.get(checksum)
        if found is not None:
            print(f"Already have content of {name} ({found})")
            if not full:
                print(f"Skipping the rest of {album_name}")
                break
            continue

        created_at = item_time(item)
        asset = await client.assets.upload_asset(
            asset_data=data,
            file_created_at=created_at,
            file_modified_at=created_at,
            filename=name,
            x_immich_checksum=checksum,
        )
        _ = await client.albums.add_assets_to_album(
            album.id, BulkIdsDto(ids=[asset.id])
        )
        existing_names[name] = asset.id
        existing_checksums[checksum] = asset.id
        uploaded += 1
        print(f"Uploaded {name} to {album_name}")

    print(f"{uploaded} uploaded to {album_name}")


async def main() -> None:
    client = await Client.create()
    async with aiohttp.ClientSession() as session:
        while True:
            line = await asyncio.to_thread(sys.stdin.readline)
            if not line:
                break  # stdin closed, bot is gone
            line = line.strip()
            if not line:
                continue

            try:
                items = cast(list[AssetItem], json.loads(line))
            except json.JSONDecodeError as error:
                print(f"Invalid JSON line: {error}", file=sys.stderr)
                continue

            try:
                await process(client, session, items, FULL)
            except Exception as error:
                print(f"Failed to process batch: {error}", file=sys.stderr)


asyncio.run(main())
