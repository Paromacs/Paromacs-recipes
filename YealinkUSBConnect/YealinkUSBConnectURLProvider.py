
#!/usr/bin/python3

import json
import re
import subprocess

from autopkglib import Processor, ProcessorError


class YealinkUSBConnectURLProvider(Processor):
    """Find the latest Yealink USB Connect macOS PKG and its download URL."""

    description = (
        "Finds the latest Yealink USB Connect macOS PKG "
        "for the selected architecture."
    )

    input_variables = {
        "ARCH": {
            "required": False,
            "description": "Target architecture: arm64 or x86_64.",
            "default": "arm64",
        },
    }

    output_variables = {
        "url": {
            "description": "Current direct download URL.",
        },
        "version": {
            "description": "Selected package version.",
        },
        "filename": {
            "description": "Local package filename.",
        },
        "file_id": {
            "description": "Yealink support file ID.",
        },
    }

    CATEGORY_ID = "01985edc-6198-75ff-81f9-e4589f147a11"

    RESOURCES_URL = (
        "https://support.yealink.com/support/v2/front/resources/list"
    )

    DOWNLOAD_URL = (
        "https://support.yealink.com/support/v2/front/file/downloadURL"
    )

    def curl_json(self, args):
        command = [
            "/usr/bin/curl",
            "--silent",
            "--show-error",
            "--fail",
            "--location",
        ] + args

        result = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
        )

        if result.returncode != 0:
            raise ProcessorError(
                "Yealink API request failed: {}".format(
                    result.stderr.strip()
                )
            )

        try:
            return json.loads(result.stdout)
        except ValueError as err:
            raise ProcessorError(
                "Yealink API returned invalid JSON: {}".format(err)
            )

    @staticmethod
    def version_tuple(version):
        parts = re.findall(r"\d+", str(version))
        if not parts:
            raise ProcessorError(
                "Could not determine package version: {}".format(version)
            )
        return tuple(int(part) for part in parts)

    @staticmethod
    def extract_version(item):
        version = item.get("quoteDocName", "")
        if version and re.search(r"\d", version):
            return version

        text = "{} {}".format(
            item.get("name", ""),
            item.get("fileName", ""),
        )

        match = re.search(r"\d+(?:\.\d+)+", text)
        if match:
            return match.group(0)

        raise ProcessorError(
            "Could not determine version for file: {}".format(
                item.get("name", item.get("fileID", "unknown"))
            )
        )

    def main(self):
        arch = self.env.get("ARCH", "arm64").lower()

        if arch not in ("arm64", "x86_64"):
            raise ProcessorError(
                "Unsupported ARCH '{}'. Use arm64 or x86_64.".format(arch)
            )

        request_body = {
            "skip": 0,
            "limit": 200,
            "autoCount": True,
            "filter": {
                "categoryID": self.CATEGORY_ID,
            },
        }

        response = self.curl_json([
            "--request", "POST",
            "--header", "Content-Type: application/json",
            "--header", "Accept: application/json",
            "--header", "x-language: en",
            "--header", "Origin: https://support.yealink.com",
            "--data-raw", json.dumps(request_body),
            self.RESOURCES_URL,
        ])

        if response.get("ret") != 0:
            raise ProcessorError(
                "Yealink resource API returned ret={}".format(
                    response.get("ret")
                )
            )

        resources = response.get("data", {}).get("value", [])

        candidates = []

        for item in resources:
            name = item.get("name", "")
            file_type = item.get("fileType", "").lower()

            if "macos" not in name.lower():
                continue

            if file_type != ".pkg":
                continue

            is_arm64 = "(arm64)" in name.lower()

            if arch == "arm64" and not is_arm64:
                continue

            if arch == "x86_64" and is_arm64:
                continue

            if not item.get("fileID"):
                continue

            version = self.extract_version(item)

            candidates.append({
                "item": item,
                "version": version,
                "version_tuple": self.version_tuple(version),
            })

        if not candidates:
            raise ProcessorError(
                "No matching Yealink macOS PKG found for ARCH={}".format(
                    arch
                )
            )

        selected = max(
            candidates,
            key=lambda candidate: candidate["version_tuple"],
        )

        item = selected["item"]
        version = selected["version"]
        file_id = item["fileID"]

        self.output(
            "Selected Yealink USB Connect {} version {}".format(
                arch, version
            )
        )

        download_response = self.curl_json([
            "--get",
            "--data-urlencode", "fileID={}".format(file_id),
            self.DOWNLOAD_URL,
        ])

        if download_response.get("ret") != 0:
            raise ProcessorError(
                "Yealink download URL API returned ret={}".format(
                    download_response.get("ret")
                )
            )

        download_url = (
            download_response.get("data", {}).get("downloadUrl")
        )

        if not download_url:
            raise ProcessorError(
                "Yealink API did not return data.downloadUrl"
            )

        if not download_url.lower().split("?", 1)[0].endswith(".pkg"):
            raise ProcessorError(
                "Unexpected download URL; expected a PKG: {}".format(
                    download_url
                )
            )

        filename = "YealinkUSBConnect-{}-{}.pkg".format(
            arch, version
        )

        self.env["url"] = download_url
        self.env["version"] = version
        self.env["filename"] = filename
        self.env["file_id"] = file_id

if __name__ == "__main__":
    processor = YealinkUSBConnectURLProvider()
    processor.main()