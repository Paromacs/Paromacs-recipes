#!/usr/bin/python3
"""Discover the current Advitronics Conversation Manager DMG from its downloads page."""
import re
import subprocess
from urllib.parse import urlparse
from autopkglib import Processor, ProcessorError

PAGE = "https://advitronics.nl/downloads/"
LINK_RE = re.compile(r"""href\s*=\s*["']([^"']*ConversationManager(?:Arm)?_[0-9]+(?:_[0-9]+)+\.dmg)["']""", re.I)
FILE_RE = re.compile(r"^(ConversationManagerArm|ConversationManager)_([0-9]+(?:_[0-9]+)+)\.dmg$", re.I)

class AdvitronicsConversationManagerProvider(Processor):
    description = __doc__
    input_variables = {"ARCH": {"required": True, "description": "arm64 or x86_64"}}
    output_variables = {
        "version": {"description": "Version found in the official download link"},
        "url": {"description": "Architecture-specific DMG URL"},
        "pkg_filename": {"description": "DMG filename"},
        "munki_arch": {"description": "Munki architecture"},
    }

    def main(self):
        arch = self.env["ARCH"].strip()
        if arch not in ("arm64", "x86_64"):
            raise ProcessorError("ARCH must be arm64 or x86_64")
        try:
            result = subprocess.run(
                ["/usr/bin/curl", "-fsSL", "--max-time", "30",
                 "--user-agent", "AutoPkg-AdvitronicsConversationManager/1.0", PAGE],
                check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, encoding="utf-8")
        except (subprocess.CalledProcessError, OSError) as exc:
            raise ProcessorError("Could not retrieve Advitronics downloads page: {}".format(
                getattr(exc, "stderr", "") or str(exc)))

        matches = []
        for href in LINK_RE.findall(result.stdout):
            if href.startswith("//"):
                url = "https:" + href
            elif href.startswith("/"):
                url = "https://advitronics.nl" + href
            else:
                url = href
            parsed = urlparse(url)
            if parsed.scheme != "https" or parsed.hostname != "advitronics.nl":
                continue
            if not parsed.path.startswith("/wp-content/uploads/"):
                continue
            filename = parsed.path.rsplit("/", 1)[-1]
            found = FILE_RE.fullmatch(filename)
            if not found:
                continue
            prefix, v = found.groups()
            is_arm = prefix.lower() == "conversationmanagerarm"
            if (arch == "arm64") != is_arm:
                continue
            parts = tuple(int(x) for x in v.split("_"))
            version = ".".join(str(x) for x in parts)
            matches.append((parts, version, url, filename))
        if not matches:
            raise ProcessorError("No official Conversation Manager DMG link found for ARCH={}; page format may have changed".format(arch))
        _, version, url, filename = max(matches, key=lambda x: x[0])
        self.env.update({"version": version, "url": url, "pkg_filename": filename, "munki_arch": arch})
        self.output("Advitronics Conversation Manager version: {}".format(version))
        self.output("Architecture: {}; download: {}".format(arch, filename))

if __name__ == "__main__":
    PROCESSOR = AdvitronicsConversationManagerProvider()
    PROCESSOR.execute_shell()
