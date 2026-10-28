
#!/usr/bin/python
# -*- coding: utf-8 -*-

from autopkglib import Processor, ProcessorError
import re
import subprocess


class YubicoAuthenticatorVersionProvider(Processor):
    description = "Finds the latest Yubico Authenticator macOS release."

    input_variables = {}
    output_variables = {
        "version": "Latest macOS version.",
        "url": "Official direct macOS download URL.",
    }

    RELEASES_URL = (
        "https://developers.yubico.com/yubioath-flutter/Releases/"
    )
    DOWNLOAD_URL = (
        "https://developers.yubico.com/yubioath-flutter/"
        "Releases/yubico-authenticator-latest-mac.dmg"
    )

    VERSION_PATTERN = re.compile(
        r"yubico-authenticator-(\d+\.\d+\.\d+)-mac\.dmg"
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
        except (subprocess.CalledProcessError,
                subprocess.TimeoutExpired,
                OSError) as err:
            details = getattr(err, "stderr", None) or str(err)
            raise ProcessorError(
                "Could not retrieve Yubico releases: %s" % details
            )

        versions = set(self.VERSION_PATTERN.findall(result.stdout))

        if not versions:
            raise ProcessorError(
                "No macOS DMG versions found on Yubico's release page."
            )

        version = max(
            versions,
            key=lambda value: tuple(
                int(part) for part in value.split(".")
            ),
        )

        self.env["version"] = version
        self.env["url"] = self.DOWNLOAD_URL

        self.output("Latest macOS version: %s" % version)
        self.output("Direct download URL: %s" % self.DOWNLOAD_URL)


if __name__ == "__main__":
    PROCESSOR = YubicoAuthenticatorVersionProvider()
    PROCESSOR.execute_shell()
