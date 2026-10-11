#!/bin/env .venv/bin/python3

# If an item is in no albums, add it to the appropriate album
# Remove assets in albums from source albums when in both source and non source albums
# Detect duplicate non source albums, non meta albums

import asyncio
import re
import sys

from immichpy.client.generated.models.album_response_dto import AlbumResponseDto
from immichpy.client.generated.models.asset_response_dto import AssetResponseDto
from immichpy.client.generated.models.bulk_ids_dto import BulkIdsDto

from shared import META_ASSETS, META_PREFIX, SRC_PREFIX, Client


async def main():
    client = await Client.create()

    regex_filters: dict[AlbumResponseDto, re.Pattern[str]] = {}
    regex_filters[await client.get_album("src: Screenshots")] = re.compile(
        r"^.*?screen.+?$", re.IGNORECASE
    )
    regex_filters[await client.get_album("src: Whatsapp")] = re.compile(
        r"^\w+?-.+?-WA.+?$"
    )
    regex_filters[await client.get_album("src: Signal")] = re.compile(r"^signal-.+?$")
    regex_filters[await client.get_album("src: Discord")] = re.compile(r"^discord-.+?$")
    unsorted_album = await client.get_album("src: Unsorted")

    asset_albums: dict[AssetResponseDto, list[AlbumResponseDto]] = {}
    for asset in await client.get_all_assets(None, True):
        asset_albums[asset] = []
    for album in await client.get_all_albums_cached():
        assets = await client.get_all_assets(album.id)
        for asset in assets:
            if asset.id in META_ASSETS.values():
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
            album_matches = [
                album
                for album, regex in regex_filters.items()
                if re.match(regex, asset.original_file_name)
            ]
            if len(album_matches) > 1:
                print(
                    f"{asset.id} matched multiple source albums: {', '.join(i.album_name for i in album_matches)}"
                )
                was_problem = True
                continue
            album_match = album_matches[0] if album_matches else unsorted_album
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
