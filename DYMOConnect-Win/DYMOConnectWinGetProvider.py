#!/usr/bin/env python3
"""AutoPkg processor: discover DYMO Connect Windows installers in WinGet."""
import json
import ssl
import certifi
import re
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen

from autopkglib import Processor, ProcessorError

SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())

API_ROOT = "https://api.github.com/repos/microsoft/winget-pkgs/contents/manifests/d/DYMO/DYMOConnect"
DYMO_HOST = "dymoreleasecontent.blob.core.windows.net"
INSTALLER_RE = re.compile(
    r"/dymo-release/DCDWIN/DCDSetup(?P<version>\d+(?:\.\d+){3})-(?P<arch>X64|X86)\.exe", re.I
)


def fetch(url, as_json=False):
    request = Request(url, headers={"User-Agent": "Paromacs-AutoPkg-DYMO/1.0", "Accept": "application/vnd.github+json"})
    with urlopen(request, context=SSL_CONTEXT, timeout=45) as response:
        data = response.read()
    return json.loads(data) if as_json else data.decode("utf-8")


def version_tuple(value):
    return tuple(int(part) for part in value.split("."))


class DYMOConnectWinGetProvider(Processor):
    description = __doc__
    input_variables = {}
    output_variables = {
        "version": {"description": "Latest four-component WinGet version."},
        "dymo_x64_url": {"description": "Official x64 installer URL."},
        "dymo_x86_url": {"description": "Official x86 installer URL."},
        "dymo_x64_sha256": {"description": "WinGet x64 SHA256, if present."},
        "dymo_x86_sha256": {"description": "WinGet x86 SHA256, if present."},
        "dymo_release_date": {"description": "ReleaseDate from WinGet installer manifest, if present."},
    }

    def main(self):
        try:
            entries = fetch(API_ROOT, as_json=True)
            versions = [e["name"] for e in entries if e.get("type") == "dir" and re.fullmatch(r"\d+(?:\.\d+){3}", e["name"])]
            if not versions:
                raise ValueError("No four-part DYMO versions found in WinGet")
            version = max(versions, key=version_tuple)
            entries = fetch(f"{API_ROOT}/{quote(version)}", as_json=True)
            manifests = [e for e in entries if e.get("name", "").endswith(".installer.yaml")]
            if len(manifests) != 1:
                raise ValueError(f"Expected one installer manifest, found {len(manifests)}")
            yaml_text = fetch(manifests[0]["download_url"])
            date_match = re.search(r"(?m)^ReleaseDate:\s*[\"']?(\d{4}-\d{2}-\d{2})[\"']?\s*$", yaml_text)
            release_date = date_match.group(1) if date_match else ""
            # Parse the simple Installer entries without requiring PyYAML in AutoPkg's Python.
            # Restrict extraction to InstallerUrl and InstallerSha256 lines per installer block.
            blocks = re.split(r"(?m)^\s*-\s+Architecture:\s*", yaml_text)[1:]
            found = {}
            for block in blocks:
                url_match = re.search(r"(?m)^\s*InstallerUrl:\s*['\"]?(https://\S+?\.exe)['\"]?\s*$", block)
                hash_match = re.search(r"(?m)^\s*InstallerSha256:\s*['\"]?([A-Fa-f0-9]{64})['\"]?\s*$", block)
                if not url_match:
                    continue
                url = url_match.group(1)
                parsed = urlparse(url)
                match = INSTALLER_RE.fullmatch(parsed.path)
                if parsed.scheme != "https" or parsed.hostname != DYMO_HOST or not match:
                    continue
                if match.group("version") != version:
                    raise ValueError("WinGet installer version mismatch")
                found[match.group("arch").upper()] = (url, hash_match.group(1).upper() if hash_match else "")
            if "X64" not in found:
                raise ValueError("No official DYMO x64 installer in WinGet manifest")
            x64_url, x64_hash = found["X64"]
            x86_url, x86_hash = found.get("X86", (re.sub(r"-X64\.exe$", "-X86.exe", x64_url, flags=re.I), ""))
            self.env.update({
                "version": version,
                "dymo_x64_url": x64_url,
                "dymo_x86_url": x86_url,
                "dymo_x64_sha256": x64_hash,
                "dymo_x86_sha256": x86_hash,
                "dymo_release_date": release_date,
            })
            self.output(f"Latest DYMO Connect version: {version}")
            self.output(f"WinGet release date: {release_date or 'not provided; Action1 creation date will be used'}")
            self.output(f"x64: {x64_url}")
            self.output(f"x86: {x86_url}")
        except Exception as error:
            raise ProcessorError(f"DYMO WinGet discovery failed: {error}") from error


if __name__ == "__main__":
    PROCESSOR = DYMOConnectWinGetProvider()
    PROCESSOR.execute_shell()
