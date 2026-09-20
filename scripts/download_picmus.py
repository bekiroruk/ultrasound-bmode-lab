"""Download and integrity-check the public PICMUS in-vivo carotid dataset."""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
from urllib.request import urlopen


URL = "https://zenodo.org/api/records/20261898/files/PICMUS_carotid_cross.uff/content"
EXPECTED_SIZE = 76_705_680
EXPECTED_MD5 = "be81dfc519d3f7c642ff60d85642f311"


def file_md5(path: Path) -> str:
    digest = hashlib.md5(usedforsecurity=False)
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/raw/PICMUS_carotid_cross.uff"),
    )
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)

    if args.output.exists():
        valid = (
            args.output.stat().st_size == EXPECTED_SIZE
            and file_md5(args.output) == EXPECTED_MD5
        )
        if valid:
            print(f"Already present and verified: {args.output}")
            return
        raise RuntimeError(f"Existing file failed integrity check: {args.output}")

    partial = args.output.with_suffix(args.output.suffix + ".part")
    digest = hashlib.md5(usedforsecurity=False)
    size = 0
    try:
        with urlopen(URL) as response, partial.open("wb") as output:
            while block := response.read(1024 * 1024):
                output.write(block)
                digest.update(block)
                size += len(block)
        if size != EXPECTED_SIZE or digest.hexdigest() != EXPECTED_MD5:
            raise RuntimeError("Downloaded file failed the Zenodo size/checksum verification")
        partial.replace(args.output)
    finally:
        if partial.exists():
            partial.unlink()
    print(f"Downloaded and verified: {args.output}")


if __name__ == "__main__":
    main()
