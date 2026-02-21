#!/usr/bin/env python3
"""Organize MP3 files into Artist/Album folders using metadata or filename parsing."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

try:
    from mutagen.easyid3 import EasyID3  # type: ignore
except ImportError:  # optional dependency
    EasyID3 = None


UNKNOWN_ARTIST = "Unknown Artist"
UNKNOWN_ALBUM = "Unknown Album"
UNKNOWN_TITLE = "Unknown Title"


@dataclass
class TrackInfo:
    artist: str
    album: str
    title: str


@dataclass
class OnlineMetadata:
    artist: str | None = None
    album: str | None = None
    title: str | None = None
    year: str | None = None
    genre: str | None = None
    source: str | None = None


def clean_name(value: str, fallback: str) -> str:
    cleaned = value.strip().strip(".")
    cleaned = re.sub(r"[\\/:*?\"<>|]", "_", cleaned)
    return cleaned or fallback


def parse_filename(file_path: Path) -> TrackInfo:
    stem = file_path.stem
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
        destination.mkdir(parents=True, exist_ok=True)
    shutil.move(str(file_path), str(target))

    return target


def fetch_json(url: str, headers: dict[str, str] | None = None, timeout: int = 8) -> dict | None:
    request = urllib.request.Request(url, headers=headers or {"User-Agent": "music-organiser/1.0"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except Exception:
        return None


def query_musicbrainz_metadata(artist: str, title: str) -> OnlineMetadata | None:
    query = urllib.parse.quote_plus(f'artist:"{artist}" recording:"{title}"')
    url = f"https://musicbrainz.org/ws/2/recording?query={query}&fmt=json&limit=5"
    payload = fetch_json(url, headers={"User-Agent": "music-organiser/1.0 (metadata-fill)"})
    if not payload:
        return None

    recordings = payload.get("recordings", [])
    if not recordings:
        return None

    best = recordings[0]
    artist_credit = best.get("artist-credit", [])
    artist_name = artist
    if artist_credit and isinstance(artist_credit[0], dict):
        artist_name = artist_credit[0].get("name", artist)

    releases = best.get("releases", [])
    album_name = releases[0].get("title") if releases else None
    year = None
    if releases:
        date_value = releases[0].get("date", "")
        year = date_value[:4] if len(date_value) >= 4 else None

    tags = best.get("tags", [])
    genre = tags[0].get("name") if tags and isinstance(tags[0], dict) else None

    return OnlineMetadata(
        artist=clean_name(artist_name, artist),
        album=clean_name(album_name, UNKNOWN_ALBUM) if album_name else None,
        title=clean_name(best.get("title", title), title),
        year=year,
        genre=genre,
        source="MusicBrainz",
    )


def query_itunes_metadata(artist: str, title: str) -> OnlineMetadata | None:
    query = urllib.parse.quote_plus(f"{artist} {title}".strip())
    url = f"https://itunes.apple.com/search?term={query}&entity=song&limit=5"
    payload = fetch_json(url)
    if not payload:
        return None

    results = payload.get("results", [])
    if not results:
        return None

    normalized_artist = artist.casefold()
    normalized_title = title.casefold()

    def match_score(candidate: dict[str, str]) -> int:
        score = 0
        candidate_artist = candidate.get("artistName", "").casefold()
        candidate_title = candidate.get("trackName", "").casefold()
        if candidate_artist == normalized_artist:
            score += 2
        if candidate_title == normalized_title:
            score += 2
        if normalized_artist in candidate_artist:
            score += 1
        if normalized_title in candidate_title:
            score += 1
        return score

    best = max(results, key=match_score)
    release_date = best.get("releaseDate", "")
    year = release_date[:4] if len(release_date) >= 4 else None

    return OnlineMetadata(
        artist=clean_name(best.get("artistName", artist), artist),
        album=clean_name(best.get("collectionName", UNKNOWN_ALBUM), UNKNOWN_ALBUM),
        title=clean_name(best.get("trackName", title), title),
        year=year,
        genre=best.get("primaryGenreName"),
        source="iTunes",
    )


def query_online_metadata(artist: str, title: str) -> OnlineMetadata | None:
    for resolver in (query_musicbrainz_metadata, query_itunes_metadata):
        result = resolver(artist, title)
        if result:
            return result
    return None


def value_is_missing(value: str | None, unknown_value: str | None = None) -> bool:
    if value is None:
        return True
    stripped = value.strip()
    if not stripped:
        return True
    if unknown_value and stripped.casefold() == unknown_value.casefold():
        return True
    return False


def infer_track_from_path(mp3: Path, output_root: Path) -> TrackInfo:
    fallback = parse_filename(mp3)
    try:
        relative = mp3.relative_to(output_root)
    except ValueError:
        return fallback

    parts = relative.parts
    artist = parts[0] if len(parts) >= 3 else fallback.artist
    album = parts[1] if len(parts) >= 3 else fallback.album
    title = mp3.stem
    return TrackInfo(
        artist=clean_name(artist, fallback.artist),
        album=clean_name(album, fallback.album),
        title=clean_name(title, fallback.title),
    )



def relocate_file_from_unknown_folder(
    file_path: Path,
    output_root: Path,
    inferred: TrackInfo,
    artist: str,
    album: str,
    title: str,
    dry_run: bool,
) -> Path:
    needs_relocation = inferred.album == UNKNOWN_ALBUM or inferred.artist == UNKNOWN_ARTIST
    if not needs_relocation:
        return file_path

    destination = output_root / clean_name(artist, UNKNOWN_ARTIST) / clean_name(album, UNKNOWN_ALBUM)
    target = destination / f"{clean_name(title, file_path.stem)}{file_path.suffix.lower()}"
    target = unique_destination(target)

    if dry_run:
        print(f"Would relocate: {file_path} -> {target}")
        return target

    destination.mkdir(parents=True, exist_ok=True)
    shutil.move(str(file_path), str(target))
    return target

def enrich_output_metadata(output_root: Path, dry_run: bool = False) -> None:
    if EasyID3 is None:
        print("Skipping metadata enrichment: install 'mutagen' to write ID3 tags.")
        return

    for mp3 in iter_mp3_files(output_root):
        inferred = infer_track_from_path(mp3, output_root)

        try:
            tags = EasyID3(str(mp3))
        except Exception:
            tags = EasyID3()
            if not dry_run:
                tags.save(str(mp3))
            tags = EasyID3(str(mp3)) if not dry_run else EasyID3()

        current_artist = tags.get("artist", [""])[0] if tags else ""
        current_album = tags.get("album", [""])[0] if tags else ""
        current_title = tags.get("title", [""])[0] if tags else ""

        query_artist = current_artist if not value_is_missing(current_artist, UNKNOWN_ARTIST) else inferred.artist
        query_title = current_title if not value_is_missing(current_title, UNKNOWN_TITLE) else inferred.title

        online = query_online_metadata(query_artist, query_title)
        if online is None:
            print(f"No online metadata found for: {mp3}")
            continue

        updates: list[str] = []

        if value_is_missing(current_artist, UNKNOWN_ARTIST) and online.artist:
            tags["artist"] = [online.artist]
            updates.append(f"artist='{online.artist}'")
        if value_is_missing(current_album, UNKNOWN_ALBUM) and online.album:
            tags["album"] = [online.album]
            updates.append(f"album='{online.album}'")
        if value_is_missing(current_title, UNKNOWN_TITLE) and online.title:
            tags["title"] = [online.title]
            updates.append(f"title='{online.title}'")

        current_date = tags.get("date", [""])[0] if tags else ""
        if value_is_missing(current_date) and online.year:
            tags["date"] = [online.year]
            updates.append(f"date='{online.year}'")

        current_genre = tags.get("genre", [""])[0] if tags else ""
        if value_is_missing(current_genre) and online.genre:
            tags["genre"] = [online.genre]
            updates.append(f"genre='{online.genre}'")

        if not updates:
            print(f"No missing metadata to fill: {mp3}")
            continue

        final_artist = tags.get("artist", [inferred.artist])[0]
        final_album = tags.get("album", [inferred.album])[0]
        final_title = tags.get("title", [inferred.title])[0]

        if dry_run:
            print(f"Would fill ({online.source}) {mp3}: {', '.join(updates)}")
            relocate_file_from_unknown_folder(
                mp3,
                output_root,
                inferred,
                final_artist,
                final_album,
                final_title,
                dry_run=True,
            )
            continue

        tags.save(str(mp3))
        relocated_path = relocate_file_from_unknown_folder(
            mp3,
            output_root,
            inferred,
            final_artist,
            final_album,
            final_title,
            dry_run=False,
        )
        print(f"Filled ({online.source}) {relocated_path}: {', '.join(updates)}")


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
    parser.add_argument(
        "--enrich-output-metadata",
        action="store_true",
        help="After organizing, fill missing ID3 tags from MusicBrainz/iTunes in output songs",
    )
    parser.add_argument(
        "--metadata-only",
        action="store_true",
        help="Do not move files; only scan the source folder recursively and fill missing metadata",
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

    if args.metadata_only:
        if not args.enrich_output_metadata:
            print("Notice: --metadata-only was set; enabling --enrich-output-metadata.")
        enrich_output_metadata(args.source, dry_run=args.dry_run)
        return 0

    if EasyID3 is None and not args.prefer_filename:
        print("Notice: 'mutagen' is not installed; falling back to filename parsing.")

    for mp3 in files:
        info = get_track_info(mp3, prefer_filename=args.prefer_filename)
        destination = move_file(mp3, args.output, info, dry_run=args.dry_run)
        action = "Would move" if args.dry_run else "Moved"
        print(f"{action}: {mp3} -> {destination}")

    if args.enrich_output_metadata:
        enrich_output_metadata(args.output, dry_run=args.dry_run)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
