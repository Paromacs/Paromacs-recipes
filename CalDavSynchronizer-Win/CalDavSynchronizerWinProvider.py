#!/usr/bin/env python3
"""Discover the newest CalDavSynchronizer Windows ZIP from the official download page."""
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
        if tag.lower() == "a":
            href = dict(attrs).get("href", "").strip()
            if href:
                self.links.append(href)


class CalDavSynchronizerWinProvider(Processor):
    description = __doc__
    input_variables = {
        "CALDAVSYNCHRONIZER_DOWNLOADS_URL": {
            "required": True, "description": "Official CalDavSynchronizer downloads page."
        }
    }
    output_variables = {
        "version": {"description": "Latest CalDavSynchronizer version."},
        "caldav_zip_url": {"description": "Official Windows ZIP URL."},
        "caldav_zip_filename": {"description": "Windows ZIP filename."},
    }

    def main(self):
        try:
            page_url = self.env["CALDAVSYNCHRONIZER_DOWNLOADS_URL"].strip()
            parsed_page = urlparse(page_url)
            if parsed_page.scheme != "https" or parsed_page.hostname not in (
                "caldavsynchronizer.org", "www.caldavsynchronizer.org"
            ):
                raise ValueError("Downloads page must be HTTPS on caldavsynchronizer.org")
            context = ssl.create_default_context(cafile=certifi.where())
            request = Request(page_url, headers={"User-Agent": "AutoPkg-CalDavSynchronizer-Win/1.0"})
            with urlopen(request, timeout=40, context=context) as response:
                final_url = response.geturl()
                html = response.read().decode("utf-8", errors="replace")
            if urlparse(final_url).hostname not in ("caldavsynchronizer.org", "www.caldavsynchronizer.org"):
                raise ValueError(f"Unexpected downloads page host: {urlparse(final_url).hostname}")

            parser = LinkParser()
            parser.feed(html)
            urls = [urljoin(final_url, href) for href in parser.links]
            # WordPress pages sometimes put direct links in embedded HTML/JSON instead of anchors.
            urls.extend(re.findall(
                r"https://(?:www\.)?caldavsynchronizer\.org/[^\"'<>\s]+?\.zip(?:\?[^\"'<>\s]*)?",
                html, re.IGNORECASE
            ))
            candidates = {}
            pattern = re.compile(
                r"(?:Outlook)?CalDavSynchronizer[-_ ]?(\d+(?:\.\d+){1,3})[^/]*\.zip$",
                re.IGNORECASE
            )
            for url in urls:
                parsed = urlparse(url)
                filename = parsed.path.rsplit("/", 1)[-1]
                match = pattern.search(filename)
                if (match and parsed.scheme == "https"
                        and parsed.hostname in ("caldavsynchronizer.org", "www.caldavsynchronizer.org", "github.com")):
                    version = match.group(1)
                    candidates[tuple(int(x) for x in version.split("."))] = (version, url, filename)
            if not candidates:
                # Fallback for the common OutlookCalDavSynchronizer-<version>.zip filename.
                pattern = re.compile(
                    r"(https://(?:www\.)?caldavsynchronizer\.org/[^\"'<>\s]*?"
                    r"(?:Outlook)?CalDavSynchronizer[-_](\d+(?:\.\d+){1,3})[^\"'<>\s]*?\.zip)",
                    re.IGNORECASE
                )
                for url, version in pattern.findall(html):
                    filename = urlparse(url).path.rsplit("/", 1)[-1]
                    candidates[tuple(int(x) for x in version.split("."))] = (version, url, filename)
            if not candidates:
                raise ValueError("Could not find a versioned CalDavSynchronizer ZIP on the official downloads page")

            version, url, filename = candidates[max(candidates)]
            self.env.update({
                "version": version,
                "caldav_zip_url": url,
                "caldav_zip_filename": filename,
            })
            self.output(f"Latest CalDavSynchronizer Windows version: {version}")
            self.output(f"ZIP: {url}")
        except Exception as exc:
            raise ProcessorError(f"CalDavSynchronizer version discovery failed: {exc}") from exc


if __name__ == "__main__":
    PROCESSOR = CalDavSynchronizerWinProvider()
    PROCESSOR.execute_shell()
