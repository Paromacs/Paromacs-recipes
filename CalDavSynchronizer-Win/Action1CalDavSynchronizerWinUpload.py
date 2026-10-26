#!/usr/bin/env python3
"""Add the discovered CalDavSynchronizer MSI to its existing Action1 package."""
from pathlib import Path
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen
from urllib.error import HTTPError
import json
import ssl

import certifi
from autopkglib import Processor, ProcessorError

CHUNK_SIZE = 10 * 1024 * 1024
PLATFORM = "Windows_64"
PATH_VARIABLE = "caldav_msi_path"


class Action1CalDavSynchronizerWinUpload(Processor):
    description = __doc__
    input_variables = {
        "version": {"required": True, "description": "Version discovered from the official CalDavSynchronizer download page."},
        "caldav_msi_path": {"required": True, "description": "Downloaded and validated MSI path."},
        "ACTION1_BASE_URL": {"required": True, "description": "Action1 API base URL, e.g. EU https://app.eu.action1.com/api/3.0."},
        "ACTION1_ORG_ID": {"required": True, "description": "Action1 organization ID."},
        "ACTION1_CLIENT_ID": {"required": True, "description": "Action1 OAuth client ID."},
        "ACTION1_CLIENT_SECRET": {"required": True, "description": "Action1 OAuth client secret; do not commit it to recipes or source control."},
        "ACTION1_PACKAGE_NAME": {"required": False, "description": "Existing Action1 package name; defaults to CalDavSynchronizer."},
        "ACTION1_DRY_RUN": {"required": False, "description": "true means inspect only and do not change Action1."},
    }
    output_variables = {
        "action1_uploaded_version": {"description": "Version present and verified in Action1."},
    }

    class Response:
        def __init__(self, status_code, headers, body):
            self.status_code, self.headers, self.body = status_code, headers, body

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
        valid = (200 <= result.status_code < 300) if allowed is None else result.status_code in allowed
        if not valid:
            raise RuntimeError(f"HTTP {result.status_code} for {method} {url.split('?')[0]}: {result.text[:1000]}")
        return result

    def request(self, method, path, *, payload=None, params=None, headers=None, data=None, allowed=None):
        request_headers = {"Authorization": f"Bearer {self.token}", "Accept": "application/json"}
        if payload is not None:
            request_headers["Content-Type"] = "application/json"
            data = json.dumps(payload).encode("utf-8")
        if headers:
            request_headers.update(headers)
        url = self.base + path
        if params:
            url += ("&" if "?" in url else "?") + urlencode(params)
        return self.http(method, url, headers=request_headers, data=data, allowed=allowed)

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
        if not isinstance(value, str) or not value or any(not p.isdigit() for p in value.split(".")):
            raise RuntimeError(f"Unsupported non-numeric version string: {value!r}")
        return tuple(int(part) for part in value.split("."))

    @staticmethod
    def template_payload(template, version):
        # Copy the installation behavior from the package's latest existing version.
        fields = ("app_name_match", "install_type", "os", "reboot_exit_codes",
                  "security_severity", "update_type", "success_exit_codes")
        payload = {"version": version}
        for key in fields:
            if key not in template:
                raise RuntimeError(f"Action1 version template is missing required field: {key}")
            payload[key] = template[key]
        payload["additional_actions"] = template.get("additional_actions", [])
        if template.get("silent_install_switches"):
            payload["silent_install_switches"] = template["silent_install_switches"]
        # Leave release_date to Action1; Advitronics does not publish a reliable release date on the page.
        return payload

    def upload(self, package_id, version_id, path):
        size = path.stat().st_size
        if not size:
            raise RuntimeError(f"Empty MSI: {path}")
        api_path = f"/software-repository/{self.org}/{package_id}/versions/{version_id}"
        init = self.request("POST", api_path + "/upload", params={
            "package_id": package_id, "version_id": version_id, "platform": PLATFORM},
            headers={"Content-Type": "application/json",
                     "X-Upload-Content-Type": "application/octet-stream",
                     "X-Upload-Content-Length": str(size)},
            data=b"", allowed={200, 201, 202, 308})
        upload_url = init.headers.get("X-Upload-Location")
        if not upload_url:
            raise RuntimeError("Action1 did not return X-Upload-Location for the MSI upload")
        if urlparse(upload_url).scheme != "https":
            raise RuntimeError("Action1 returned a non-HTTPS upload URL")
        uploaded = 0
        with path.open("rb") as stream:
            while uploaded < size:
                chunk = stream.read(min(CHUNK_SIZE, size - uploaded))
                if not chunk:
                    raise RuntimeError("Unexpected end of MSI file")
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
                        raise RuntimeError(f"Invalid upload Range header: {response.headers.get('Range')}")
                    if end + 1 == size:
                        raise RuntimeError("Action1 returned HTTP 308 for the final upload chunk")
                elif end + 1 != size:
                    raise RuntimeError(f"Upload ended early: HTTP {response.status_code}: {response.text[:500]}")
                uploaded = end + 1
        self.output(f"Uploaded {PLATFORM}: {path.name} ({size} bytes)")

    def main(self):
        try:
            self.base = self.env["ACTION1_BASE_URL"].rstrip("/")
            self.org = self.env["ACTION1_ORG_ID"].strip()
            client_id = self.env["ACTION1_CLIENT_ID"].strip()
            client_secret = self.env["ACTION1_CLIENT_SECRET"]
            version = self.env["version"].strip()
            self.version_key(version)
            name = self.env.get("ACTION1_PACKAGE_NAME", "CalDavSynchronizer").strip()
            dry_run = str(self.env.get("ACTION1_DRY_RUN", "true")).lower() in ("true", "1", "yes")
            path = Path(self.env[PATH_VARIABLE])
            if not path.is_file() or path.stat().st_size < 1024:
                raise RuntimeError(f"MSI file is missing or too small: {path}")
            with path.open("rb") as stream:
                if stream.read(8) != bytes.fromhex("D0CF11E0A1B11AE1"):
                    raise RuntimeError("Downloaded file does not have the expected MSI/OLE signature")

            self.ssl_context = ssl.create_default_context(cafile=certifi.where())
            auth = self.http("POST", self.base + "/oauth2/token",
                data=urlencode({"client_id": client_id, "client_secret": client_secret}).encode("utf-8"),
                headers={"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"}, timeout=30)
            self.token = auth.json()["access_token"]

            package = self.find_package(name)
            if not package:
                raise RuntimeError(f"Existing Action1 package not found: {name!r}; refusing to create a new package")
            package_id = package["id"]
            details = self.get(f"/software-repository/{self.org}/{package_id}?fields=versions")
            versions = details.get("versions", [])
            if not versions:
                raise RuntimeError("Existing Action1 package has no versions to use as an installation template")
            latest = max(versions, key=lambda item: self.version_key(item["version"]))
            target = next((item for item in versions if item.get("version") == version), None)
            self.output(f"Action1 package: {name} ({package_id})")
            self.output(f"Action1 latest version: {latest['version']}; vendor version: {version}")
            if self.version_key(version) < self.version_key(latest["version"]):
                self.output("Action1 already has a newer version; skipping to avoid downgrading the package")
                return

            base_path = f"/software-repository/{self.org}/{package_id}/versions"
            if target:
                target_id = target["id"]
                current = self.get(f"{base_path}/{target_id}")
                metadata = current.get("file_name") or {}
                if isinstance(metadata.get(PLATFORM), dict) and metadata[PLATFORM].get("name") == path.name and metadata[PLATFORM].get("type") == "cloud":
                    self.output(f"Version {version} already has {path.name}; nothing to upload")
                    self.env["action1_uploaded_version"] = version
                    return
                self.output(f"Version {version} already exists but the MSI filename is not configured; will repair it")
            else:
                template = self.get(f"{base_path}/{latest['id']}")
                payload = self.template_payload(template, version)
                if dry_run:
                    self.output(f"DRY RUN: would create version {version} in existing package {name} and upload {path.name}")
                    return
                created = self.request("POST", base_path, payload=payload).json()
                target_id = created["id"]
                metadata = {}
                self.output(f"Created Action1 version {version}")

            if dry_run:
                self.output(f"DRY RUN: would upload {path.name} to Action1 version {version}")
                return
            self.upload(package_id, target_id, path)
            updated = dict(metadata)
            updated[PLATFORM] = {"name": path.name, "type": "cloud"}
            self.request("PATCH", f"{base_path}/{target_id}", payload={"file_name": updated})
            verified = self.get(f"{base_path}/{target_id}").get("file_name") or {}
            item = verified.get(PLATFORM)
            if not isinstance(item, dict) or item.get("name") != path.name or item.get("type") != "cloud":
                raise RuntimeError("Action1 version verification failed after upload")
            self.env["action1_uploaded_version"] = version
            self.output(f"Action1 {name} {version}: MSI upload and metadata verified")
        except Exception as exc:
            raise ProcessorError(f"Action1 CalDavSynchronizer Windows sync failed: {exc}") from exc


if __name__ == "__main__":
    PROCESSOR = Action1CalDavSynchronizerWinUpload()
    PROCESSOR.execute_shell()
