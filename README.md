# Music Organiser

A Python CLI that organizes `.mp3` files into this structure:

```text
<output>/<Artist Name>/<Album Name>/<Song Title>.mp3
```

It reads ID3 metadata first (`artist`, `album`, `title`) and falls back to filename parsing when metadata is missing.

## Features

- Organize one MP3 file or an entire directory recursively.
- Use metadata if available (`mutagen` optional dependency).
- Fallback filename parsing supports:
  - `Artist - Album - Song.mp3`
  - `Artist - Song.mp3`
- Safe duplicate handling (`Song (1).mp3`, `Song (2).mp3`, ...).
- Dry-run mode to preview moves.
- Optional metadata enrichment to fill **missing** tags from online databases:
  - MusicBrainz (primary)
  - iTunes Search API (fallback)

## Usage

```bash
python3 organize_mp3.py /path/to/music --output /path/to/organized
```

Preview changes without moving files:

```bash
python3 organize_mp3.py /path/to/music --dry-run
```

Force filename parsing (skip metadata):

```bash
python3 organize_mp3.py /path/to/music --prefer-filename
```

Fill missing metadata in output files after organizing:

```bash
python3 organize_mp3.py /path/to/music --output /path/to/organized --enrich-output-metadata
```

## Optional dependency

To read/write metadata, install `mutagen`:

```bash
pip install mutagen
```

Without it, organizing still works by parsing filenames, but metadata writing is skipped.
