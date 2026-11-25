
#!/usr/bin/python3

from autopkglib import Processor


class YealinkMunkiVersion(Processor):
    """Set the Munki pkginfo version from the download recipe."""

    description = "Sets the Munki pkginfo version."

    input_variables = {
        "version": {
            "required": True,
            "description": "Version supplied by the download recipe.",
        },
    }

    output_variables = {
        "pkginfo": {
            "description": "Munki pkginfo with the correct version.",
        },
    }

    def main(self):
        pkginfo = self.env.get("pkginfo", {}).copy()
        pkginfo["version"] = self.env["version"]
        self.env["pkginfo"] = pkginfo


if __name__ == "__main__":
    processor = YealinkMunkiVersion()
    processor.execute()
