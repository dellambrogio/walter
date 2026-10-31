"""Download only the swissTLM3D layers we use from the national shapefile zip.

Usage: .venv/bin/python data/preprocessing/download_tlm_strassen.py   (or `just download-tlm`)
Source: geo.admin STAC, collection ch.swisstopo.swisstlm3d (open government data, "© swisstopo").
Output: data/ref/swisstlm3d/swissTLM3D_<layer>.{shp,shx,dbf,prj,cpg} for
- TLM_STRASSE: roads and paths, with the hiking trail categories (load_trails.py)
- TLM_UEBRIGE_BAHN: cable cars, gondolas, chairlifts, ski lifts, funiculars (load_lifts.py)

The full zip is ~3.6 GB; the zip directory lets us read just these members (~530 MB) with HTTP range
requests. Skips files that are already there.
"""

import io
import shutil
import urllib.request
import zipfile
from pathlib import Path

RELEASE = "2026-02"
URL = (
    f"https://data.geo.admin.ch/ch.swisstopo.swisstlm3d/swisstlm3d_{RELEASE}/"
    f"swisstlm3d_{RELEASE}_2056_5728.shp.zip"
)
LAYERS = {"swissTLM3D_TLM_STRASSE", "swissTLM3D_TLM_UEBRIGE_BAHN"}
OUT = Path("data/ref/swisstlm3d")


class RemoteFile(io.RawIOBase):
    """A seekable read-only view of a URL, one HTTP range request per read."""

    def __init__(self, url: str) -> None:
        self.url = url
        self.pos = 0
        with urllib.request.urlopen(urllib.request.Request(url, method="HEAD")) as r:
            self.size = int(r.headers["Content-Length"])

    def readable(self) -> bool:
        return True

    def seekable(self) -> bool:
        return True

    def tell(self) -> int:
        return self.pos

    def seek(self, offset: int, whence: int = io.SEEK_SET) -> int:
        self.pos = {io.SEEK_SET: 0, io.SEEK_CUR: self.pos, io.SEEK_END: self.size}[whence] + offset
        return self.pos

    def readinto(self, buffer) -> int:  # noqa: ANN001 (memoryview from BufferedReader)
        if self.pos >= self.size:
            return 0
        end = min(self.pos + len(buffer), self.size) - 1
        req = urllib.request.Request(self.url, headers={"Range": f"bytes={self.pos}-{end}"})
        with urllib.request.urlopen(req) as r:
            data = r.read()
        buffer[: len(data)] = data
        self.pos += len(data)
        return len(data)


OUT.mkdir(parents=True, exist_ok=True)
with zipfile.ZipFile(io.BufferedReader(RemoteFile(URL), buffer_size=8 << 20)) as z:
    for info in z.infolist():
        name = info.filename.replace("\\", "/").rsplit("/", 1)[-1]
        stem, _, ext = name.partition(".")
        if stem not in LAYERS or ext not in {"shp", "shx", "dbf", "prj", "cpg"}:
            continue
        target = OUT / name
        if target.exists() and target.stat().st_size == info.file_size:
            print(f"{name}: already there")
            continue
        print(f"{name}: {info.compress_size / 1e6:.0f} MB ...", flush=True)
        with z.open(info) as src, open(target, "wb") as dst:
            shutil.copyfileobj(src, dst, 8 << 20)
print(f"swissTLM3D {RELEASE} {', '.join(sorted(LAYERS))} in {OUT}")
