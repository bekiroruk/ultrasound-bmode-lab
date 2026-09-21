"""Download and integrity-check selected public PICMUS channel datasets."""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
from urllib.request import urlopen

RECORD_API = "https://zenodo.org/api/records/20261898/files/{filename}/content"
DATASETS = {
    "carotid": (
        "PICMUS_carotid_cross.uff",
        76_705_680,
        "be81dfc519d3f7c642ff60d85642f311",
    ),
    "contrast": (
        "PICMUS_experiment_contrast_speckle.uff",
        145_518_504,
        "26bbfbbb702e90fe4fa9f1ab7d7fc065",
    ),
    "resolution": (
        "PICMUS_experiment_resolution_distortion.uff",
        145_518_524,
        "e8a4487993222f28458aa88259345440",
    ),
}


def file_md5(path: Path) -> str:
    digest = hashlib.md5(usedforsecurity=False)
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", choices=DATASETS, default="carotid")
    parser.add_argument(
        "--output",
        type=Path,
        help="Override the default data/raw output path",
    )
    args = parser.parse_args()
    filename, expected_size, expected_md5 = DATASETS[args.dataset]
    output_path = args.output or Path("data/raw") / filename
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if output_path.exists():
        valid = (
            output_path.stat().st_size == expected_size
            and file_md5(output_path) == expected_md5
        )
        if valid:
            print(f"Already present and verified: {output_path}")
            return
        raise RuntimeError(f"Existing file failed integrity check: {output_path}")

    partial = output_path.with_suffix(output_path.suffix + ".part")
    digest = hashlib.md5(usedforsecurity=False)
    size = 0
    try:
        with urlopen(RECORD_API.format(filename=filename)) as response, partial.open("wb") as output:
            while block := response.read(1024 * 1024):
                output.write(block)
                digest.update(block)
                size += len(block)
        if size != expected_size or digest.hexdigest() != expected_md5:
            raise RuntimeError("Downloaded file failed the Zenodo size/checksum verification")
        partial.replace(output_path)
    finally:
        if partial.exists():
            partial.unlink()
    print(f"Downloaded and verified: {output_path}")


if __name__ == "__main__":
    main()
