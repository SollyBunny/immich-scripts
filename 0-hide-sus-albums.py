#!/bin/env .venv/bin/python3

# Makes all albums with "Sus" in them have the same thumbnail
# This thumbnail must be in all applicable albums

import asyncio
from uuid import UUID

from immichpy.client.generated.models.asset_visibility import AssetVisibility
from immichpy.client.generated.models.update_album_dto import UpdateAlbumDto
from immichpy.client.generated.models.update_asset_dto import UpdateAssetDto

from shared import Client, env

SUS_THUMBNAIL_UUID = UUID(env["SUS_THUMBNAIL_UUID"])


async def main():
    client = await Client.create()

    # Hide the thumbnail
    _ = await client.assets.update_asset(
        id=SUS_THUMBNAIL_UUID,
        update_asset_dto=UpdateAssetDto(visibility=AssetVisibility.HIDDEN),
    )

    albums = await client.albums.get_all_albums()
    for album in albums:
        if "Sus" not in album.album_name:
            continue
        if album.album_thumbnail_asset_id == SUS_THUMBNAIL_UUID:
            continue
        _ = await client.albums.update_album_info(
            id=album.id,
            update_album_dto=UpdateAlbumDto(
                albumThumbnailAssetId=SUS_THUMBNAIL_UUID
            ),
        )


asyncio.run(main())
