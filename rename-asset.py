#!/bin/env .venv/bin/python3

import asyncio
import re
import sys
from uuid import UUID

from immichpy.client.generated.models.asset_bulk_delete_dto import AssetBulkDeleteDto

from shared import Client

SUS_THUMBNAIL_UUID = UUID("8987ead8-6a56-4694-9d8c-007846e39505")


def input_uuid():
    inp = input("Enter UUID/link: ")
    # http://localhost:2283/albums/9e266011-252c-4a17-bf47-112b59aa0002/photos/4696e3e4-3fac-4b8a-8af5-d107044db1da
    # http://localhost:2283/photos/4696e3e4-3fac-4b8a-8af5-d107044db1da
    # 4696e3e4-3fac-4b8a-8af5-d107044db1da
    match = re.search(
        r"([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})$",
        inp,
    )
    if match:
        return UUID(match.group(1))
    print("No UUID found in input")
    sys.exit(1)


async def main():
    print("Note this doesn't support copying metadata like albums")
    client = await Client.create()

    id = input_uuid()

    asset = await client.assets.get_asset_info(id)
    if not asset:
        print(f"No asset with UUID {id}")
        sys.exit(1)

    print(f"Old file name: {asset.original_file_name}")
    newName = input("New name: ")

    assetData = await client.assets.download_asset(id)
    assetNew = await client.assets.upload_asset(
        asset_data=assetData,
        file_created_at=asset.file_created_at,
        file_modified_at=asset.file_modified_at,
        filename=newName,
        is_favorite=asset.is_favorite,
        live_photo_video_id=UUID(asset.live_photo_video_id)
        if asset.live_photo_video_id
        else None,
        visibility=asset.visibility,
    )

    print(f"New UUID: {assetNew.id}")

    _ = input("Press enter to delete old asset")
    await client.assets.delete_assets(AssetBulkDeleteDto(ids=[id]))


asyncio.run(main())
