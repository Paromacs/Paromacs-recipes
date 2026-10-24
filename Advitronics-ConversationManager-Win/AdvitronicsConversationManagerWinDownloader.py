#!/usr/bin/env python3
"""Download the official Advitronics Conversation Manager Windows MSI into the AutoPkg cache."""
import os
import ssl
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen

import certifi
from autopkglib import Processor, ProcessorError


class AdvitronicsConversationManagerWinDownloader(Processor):
    description = __doc__
    input_variables = {
        "version": {"required": True, "description": "Discovered Windows MSI version."},
        "advitronics_msi_url": {"required": True, "description": "Official MSI URL."},
        "advitronics_msi_filename": {"required": True, "description": "Official MSI filename."},
    }
    output_variables = {
        "advitronics_msi_path": {"description": "Downloaded MSI path."},
    }

    def main(self):
        temp = None
        try:
            url = self.env["advitronics_msi_url"]
            parsed = urlparse(url)
            if parsed.scheme != "https" or parsed.hostname not in ("advitronics.nl", "www.advitronics.nl"):
                raise ValueError("MSI URL must use HTTPS on the official advitronics.nl host")
            filename = self.env["advitronics_msi_filename"]
            if not filename.lower().endswith(".msi") or "/" in filename or "\\" in filename:
                raise ValueError(f"Invalid MSI filename: {filename}")

            cache = Path(self.env["RECIPE_CACHE_DIR"]) / "downloads" / self.env["version"]
            cache.mkdir(parents=True, exist_ok=True)
            destination = cache / filename
            # A cached file is reused only if it looks like a real Windows Installer database.
            if destination.is_file() and self.looks_like_msi(destination):
                self.output(f"Using cached MSI: {destination}")
                self.env["advitronics_msi_path"] = str(destination)
                return

            temp = cache / (filename + ".partial")
            temp.unlink(missing_ok=True)
            context = ssl.create_default_context(cafile=certifi.where())
            request = Request(url, headers={"User-Agent": "AutoPkg-Advitronics-ConversationManager-Win/1.0"})
            with urlopen(request, timeout=180, context=context) as response, temp.open("wb") as output:
                final = urlparse(response.geturl())
                if final.scheme != "https" or final.hostname not in ("advitronics.nl", "www.advitronics.nl"):
                    raise ValueError(f"MSI download redirected to unexpected host: {final.hostname}")
                while True:
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    output.write(chunk)
            if not self.looks_like_msi(temp):
                raise ValueError("Downloaded file is too small or does not have the expected MSI/OLE signature")
            os.replace(temp, destination)
            self.env["advitronics_msi_path"] = str(destination)
            self.output(f"Downloaded MSI: {destination} ({destination.stat().st_size} bytes)")
        except Exception as exc:
            raise ProcessorError(f"Advitronics MSI download failed: {exc}") from exc
        finally:
            if temp is not None:
                temp.unlink(missing_ok=True)

    @staticmethod
    def looks_like_msi(path):
        try:
            if path.stat().st_size < 1024:
                return False
            with path.open("rb") as stream:
                signature = stream.read(8)
            return signature == bytes.fromhex("D0CF11E0A1B11AE1")
        except OSError:
            return False


if __name__ == "__main__":
    PROCESSOR = AdvitronicsConversationManagerWinDownloader()
    PROCESSOR.execute_shell()
