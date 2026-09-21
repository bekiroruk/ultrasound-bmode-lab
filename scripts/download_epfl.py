"""Range-download selected EPFL in-vivo RF samples without fetching full volunteer archives."""

from __future__ import annotations

import argparse
import hashlib
import zlib
from pathlib import Path

try:
    from remotezip import RemoteZip
except ImportError as exc:  # pragma: no cover - command-line dependency guard
    raise SystemExit('Install the data extra first: python -m pip install -e ".[datasets]"') from exc

BASE_URL = "https://datasets.epfl.ch/epfl_ultrafast_ultrasound"
SETTINGS = {
    "beamforming_settings.yaml": (1_843, 191_401_184),
    "steering_angles.npy": (824, 3_807_021_387),
    "time_axis.npy": (17_192, 2_967_575_721),
    "time_axis_per_angle.npy": (1_425_536, 3_757_611_726),
}
SAMPLES = {
    "v5-carotid": {
        "archive": "volunteer_005.zip",
        "member": "volunteer_005/carotid/invivo_14965.npz",
        "output": "invivo_14965.npz",
        "size": 129_470_889,
        "crc32": 3_380_171_651,
        "sha256": "55432c87f1f12aac866a75976cb5680c3d303d5b103076fcd0c18841256c749e",
    },
    "v8-carotid": {
        "archive": "volunteer_008.zip",
        "member": "volunteer_008/carotid/invivo_18198.npz",
        "output": "invivo_18198.npz",
        "size": 129_495_251,
        "crc32": 4_287_067_764,
        "sha256": "d82d56f1888e1be5b21cf9302ba95bf97ff91d4b7f79dbe32cff7a89b210b6f0",
    },
}


def _verified_write(
    output: Path, data: bytes, size: int, crc32: int, sha256: str | None = None
) -> None:
    digest = hashlib.sha256(data).hexdigest()
    if len(data) != size or zlib.crc32(data) != crc32 or (sha256 and digest != sha256):
        raise RuntimeError(f"EPFL member integrity check failed: {output.name}")
    output.parent.mkdir(parents=True, exist_ok=True)
    partial = output.with_suffix(output.suffix + ".part")
    partial.write_bytes(data)
    partial.replace(output)


def _existing_valid(
    output: Path, size: int, crc32: int, sha256: str | None = None
) -> bool:
    if not output.is_file() or output.stat().st_size != size:
        return False
    data = output.read_bytes()
    return zlib.crc32(data) == crc32 and (
        sha256 is None or hashlib.sha256(data).hexdigest() == sha256
    )


def download_settings(root: Path) -> None:
    url = f"{BASE_URL}/settings.zip"
    with RemoteZip(url) as archive:
        for filename, (size, crc32) in SETTINGS.items():
            output = root / "settings" / filename
            if _existing_valid(output, size, crc32):
                print(f"Already present and verified: {output}")
                continue
            _verified_write(output, archive.read(f"settings/{filename}"), size, crc32)
            print(f"Downloaded and verified: {output}")


def download_sample(alias: str, root: Path) -> None:
    item = SAMPLES[alias]
    output = root / str(item["output"])
    size = int(item["size"])
    crc32 = int(item["crc32"])
    sha256 = str(item["sha256"])
    if _existing_valid(output, size, crc32, sha256):
        print(f"Already present and verified: {output}")
        return
    with RemoteZip(f"{BASE_URL}/{item['archive']}") as archive:
        data = archive.read(str(item["member"]))
    _verified_write(output, data, size, crc32, sha256)
    print(f"Downloaded and verified: {output}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sample", choices=["all", *SAMPLES], default="all")
    parser.add_argument("--output-dir", type=Path, default=Path("data/raw/epfl"))
    args = parser.parse_args()
    download_settings(args.output_dir)
    selected = SAMPLES if args.sample == "all" else (args.sample,)
    for alias in selected:
        download_sample(alias, args.output_dir)


if __name__ == "__main__":
    main()
