#!/bin/env .venv/bin/python3

# Make sure all assets have correct visibility
# Ignore HIDDEN / LOCKED
# Rest should be TIMELINE
# Apart from those in sus albums

import asyncio

from immichpy.client.generated.models.asset_bulk_update_dto import AssetBulkUpdateDto
from immichpy.client.generated.models.asset_response_dto import AssetResponseDto
from immichpy.client.generated.models.asset_visibility import AssetVisibility

from shared import SUS_PREFIX, Client


async def work(client: Client):
    client = await Client.create()

    albums = await client.albums.get_all_albums()
    to_archive: list[AssetResponseDto] = []
    to_unarchive: list[AssetResponseDto] = []
    for album in albums:
        assets = await client.get_all_assets(album.id)
        if album.album_name.startswith(SUS_PREFIX):
            assets = list(
                filter(lambda a: a.visibility == AssetVisibility.TIMELINE, assets)
            )
            print(
                f"Archiving {len(assets)}/{album.asset_count} assets in {album.album_name}"
            )
            to_archive.extend(assets)
        else:
            assets = list(
                filter(lambda a: a.visibility == AssetVisibility.ARCHIVE, assets)
            )
            print(
                f"Unarchiving {len(assets)}/{album.asset_count} assets in {album.album_name}"
            )
            to_unarchive.extend(assets)

    print(f"Archiving {len(to_archive)} assets")
    await client.assets.update_assets(
        AssetBulkUpdateDto(
            ids=[asset.id for asset in to_archive],
            visibility=AssetVisibility.ARCHIVE,
        )
    )

    print(f"Unarchiving {len(to_unarchive)} assets")
    await client.assets.update_assets(
        AssetBulkUpdateDto(
            ids=[asset.id for asset in to_unarchive],
            visibility=AssetVisibility.TIMELINE,
        )
    )


async def main():
    client = await Client.create()
    try:
        await work(client)
    finally:
        await client.close()


asyncio.run(main())
