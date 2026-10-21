#!/usr/bin/env python3
"""Publish the cached PearPie Windows x64 MSI to the existing Action1 package."""
import os
from pathlib import Path
from datetime import date
from urllib.parse import urlparse

import json
import ssl
import certifi
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from urllib.parse import urlencode
from autopkglib import Processor, ProcessorError

CHUNK_SIZE = 10 * 1024 * 1024
PLATFORMS = (("Windows_64", "pearpie_msi_path"),)


class Action1PearPieUpload(Processor):
    description = __doc__
    input_variables = {
        "version": {"required": True, "description": "Version discovered by PearPie release feed."},
        "pearpie_release_date": {"required": True, "description": "YYYY-MM-DD from PearPie published_at."},
        "pearpie_msi_path": {"required": True, "description": "SHA-256 verified Windows x64 MSI."},
        "ACTION1_BASE_URL": {"required": True, "description": "Action1 API base URL."},
        "ACTION1_ORG_ID": {"required": True, "description": "Action1 organization ID."},
        "ACTION1_CLIENT_ID": {"required": True, "description": "OAuth client ID."},
        "ACTION1_CLIENT_SECRET": {"required": True, "description": "OAuth client secret. Do not store in recipe."},
        "ACTION1_PACKAGE_NAME": {"required": False, "description": "Existing package name; default PearPie."},
        "ACTION1_DRY_RUN": {"required": False, "description": "Set true to inspect without modifying Action1."},
    }
    output_variables = {"action1_uploaded_version": {"description": "Version synchronized with Action1."}}

    class Response:
        def __init__(self, status_code, headers, body):
            self.status_code = status_code
            self.headers = headers
            self.body = body

        @property
        def text(self):
            return self.body.decode("utf-8", errors="replace")

        def json(self):
            return json.loads(self.body)

    def http(self, method, url, *, headers=None, data=None, allowed=None, timeout=120):
        request = Request(url, data=data, headers=headers or {}, method=method)
        try:
            with urlopen(request, timeout=timeout, context=self.ssl_context) as response:
                result = self.Response(response.status, response.headers, response.read())
        except HTTPError as error:
            result = self.Response(error.code, error.headers, error.read())
        if allowed is None:
            valid = 200 <= result.status_code < 300
        else:
            valid = result.status_code in allowed
        if not valid:
            raise RuntimeError(f"HTTP {result.status_code} for {method} {url.split('?')[0]}: {result.text[:1000]}")
        return result

    def request(self, method, path, *, payload=None, params=None, headers=None, data=None, allowed=None):
        h = {"Authorization": f"Bearer {self.token}", "Accept": "application/json"}
        if payload is not None:
            h["Content-Type"] = "application/json"
            data = json.dumps(payload).encode("utf-8")
        if headers:
            h.update(headers)
        url = self.base + path
        if params:
            url += ("&" if "?" in url else "?") + urlencode(params)
        return self.http(method, url, headers=h, data=data, allowed=allowed)

    def get(self, path):
        return self.request("GET", path).json()

    def find_package(self, name):
        offset = 0
        while True:
            result = self.get(f"/software-repository/{self.org}?from={offset}&limit=50")
            items = result.get("items", [])
            for item in items:
                if item.get("name", "").casefold() == name.casefold():
                    return item
            if len(items) < 50:
                return None
            offset += 50

    @staticmethod
    def version_key(value):
        return tuple(int(x) for x in value.split("."))

    @staticmethod
    def template_payload(template, version, release_date):
        fields = ("app_name_match", "install_type", "os", "reboot_exit_codes",
                  "security_severity", "update_type", "success_exit_codes")
        payload = {"version": version}
        for key in fields:
            if key not in template:
                raise RuntimeError(f"Action1 template missing required field: {key}")
            payload[key] = template[key]
        payload["additional_actions"] = template.get("additional_actions", [])
        if template.get("silent_install_switches"):
            payload["silent_install_switches"] = template["silent_install_switches"]
        payload["release_date"] = release_date
        return payload

    def upload(self, package_id, version_id, platform, path):
        size = path.stat().st_size
        if not size:
            raise RuntimeError(f"Empty installer: {path}")
        api_path = f"/software-repository/{self.org}/{package_id}/versions/{version_id}"
        init = self.request("POST", api_path + "/upload", params={
            "package_id": package_id, "version_id": version_id, "platform": platform},
            headers={"Content-Type": "application/json",
                     "X-Upload-Content-Type": "application/octet-stream",
                     "X-Upload-Content-Length": str(size)},
            data=b"", allowed={200, 201, 202, 308})
        upload_url = init.headers.get("X-Upload-Location")
        if not upload_url:
            raise RuntimeError(f"No X-Upload-Location for {platform}")
        parsed = urlparse(upload_url)
        if parsed.scheme != "https":
            raise RuntimeError("Action1 returned a non-HTTPS upload URL")
        uploaded = 0
        with path.open("rb") as stream:
            while uploaded < size:
                chunk = stream.read(min(CHUNK_SIZE, size - uploaded))
                if not chunk:
                    raise RuntimeError("Unexpected end of file")
                start, end = uploaded, uploaded + len(chunk) - 1
                response = self.http("PUT", upload_url, data=chunk, headers={
                    "Authorization": f"Bearer {self.token}",
                    "Content-Type": "application/octet-stream",
                    "Content-Length": str(len(chunk)),
                    "Content-Range": f"bytes {start}-{end}/{size}"},
                    allowed={200, 201, 202, 204, 308})
                if response.status_code == 308:
                    expected = f"bytes={start}-{end}"
                    if response.headers.get("Range") != expected:
                        raise RuntimeError(f"Invalid Action1 upload Range for {platform}: {response.headers.get('Range')}")
                    if end + 1 == size:
                        raise RuntimeError("Action1 returned 308 for final chunk")
                elif end + 1 != size:
                    raise RuntimeError(f"Action1 upload error for {platform}: HTTP {response.status_code}: {response.text[:500]}")
                uploaded = end + 1
        self.output(f"Uploaded {platform}: {path.name} ({size} bytes)")

    def main(self):
        try:
            self.base = self.env["ACTION1_BASE_URL"].rstrip("/")
            self.org = self.env["ACTION1_ORG_ID"]
            client_id = self.env["ACTION1_CLIENT_ID"]
            client_secret = self.env["ACTION1_CLIENT_SECRET"]
            version = self.env["version"]
            feed_date = str(self.env.get("pearpie_release_date", "")).strip()
            if feed_date:
                try:
                    date.fromisoformat(feed_date)
                except ValueError as exc:
                    raise RuntimeError(f"Invalid PearPie published_at date: {feed_date}") from exc
            release_date = feed_date or date.today().isoformat()
            name = self.env.get("ACTION1_PACKAGE_NAME", "PearPie")
            dry_run = str(self.env.get("ACTION1_DRY_RUN", "false")).lower() in ("true", "1", "yes")
            paths = {platform: Path(self.env[key]) for platform, key in PLATFORMS}
            for platform, path in paths.items():
                if not path.is_file():
                    raise RuntimeError(f"Missing {platform} installer: {path}")
            self.ssl_context = ssl.create_default_context(cafile=certifi.where())
            auth = self.http("POST", self.base + "/oauth2/token",
                             data=urlencode({"client_id": client_id,
                                             "client_secret": client_secret}).encode("utf-8"),
                             headers={"Content-Type": "application/x-www-form-urlencoded",
                                      "Accept": "application/json"}, timeout=30)
            self.token = auth.json()["access_token"]
            package = self.find_package(name)
            if not package:
                raise RuntimeError(f"Action1 package not found: {name}")
            package_id = package["id"]
            details = self.get(f"/software-repository/{self.org}/{package_id}?fields=versions")
            versions = details.get("versions", [])
            if not versions:
                raise RuntimeError("Action1 package has no existing versions to clone")
            latest = max(versions, key=lambda item: self.version_key(item["version"]))
            target = next((item for item in versions if item["version"] == version), None)
            self.output(f"Action1 latest: {latest['version']}; PearPie latest: {version}")
            if self.version_key(version) < self.version_key(latest["version"]):
                self.output("Action1 already contains a newer version; skipping")
                return
            base_path = f"/software-repository/{self.org}/{package_id}/versions"
            if target:
                # Existing version may be complete or a partial failed run.
                target_id = target["id"]
                current = self.get(f"{base_path}/{target_id}")
                metadata = current.get("file_name") or {}
                existing_date = current.get("release_date")
                if not existing_date or existing_date == "N/A":
                    if dry_run:
                        self.output(f"DRY RUN: would set release date to {release_date} ({'PearPie release feed' if feed_date else 'today'})")
                    else:
                        self.request("PATCH", f"{base_path}/{target_id}", payload={"release_date": release_date})
                        self.output(f"Updated release date: {release_date} ({'PearPie release feed' if feed_date else 'today'})")
                else:
                    self.output(f"Keeping existing release date: {existing_date}")
                if all(isinstance(metadata.get(platform), dict) and
                       metadata[platform].get("name") == path.name and
                       metadata[platform].get("type") == "cloud"
                       for platform, path in paths.items()):
                    self.output("Installer filename already configured; no upload needed")
                    self.env["action1_uploaded_version"] = version
                    return
                self.output("Existing version is incomplete; uploading missing installer")
            else:
                template = self.get(f"{base_path}/{latest['id']}")
                payload = self.template_payload(template, version, release_date)
                if dry_run:
                    self.output(f"DRY RUN: would create {name} version {version} and upload installer")
                    return
                created = self.request("POST", base_path, payload=payload).json()
                target_id = created["id"]
                metadata = {}
                self.output(f"Created Action1 version {version} (release date {release_date})")
            if dry_run:
                self.output(f"DRY RUN: would repair {name} version {version} and upload missing installer")
                return
            # Preserve existing platform metadata on partial retries.
            updated = dict(metadata)
            for platform, path in paths.items():
                if isinstance(updated.get(platform), dict) and updated[platform].get("name") == path.name and updated[platform].get("type") == "cloud":
                    self.output(f"Keeping existing {platform} installer")
                    continue
                self.upload(package_id, target_id, platform, path)
                updated[platform] = {"name": path.name, "type": "cloud"}
                self.request("PATCH", f"{base_path}/{target_id}", payload={"file_name": updated})
                self.output(f"Configured {platform} installer")
            verified = self.get(f"{base_path}/{target_id}").get("file_name") or {}
            if not all(isinstance(verified.get(platform), dict) and verified[platform].get("name") == path.name and verified[platform].get("type") == "cloud" for platform, path in paths.items()):
                raise RuntimeError("Action1 version verification failed")
            self.env["action1_uploaded_version"] = version
            self.output(f"Action1 PearPie {version}: installer configured")
        except Exception as error:
            raise ProcessorError(f"Action1 PearPie sync failed: {error}") from error


if __name__ == "__main__":
    PROCESSOR = Action1PearPieUpload()
    PROCESSOR.execute_shell()
