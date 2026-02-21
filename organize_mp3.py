#!/usr/bin/env python3
"""Organize MP3 files into Artist/Album folders using metadata or filename parsing."""

from __future__ import annotations

import argparse
import re
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

try:
    from mutagen.easyid3 import EasyID3  # type: ignore
except ImportError:  # optional dependency
    EasyID3 = None


UNKNOWN_ARTIST = "Unknown Artist"
UNKNOWN_ALBUM = "Unknown Album"


@dataclass
class TrackInfo:
    artist: str
    album: str
    title: str


def clean_name(value: str, fallback: str) -> str:
    cleaned = value.strip().strip(".")
    cleaned = re.sub(r"[\\/:*?\"<>|]", "_", cleaned)
    return cleaned or fallback


def parse_filename(file_path: Path) -> TrackInfo:
    stem = file_path.stem

    # Common patterns: "Artist - Album - Title" or "Artist - Title"
    parts = [part.strip() for part in stem.split("-")]
    if len(parts) >= 3:
        artist, album = parts[0], parts[1]
        title = "-".join(parts[2:]).strip()
    elif len(parts) == 2:
        artist, title = parts
        album = UNKNOWN_ALBUM
    else:
        artist = UNKNOWN_ARTIST
        album = UNKNOWN_ALBUM
        title = stem

    return TrackInfo(
        artist=clean_name(artist, UNKNOWN_ARTIST),
        album=clean_name(album, UNKNOWN_ALBUM),
        title=clean_name(title, stem),
    )


def parse_metadata(file_path: Path) -> TrackInfo | None:
    if EasyID3 is None:
        return None

    try:
        tags = EasyID3(str(file_path))
    except Exception:
        return None

    artist = tags.get("artist", [UNKNOWN_ARTIST])[0]
    album = tags.get("album", [UNKNOWN_ALBUM])[0]
    title = tags.get("title", [file_path.stem])[0]

    return TrackInfo(
        artist=clean_name(artist, UNKNOWN_ARTIST),
        album=clean_name(album, UNKNOWN_ALBUM),
        title=clean_name(title, file_path.stem),
    )


def get_track_info(file_path: Path, prefer_filename: bool = False) -> TrackInfo:
    if not prefer_filename:
        metadata = parse_metadata(file_path)
        if metadata:
            return metadata

    return parse_filename(file_path)


def iter_mp3_files(path: Path) -> Iterable[Path]:
    if path.is_file() and path.suffix.lower() == ".mp3":
        yield path
    elif path.is_dir():
        for file_path in path.rglob("*.mp3"):
            if file_path.is_file():
                yield file_path


def unique_destination(path: Path) -> Path:
    if not path.exists():
        return path

    counter = 1
    while True:
        candidate = path.with_name(f"{path.stem} ({counter}){path.suffix}")
        if not candidate.exists():
            return candidate
        counter += 1


def move_file(file_path: Path, destination_root: Path, info: TrackInfo, dry_run: bool) -> Path:
    artist_dir = destination_root / info.artist
    album_dir = artist_dir / info.album
    album_dir.mkdir(parents=True, exist_ok=True)

    target = album_dir / f"{info.title}{file_path.suffix.lower()}"
    target = unique_destination(target)

    if not dry_run:
        shutil.move(str(file_path), str(target))

    return target


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Organize MP3 files into Artist/Album folders. "
            "Reads ID3 metadata when available and falls back to parsing file names."
        )
    )
    parser.add_argument("source", type=Path, help="MP3 file or folder to organize")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("organized_music"),
        help="Destination root folder (default: ./organized_music)",
    )
    parser.add_argument(
        "--prefer-filename",
        action="store_true",
        help="Skip metadata and always parse artist/album/title from filename",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print actions without moving files",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()

    if not args.source.exists():
        print(f"Error: source path '{args.source}' does not exist.", file=sys.stderr)
        return 1

    files = list(iter_mp3_files(args.source))
    if not files:
        print("No MP3 files found.")
        return 0

    if EasyID3 is None and not args.prefer_filename:
        print("Notice: 'mutagen' is not installed; falling back to filename parsing.")

    for mp3 in files:
        info = get_track_info(mp3, prefer_filename=args.prefer_filename)
        destination = move_file(mp3, args.output, info, dry_run=args.dry_run)
        action = "Would move" if args.dry_run else "Moved"
        print(f"{action}: {mp3} -> {destination}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
