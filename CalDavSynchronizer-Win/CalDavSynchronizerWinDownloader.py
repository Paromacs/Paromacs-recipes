#!/usr/bin/env python3
"""Download the official CalDavSynchronizer ZIP and extract only its Windows MSI."""
import os
import ssl
import zipfile
from pathlib import Path, PurePosixPath
from urllib.parse import urlparse
from urllib.request import Request, urlopen

import certifi
from autopkglib import Processor, ProcessorError


class CalDavSynchronizerWinDownloader(Processor):
    description = __doc__
    input_variables = {
        "version": {"required": True, "description": "Discovered CalDavSynchronizer version."},
        "caldav_zip_url": {"required": True, "description": "Official ZIP URL."},
        "caldav_zip_filename": {"required": True, "description": "Official ZIP filename."},
    }
    output_variables = {
        "caldav_msi_path": {"description": "Extracted and validated MSI path."},
    }

    @staticmethod
    def looks_like_msi(path):
        try:
            if path.stat().st_size < 1024:
                return False
            with path.open("rb") as stream:
                return stream.read(8) == bytes.fromhex("D0CF11E0A1B11AE1")
        except OSError:
            return False

    def main(self):
        temp_zip = None
        temp_msi = None
        try:
            url = self.env["caldav_zip_url"]
            parsed = urlparse(url)
            # The provider resolves the vendor's official download page to the
            # GitHub Releases asset URL. Accept that exact upstream repository
            # path as well as the vendor site, while rejecting arbitrary hosts.
            official_vendor = parsed.scheme == "https" and parsed.hostname in (
                "caldavsynchronizer.org", "www.caldavsynchronizer.org"
            )
            official_github_release = (
                parsed.scheme == "https"
                and parsed.hostname == "github.com"
                and parsed.path.startswith(
                    "/aluxnimm/outlookcaldavsynchronizer/releases/download/"
                )
            )
            if not (official_vendor or official_github_release):
                raise ValueError(
                    "ZIP URL must use HTTPS on caldavsynchronizer.org or the "
                    "official aluxnimm/outlookcaldavsynchronizer GitHub Releases path"
                )
            zip_filename = self.env["caldav_zip_filename"]
            if not zip_filename.lower().endswith(".zip") or "/" in zip_filename or "\\" in zip_filename:
                raise ValueError(f"Invalid ZIP filename: {zip_filename}")

            cache = Path(self.env["RECIPE_CACHE_DIR"]) / "downloads" / self.env["version"]
            cache.mkdir(parents=True, exist_ok=True)
            zip_path = cache / zip_filename
            msi_path = cache / "CalDavSynchronizer.Setup.msi"
            if msi_path.is_file() and self.looks_like_msi(msi_path):
                self.env["caldav_msi_path"] = str(msi_path)
                self.output(f"Using cached MSI: {msi_path}")
                return

            temp_zip = cache / (zip_filename + ".partial")
            temp_zip.unlink(missing_ok=True)
            context = ssl.create_default_context(cafile=certifi.where())
            request = Request(url, headers={"User-Agent": "AutoPkg-CalDavSynchronizer-Win/1.0"})
            with urlopen(request, timeout=180, context=context) as response, temp_zip.open("wb") as output:
                final = urlparse(response.geturl())
                if final.scheme != "https" or final.hostname not in (
                    "caldavsynchronizer.org", "www.caldavsynchronizer.org", "github.com",
                    "githubusercontent.com", "release-assets.githubusercontent.com"
                ):
                    raise ValueError(f"ZIP download redirected to unexpected host: {final.hostname}")
                while True:
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    output.write(chunk)
            os.replace(temp_zip, zip_path)

            with zipfile.ZipFile(zip_path) as archive:
                # Select an MSI only; explicitly never select the EXE in this archive.
                members = []
                for info in archive.infolist():
                    if info.is_dir():
                        continue
                    posix = PurePosixPath(info.filename)
                    if posix.is_absolute() or ".." in posix.parts:
                        continue
                    if posix.name.lower().endswith(".msi"):
                        members.append(info)
                if not members:
                    raise ValueError("The vendor ZIP contains no MSI file")
                # Prefer the expected setup MSI, then a CalDav-named MSI, then a sole MSI.
                preferred = [m for m in members if m.filename.rsplit("/", 1)[-1].lower() == "caldavsynchronizer.setup.msi"]
                if not preferred:
                    preferred = [m for m in members if "caldav" in m.filename.rsplit("/", 1)[-1].lower()]
                if len(preferred) == 1:
                    selected = preferred[0]
                elif len(members) == 1:
                    selected = members[0]
                else:
                    raise ValueError("ZIP has multiple MSI files and no unambiguous CalDavSynchronizer setup MSI: "
                                     + ", ".join(m.filename for m in members))
                temp_msi = cache / (selected.filename.rsplit("/", 1)[-1] + ".partial")
                with archive.open(selected) as source, temp_msi.open("wb") as target:
                    while True:
                        chunk = source.read(1024 * 1024)
                        if not chunk:
                            break
                        target.write(chunk)
            if not self.looks_like_msi(temp_msi):
                raise ValueError(f"Extracted MSI failed size/signature validation: {selected.filename}")
            os.replace(temp_msi, msi_path)
            self.env["caldav_msi_path"] = str(msi_path)
            self.output(f"Extracted MSI (not EXE): {msi_path} ({msi_path.stat().st_size} bytes)")
        except Exception as exc:
            raise ProcessorError(f"CalDavSynchronizer ZIP/MSI download failed: {exc}") from exc
        finally:
            if temp_zip is not None:
                temp_zip.unlink(missing_ok=True)
            if temp_msi is not None:
                temp_msi.unlink(missing_ok=True)


if __name__ == "__main__":
    PROCESSOR = CalDavSynchronizerWinDownloader()
    PROCESSOR.execute_shell()
