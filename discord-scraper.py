#!/usr/bin/env python3

# Discord -> Immich media scraper bot.
#
# Reads config.json:
#   {
#     "token": "<discord bot token>",
#     "scan": [
#       {
#         "album": "<immich album name>",
#         "prefix": "<filename prefix>",
#         "channel": "<channel snowflake>"
#       }
#     ]
#   }
#
# For every scan target it looks at the newest MESSAGE_LIMIT messages of the
# channel (or all history if --full is passed). Attachments are downloaded and
# uploaded to Immich directly. Assets already present (by name or checksum)
# cause the rest of a batch to be skipped unless --full is used.
#
# Pass --full to walk the entire channel history and don't stop at duplicates.

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import os
import sys
from datetime import UTC, datetime
from typing import TypedDict, cast

import aiohttp
import discord
from immichpy.client.generated.models.bulk_ids_dto import BulkIdsDto
from immichpy.client.generated.models.create_album_dto import CreateAlbumDto

from shared import Client

MESSAGE_LIMIT = 100
FULL = "--full" in sys.argv[1:]

SCANNING_STATUS = "Scanning media!"

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.json")


class ScanTarget(TypedDict):
    album: str
    prefix: str
    channel: str


class Config(TypedDict):
    token: str
    scan: list[ScanTarget]


class AssetItem(TypedDict):
    album: str
    url: str
    name: str
    originalName: str
    createdAt: int


def item_time(created_at_ms: int) -> datetime:
    return datetime.fromtimestamp(created_at_ms / 1000, tz=UTC)


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


async def process_batch(
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

        created_at = item_time(item["createdAt"])
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


class DiscordScraper(discord.Client):
    def __init__(self, immich_client: Client, scan_targets: list[ScanTarget]):
        intents = discord.Intents.default()
        intents.guilds = True
        intents.messages = True
        intents.message_content = True
        super().__init__(intents=intents)
        self.immich_client: Client = immich_client
        self.scan_targets: list[ScanTarget] = scan_targets

    async def on_ready(self):
        print(f"Logged in as {self.user}")
        await self.set_status(SCANNING_STATUS, "👀")
        try:
            await self.scan_all()
        finally:
            await self.close()

    async def set_status(self, status: str, emoji: str):
        if self.user:
            activity = discord.Activity(
                type=discord.ActivityType.watching, name=f"{status} {emoji}"
            )
            await self.change_presence(activity=activity)

    async def scan_target(self, target: ScanTarget) -> list[AssetItem]:
        channel_id = int(target["channel"])
        channel = self.get_channel(channel_id)
        if channel is None:
            channel = await self.fetch_channel(channel_id)
        if not isinstance(channel, discord.TextChannel):
            raise TypeError("Channel not found or is not a text channel")
        assets: list[AssetItem] = []
        before = None

        while True:
            messages = [
                message
                async for message in channel.history(
                    limit=MESSAGE_LIMIT,
                    before=before,
                    oldest_first=False,
                )
            ]

            if not messages:
                break

            # Newest first for early duplicate detection
            ordered = sorted(messages, key=lambda m: m.created_at, reverse=True)
            for message in ordered:
                for attachment in message.attachments:
                    assets.append(
                        {
                            "album": target["album"],
                            "url": attachment.url,
                            "name": target["prefix"] + attachment.filename,
                            "originalName": attachment.filename,
                            "createdAt": int(message.created_at.timestamp() * 1000),
                        }
                    )

            if not FULL or len(messages) < MESSAGE_LIMIT:
                break
            before = ordered[-1]

        return assets

    async def scan_all(self):
        async with aiohttp.ClientSession() as http_session:
            for target in self.scan_targets:
                assets = await self.scan_target(target)
                print(
                    f"Scanned {len(assets)} attachment(s) for album {target['album']}"
                )
                if not assets:
                    continue
                await process_batch(self.immich_client, http_session, assets, FULL)

async def main(config: Config):
    immich_client = await Client.create()
    try:
        client = DiscordScraper(immich_client, config["scan"])
        await client.start(config["token"])
    finally:
        await immich_client.close()


with open(CONFIG_PATH, "r") as f:
    config = cast(Config, json.load(f))

asyncio.run(main(config))
