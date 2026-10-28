
#!/usr/bin/python
# -*- coding: utf-8 -*-

from autopkglib import Processor, ProcessorError
import re
import subprocess
from urllib.parse import urljoin, urlparse


class YubiKeyManagerVersionProvider(Processor):
    description = "Finds the latest YubiKey Manager macOS PKG."
    input_variables = {}
    output_variables = {
        "version": "Latest version.",
        "url": "Direct URL to the macOS installer.",
    }

    RELEASES_URL = (
        "https://developers.yubico.com/yubikey-manager/Releases/"
    )

    PKG_PATTERN = re.compile(
        r"yubikey-manager-(\d+\.\d+\.\d+)-mac\.pkg",
        re.IGNORECASE,
    )

    def main(self):
        try:
            result = subprocess.run(
                [
                    "/usr/bin/curl",
                    "--fail",
                    "--location",
                    "--silent",
                    "--show-error",
                    "--max-time",
                    "30",
                    self.RELEASES_URL,
                ],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=35,
            )
            html = result.stdout

        except (subprocess.CalledProcessError,
                subprocess.TimeoutExpired,
                OSError) as err:
            details = getattr(err, "stderr", None)
            if not details:
                details = str(err)

            raise ProcessorError(
                "Could not retrieve Yubico release page: %s" % details
            )

        matches = self.PKG_PATTERN.findall(html)
        versions = set(matches)

        if not versions:
            raise ProcessorError(
                "No macOS PKG links found on the Yubico release page."
            )

        version = max(
            versions,
            key=lambda value: tuple(
                int(part) for part in value.split(".")
            ),
        )

        filename = "yubikey-manager-%s-mac.pkg" % version
        url = urljoin(self.RELEASES_URL, filename)

        parsed = urlparse(url)
        if (
            parsed.scheme != "https"
            or parsed.hostname != "developers.yubico.com"
        ):
            raise ProcessorError(
                "Refusing unexpected installer URL: %s" % url
            )

        self.env["version"] = version
        self.env["url"] = url

        self.output("Latest version: %s" % version)
        self.output("Installer URL: %s" % url)


if __name__ == "__main__":
    PROCESSOR = YubiKeyManagerVersionProvider()
    PROCESSOR.execute_shell()
