#!/usr/bin/env python3
"""Discover the current Windows MSI version from the official Advitronics downloads page."""
import re
import ssl
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

import certifi
from autopkglib import Processor, ProcessorError


class LinkParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() != "a":
            return
        attrs = dict(attrs)
        href = attrs.get("href", "").strip()
        if href:
            self.links.append(href)


class AdvitronicsConversationManagerWinProvider(Processor):
    description = __doc__
    input_variables = {
        "ADVITRONICS_DOWNLOADS_URL": {
            "required": True,
            "description": "Official Advitronics downloads page.",
        },
    }
    output_variables = {
        "version": {"description": "Latest Windows MSI version."},
        "advitronics_msi_url": {"description": "Official Windows MSI download URL."},
        "advitronics_msi_filename": {"description": "Windows MSI filename."},
    }

    def main(self):
        try:
            page_url = self.env["ADVITRONICS_DOWNLOADS_URL"].strip()
            if urlparse(page_url).scheme != "https":
                raise ValueError("Downloads page must use HTTPS")
            context = ssl.create_default_context(cafile=certifi.where())
            request = Request(page_url, headers={"User-Agent": "AutoPkg-Advitronics-ConversationManager-Win/1.0"})
            with urlopen(request, timeout=30, context=context) as response:
                final_url = response.geturl()
                html = response.read().decode("utf-8", errors="replace")
            if urlparse(final_url).hostname not in ("advitronics.nl", "www.advitronics.nl"):
                raise ValueError(f"Unexpected downloads page host: {urlparse(final_url).hostname}")

            parser = LinkParser()
            parser.feed(html)
            candidates = []
            for href in parser.links:
                absolute = urljoin(final_url, href)
                parsed = urlparse(absolute)
                filename = parsed.path.rsplit("/", 1)[-1]
                match = re.fullmatch(r"ConversationManager_(\d+(?:_\d+)+)\.msi", filename, re.IGNORECASE)
                if match and parsed.scheme == "https" and parsed.hostname in ("advitronics.nl", "www.advitronics.nl"):
                    version = match.group(1).replace("_", ".")
                    candidates.append((version, absolute, filename))

            # Some WordPress themes expose the download URL in a data attribute rather than an anchor.
            if not candidates:
                pattern = re.compile(r"https://(?:www\.)?advitronics\.nl/[^\"'<>\s]*ConversationManager_(\d+(?:_\d+)+)\.msi", re.IGNORECASE)
                for match in pattern.finditer(html):
                    filename = match.group(0).rsplit("/", 1)[-1]
                    candidates.append((match.group(1).replace("_", "."), match.group(0), filename))

            if not candidates:
                raise ValueError("Could not find an official ConversationManager_<version>.msi link on the downloads page")

            def version_key(item):
                return tuple(int(part) for part in item[0].split("."))

            candidates.sort(key=version_key)
            version, url, filename = candidates[-1]
            self.env.update({
                "version": version,
                "advitronics_msi_url": url,
                "advitronics_msi_filename": filename,
            })
            self.output(f"Latest Advitronics Conversation Manager Windows version: {version}")
            self.output(f"MSI: {url}")
        except Exception as exc:
            raise ProcessorError(f"Advitronics Windows version discovery failed: {exc}") from exc


if __name__ == "__main__":
    PROCESSOR = AdvitronicsConversationManagerWinProvider()
    PROCESSOR.execute_shell()
