#!/bin/env .venv/bin/python3

# Makes all albums with "Sus" in them have the same thumbnail
# This thumbnail must be in all applicable albums

import asyncio

from immichpy.client.generated.models.asset_visibility import AssetVisibility
from immichpy.client.generated.models.update_album_dto import UpdateAlbumDto
from immichpy.client.generated.models.update_asset_dto import UpdateAssetDto

from shared import META_ASSETS, Client


async def main():
    client = await Client.create()

    # Hide the thumbnail
    _ = await client.assets.update_asset(
        id=META_ASSETS["SUS_THUMBNAIL"],
        update_asset_dto=UpdateAssetDto(visibility=AssetVisibility.HIDDEN)
    )

    albums = await client.albums.get_all_albums()
    for album in albums:
        if "Sus" not in album.album_name:
            continue
        if album.album_thumbnail_asset_id == META_ASSETS["SUS_THUMBNAIL"]:
            continue
        _ = await client.albums.update_album_info(
            id=album.id,
            update_album_dto=UpdateAlbumDto(
                albumThumbnailAssetId=META_ASSETS["SUS_THUMBNAIL"]
            ),
        )


asyncio.run(main())
