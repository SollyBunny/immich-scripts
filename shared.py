from __future__ import annotations

import asyncio
import atexit
import sys
from typing import Final, Protocol, TypeVar
from uuid import UUID

from immichpy import AsyncClient
from immichpy.client.generated.models.album_response_dto import AlbumResponseDto
from immichpy.client.generated.models.asset_response_dto import AssetResponseDto
from immichpy.client.generated.models.metadata_search_dto import MetadataSearchDto

SOURCE_ALBUMS: Final = ("Screenshots", "Whatsapp", "Signal", "Discord", "Unsorted")
META_ASSETS: Final = [
    UUID("8987ead8-6a56-4694-9d8c-007846e39505"),
]


class HasIdUUID(Protocol):
    id: UUID


T = TypeVar("T", bound=HasIdUUID)


def addIdEqAndHash(cls: type[T]):
    cls.__eq__ = lambda self, other: isinstance(other, cls) and self.id == other.id
    cls.__hash__ = lambda self: hash(self.id)


addIdEqAndHash(AssetResponseDto)
addIdEqAndHash(AlbumResponseDto)


def readEnv():
    out: dict[str, str] = {}
    with open(".env") as file:
        lines = file.readlines()
    for line in lines:
        line = line.strip(" \n")
        if not line:
            continue
        key, _, value = line.partition("=")
        out[key] = value
    return out


env = readEnv()
if "IMMICH_API_KEY" not in env:
    sys.exit("Missing IMMICH_API_KEY in .env")
if "IMMICH_URL" not in env:
    sys.exit("Missing IMMICH_URL in .env")


class Client(AsyncClient):
    @classmethod
    async def create(cls) -> Client:
        client = cls(
            api_key=env["IMMICH_API_KEY"],
            base_url=env["IMMICH_URL"],
        )
        try:
            info = await client.server.get_about_info()
        finally:
            await client.close()
        _ = atexit.register(lambda: asyncio.run(client.close()))
        print(f"Connected to client {info.build_image}")
        return client

    async def get_all_assets(
        self,
        albumId: UUID | None = None,
        notInAlbum: bool = False,
    ) -> list[AssetResponseDto]:
        assets: list[AssetResponseDto] = []

        search = MetadataSearchDto(
            page=1,
            size=1000,
        )
        if albumId is not None:
            search.album_ids = [albumId]
        if notInAlbum:
            search.is_not_in_album = True

        while True:
            result = await self.search.search_assets(search)

            items = result.assets.items
            if not items:
                break

            assets.extend(items)

            if not result.assets.next_page:
                break

            search.page = int(result.assets.next_page)

        return assets
