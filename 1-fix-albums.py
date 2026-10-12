#!/bin/env .venv/bin/python3

# If an item is in no albums, add it to the appropriate album
# Remove assets in albums from source albums when in both source and non source albums
# Detect duplicate non source albums, non meta albums

import asyncio
import re
import sys

from immichpy.client.generated.models.album_response_dto import AlbumResponseDto
from immichpy.client.generated.models.asset_response_dto import AssetResponseDto
from immichpy.client.generated.models.asset_visibility import AssetVisibility
from immichpy.client.generated.models.bulk_ids_dto import BulkIdsDto

from shared import META_PREFIX, SRC_PREFIX, Client


async def main():
    client = await Client.create()

    regex_filters: dict[AlbumResponseDto, re.Pattern[str]] = {}
    async def add_regex_filter(album_name: str, regex: str, regex_flags: re.RegexFlag = re.NOFLAG):
        regex_filters[await client.get_album(album_name)] = re.compile(regex, regex_flags)

    # Order matters
    await add_regex_filter("src: Discord", r"^discord-.+?$")
    await add_regex_filter("src: Screenshots", r"^.*?screen.+?$", re.IGNORECASE)
    await add_regex_filter("src: Whatsapp", r"^\w+?-.+?-WA.+?$")
    await add_regex_filter("src: Signal", r"^signal-.+?$")
    unsorted_album = await client.get_album("src: Unsorted")

    asset_albums: dict[AssetResponseDto, list[AlbumResponseDto]] = {}
    for asset in await client.get_all_assets(None, True):
        asset_albums[asset] = []
    for album in await client.get_all_albums_cached():
        assets = await client.get_all_assets(album.id)
        for asset in assets:
            if asset.visibility == AssetVisibility.HIDDEN or asset.visibility == AssetVisibility.LOCKED:
                continue
            if asset not in asset_albums:
                asset_albums[asset] = []
            asset_albums[asset].append(album)

    to_remove: dict[AlbumResponseDto, list[AssetResponseDto]] = {}
    to_add: dict[AlbumResponseDto, list[AssetResponseDto]] = {}
    for album in await client.get_all_albums_cached():
        to_remove[album] = []
        to_add[album] = []

    was_problem = False
    for asset, albums in asset_albums.items():
        non_source_meta_albums = [
            i.album_name for i in albums if not i.album_name.startswith(SRC_PREFIX) and not i.album_name.startswith(META_PREFIX)
        ]
        if len(non_source_meta_albums) > 0:
            if len(non_source_meta_albums) > 1:
                print(
                    f"{asset.id} in multiple non source non meta albums: {', '.join([i.album_name for i in albums])}"
                )
                was_problem = True
                continue
            for album in albums:
                if album.album_name.startswith(SRC_PREFIX):
                    to_remove[album].append(asset)
        else:
            album_match = unsorted_album
            for album, regex in regex_filters.items():
                if re.match(regex, asset.original_file_name):
                    album_match = album
                    break
            if album_match not in albums:
                to_add[album_match].append(asset)
            for album in albums:
                if album.album_name.startswith(SRC_PREFIX) and album != album_match:
                    to_remove[album].append(asset)

    if was_problem:
        sys.exit(1)

    for album, assets in to_add.items():
        if len(assets) == 0:
            continue
        print(f"Added {len(assets)} to {album.album_name}")
        _ = await client.albums.add_assets_to_album(
            album.id, BulkIdsDto(ids=[i.id for i in assets])
        )

    for album, assets in to_remove.items():
        if len(assets) == 0:
            continue
        print(f"Removed {len(assets)} from {album.album_name}")
        _ = await client.albums.remove_asset_from_album(
            album.id, BulkIdsDto(ids=[i.id for i in assets])
        )


asyncio.run(main())
