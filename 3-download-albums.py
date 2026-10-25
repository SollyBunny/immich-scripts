#!/bin/env .venv/bin/python3

# Download album assets into directories.
#
# For each <album name>: <directory> pair in ALBUM_LINKS:
#   - download every asset in the album into the directory
#   - assets already present are left alone
#   - images larger than MAX_DIMENSION in any dimension are resized with magick
#   - regular files in the directory that no longer belong to the album are
#     removed (folders and symlinks are ignored)

import asyncio
import subprocess
from pathlib import Path

from immichpy.client.generated.models.asset_response_dto import AssetResponseDto
from immichpy.client.generated.models.asset_type_enum import AssetTypeEnum

from shared import Client

# Album name -> destination directory
ALBUM_LINKS = {
    "meta: Phone Backgrounds": "~/Shared/Phone Backgrounds",
}

MAX_DIMENSION = 1024


def resize(path: Path, asset: AssetResponseDto) -> bool:
    if asset.type != AssetTypeEnum.IMAGE:
        return False
    if path.is_symlink() or not path.exists():
        return False

    identify = subprocess.run(
        ["magick", "identify", "-format", "%w %h", str(path)],
        capture_output=True,
        text=True,
        check=False,
    )
    if identify.returncode != 0:
        print(f"  Could not read dimensions of {path.name}: {identify.stderr.strip()}")
        return False

    width, height = (int(dimension) for dimension in identify.stdout.split())
    if width <= MAX_DIMENSION and height <= MAX_DIMENSION:
        return False

    tmp = path.with_name(f"{path.stem}.tmp{path.suffix}")
    result = subprocess.run(
        [
            "magick",
            str(path),
            "-resize",
            f"{MAX_DIMENSION}x{MAX_DIMENSION}>",
            str(tmp),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        print(f"  Failed to resize {path.name}: {result.stderr.strip()}")
        tmp.unlink(missing_ok=True)
        return False

    _ = tmp.replace(path)
    print(f"  Resized {path.name} ({width}x{height})")
    return True


async def sync(client: Client, dest: Path, assets: list[AssetResponseDto]) -> None:
    dest.mkdir(parents=True, exist_ok=True)

    wanted: dict[str, AssetResponseDto] = {}
    for asset in assets:
        name = asset.original_file_name
        if name in wanted:
            print(f"  Duplicate name {name!r}, skipping {asset.id}")
            continue
        wanted[name] = asset

    downloaded = 0
    resized = 0
    for name, asset in wanted.items():
        target = dest / name
        if target.exists() or target.is_symlink():
            continue  # already present
        data = await client.assets.download_asset(asset.id)
        _ = target.write_bytes(data)
        print(f"  Downloaded {name}")
        downloaded += 1
        if resize(target, asset):
            resized += 1

    removed = 0
    for entry in dest.iterdir():
        if entry.is_dir() or entry.is_symlink():
            continue  # ignore folders and symlinks
        if entry.name in wanted:
            continue
        entry.unlink()
        removed += 1

    print(f"  {downloaded} downloaded, {resized} resized, {removed} removed in {dest}")


async def work(client: Client):
    for album_name, raw_dest in ALBUM_LINKS.items():
        album = await client.get_album(album_name)
        assets = await client.get_all_assets(album.id)
        dest = Path(raw_dest).expanduser()
        print(f"{album_name} -> {dest} ({len(assets)} assets)")
        await sync(client, dest, assets)


async def main():
    client = await Client.create()
    try:
        await work(client)
    finally:
        await client.close()


asyncio.run(main())
