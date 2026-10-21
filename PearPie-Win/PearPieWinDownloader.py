#!/usr/bin/env python3
"""Download and SHA-256 verify the PearPie Windows x64 MSI with persistent AutoPkg caching."""
import hashlib
import os
import ssl
import certifi
from pathlib import Path
from urllib.parse import urlparse, unquote
from urllib.request import Request, urlopen
from autopkglib import Processor, ProcessorError

class PearPieWinDownloader(Processor):
    description = __doc__
    input_variables = {
        "version": {"required": True, "description": "PearPie version."},
        "pearpie_msi_url": {"required": True, "description": "MSI URL."},
        "pearpie_sha256": {"required": True, "description": "Expected SHA-256."},
    }
    output_variables = {
        "pearpie_msi_path": {"description": "Verified cached MSI path."},
        "download_changed": {"description": "Whether the MSI was newly downloaded."},
    }

    @staticmethod
    def sha256(path):
        digest = hashlib.sha256()
        with path.open("rb") as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest().lower()

    def main(self):
        try:
            url = self.env["pearpie_msi_url"]
            parsed = urlparse(url)
            if parsed.scheme != "https":
                raise ValueError("MSI URL must use HTTPS")
            filename = Path(unquote(parsed.path)).name
            if not filename.lower().endswith(".msi"):
                raise ValueError(f"Expected MSI installer, got: {filename}")
            expected = self.env["pearpie_sha256"].lower()
            cache = Path(self.env["RECIPE_CACHE_DIR"]) / "downloads" / self.env["version"]
            cache.mkdir(parents=True, exist_ok=True)
            destination = cache / filename
            if destination.is_file() and self.sha256(destination) == expected:
                self.output(f"Using verified cached installer: {destination}")
                self.env["pearpie_msi_path"] = str(destination)
                self.env["download_changed"] = False
                return
            temp = cache / (filename + ".partial")
            temp.unlink(missing_ok=True)
            try:
                context = ssl.create_default_context(cafile=certifi.where())
                request = Request(url, headers={"User-Agent": "AutoPkg-PearPie-Win"})
                with urlopen(request, timeout=120, context=context) as response, temp.open("wb") as output:
                    while True:
                        chunk = response.read(1024 * 1024)
                        if not chunk:
                            break
                        output.write(chunk)
                actual = self.sha256(temp)
                if actual != expected:
                    raise ValueError(f"SHA-256 mismatch: expected {expected}, received {actual}")
                os.replace(temp, destination)
            finally:
                temp.unlink(missing_ok=True)
            self.env["pearpie_msi_path"] = str(destination)
            self.env["download_changed"] = True
            self.output(f"Downloaded and SHA-256 verified: {destination}")
        except Exception as exc:
            raise ProcessorError(f"PearPie MSI download failed: {exc}") from exc

if __name__ == "__main__":
    PROCESSOR = PearPieWinDownloader()
    PROCESSOR.execute_shell()
