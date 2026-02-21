# Music Organiser

A simple Python CLI that organizes `.mp3` files into this structure:

```text
<output>/<Artist Name>/<Album Name>/<Song Title>.mp3
```

It tries to read ID3 metadata first (`artist`, `album`, `title`) and, if unavailable, falls back to filename parsing.

## Features

- Organize one MP3 file or an entire directory recursively.
- Use metadata if available (`mutagen` optional dependency).
- Fallback filename parsing supports:
  - `Artist - Album - Song.mp3`
  - `Artist - Song.mp3`
- Safe duplicate handling (`Song (1).mp3`, `Song (2).mp3`, ...).
- Dry-run mode to preview moves.

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

## Optional dependency

To read metadata, install `mutagen`:

```bash
pip install mutagen
```

Without it, the tool still works by parsing filenames.
