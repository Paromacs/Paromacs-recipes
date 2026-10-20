#!/usr/bin/env python3
"""AutoPkg processor: download and validate DYMO x64 and x86 EXE files."""
import hashlib
import ssl
import certifi
import os
import tempfile
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from autopkglib import Processor, ProcessorError

SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())


class DYMOConnectDualDownloader(Processor):
    description = __doc__
    input_variables = {
        "version": {"required": True, "description": "Release version."},
        "dymo_x64_url": {"required": True, "description": "x64 download URL."},
        "dymo_x86_url": {"required": True, "description": "x86 download URL."},
        "dymo_x64_sha256": {"required": False, "description": "Optional x64 expected SHA256."},
        "dymo_x86_sha256": {"required": False, "description": "Optional x86 expected SHA256."},
    }
    output_variables = {
        "dymo_x64_path": {"description": "Cached x64 installer path."},
        "dymo_x86_path": {"description": "Cached x86 installer path."},
        "dymo_x64_actual_sha256": {"description": "Calculated x64 SHA256."},
        "dymo_x86_actual_sha256": {"description": "Calculated x86 SHA256."},
    }

    @staticmethod
    def sha256(path):
        digest = hashlib.sha256()
        with open(path, "rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
        return digest.hexdigest().upper()

    def download(self, arch, url, expected, destination):
        parsed = urlparse(url)
        if parsed.scheme != "https" or parsed.hostname != "dymoreleasecontent.blob.core.windows.net":
            raise ValueError(f"Untrusted {arch} download URL: {url}")
        if destination.is_file():
            actual = self.sha256(destination)
            if not expected or actual == expected.upper():
                self.output(f"Using cached {arch} installer: {destination}")
                return actual
            destination.unlink()
        fd, temporary = tempfile.mkstemp(prefix=".dymo-", suffix=".tmp", dir=str(destination.parent))
        try:
            with os.fdopen(fd, "wb") as out:
                request = Request(url, headers={"User-Agent": "Paromacs-AutoPkg-DYMO/1.0"})
                with urlopen(request, context=SSL_CONTEXT, timeout=120) as response:
                    if response.status != 200:
                        raise ValueError(f"Unexpected HTTP {response.status} for {arch}")
                    for chunk in iter(lambda: response.read(1024 * 1024), b""):
                        out.write(chunk)
            actual = self.sha256(temporary)
            if expected and actual != expected.upper():
                raise ValueError(f"{arch} SHA256 mismatch: expected {expected}, got {actual}")
            os.replace(temporary, destination)
            self.output(f"Downloaded {arch}: {destination} (SHA256 {actual})")
            return actual
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    def main(self):
        try:
            version = self.env["version"]
            cache = Path(self.env["RECIPE_CACHE_DIR"]) / "downloads" / version
            cache.mkdir(parents=True, exist_ok=True)
            for arch, suffix in (("x64", "X64"), ("x86", "X86")):
                url = self.env[f"dymo_{arch}_url"]
                expected = self.env.get(f"dymo_{arch}_sha256", "")
                destination = cache / f"DCDSetup{version}-{suffix}.exe"
                actual = self.download(arch, url, expected, destination)
                self.env[f"dymo_{arch}_path"] = str(destination)
                self.env[f"dymo_{arch}_actual_sha256"] = actual
        except Exception as error:
            raise ProcessorError(f"DYMO download failed: {error}") from error


if __name__ == "__main__":
    PROCESSOR = DYMOConnectDualDownloader()
    PROCESSOR.execute_shell()
