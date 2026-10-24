#!/usr/bin/env python3
"""Read the PearPie Windows release feed and expose version, MSI URL, hash and release date."""
import json
import ssl
import certifi
from datetime import datetime
from urllib.parse import urlparse
from urllib.request import Request, urlopen
from autopkglib import Processor, ProcessorError

class PearPieWinReleaseProvider(Processor):
    description = __doc__
    input_variables = {
        "PEARPIE_RELEASE_URL": {"required": True, "description": "JSON release feed URL used by the existing PearPie Windows script."},
    }
    output_variables = {
        "version": {"description": "Latest PearPie version."},
        "pearpie_msi_url": {"description": "MSI download URL."},
        "pearpie_sha256": {"description": "Expected SHA-256."},
        "pearpie_release_date": {"description": "YYYY-MM-DD from published_at."},
    }

    def main(self):
        try:
            url = self.env["PEARPIE_RELEASE_URL"].strip()
            if urlparse(url).scheme != "https":
                raise ValueError("PEARPIE_RELEASE_URL must use HTTPS")
            context = ssl.create_default_context(cafile=certifi.where())
            req = Request(url, headers={"Accept": "application/json", "User-Agent": "AutoPkg-PearPie-Win"})
            with urlopen(req, timeout=30, context=context) as response:
                release = json.load(response)
            version = str(release["version"]).strip()
            msi_url = str(release["url"]).strip()
            sha256 = str(release["sha256"]).strip().lower()
            published_at = str(release["published_at"]).strip()
            if not version or any(not x.isdigit() for x in version.split(".")):
                raise ValueError("Invalid numeric PearPie version")
            if urlparse(msi_url).scheme != "https":
                raise ValueError("PearPie MSI URL must use HTTPS")
            if len(sha256) != 64 or any(c not in "0123456789abcdef" for c in sha256):
                raise ValueError("Invalid PearPie SHA-256")
            release_date = datetime.fromisoformat(published_at[:10]).date().isoformat()
            self.env.update({
                "version": version,
                "pearpie_msi_url": msi_url,
                "pearpie_sha256": sha256,
                "pearpie_release_date": release_date,
            })
            self.output(f"Latest PearPie Windows version: {version}")
            self.output(f"Release date: {release_date}")
            self.output(f"MSI: {msi_url}")
        except Exception as exc:
            raise ProcessorError(f"PearPie release discovery failed: {exc}") from exc

if __name__ == "__main__":
    PROCESSOR = PearPieWinReleaseProvider()
    PROCESSOR.execute_shell()
