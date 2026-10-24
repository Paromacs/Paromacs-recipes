#!/usr/bin/env python3
"""Discover the current DYMO Connect macOS version from DYMO's public XML update manifest."""
import re
import subprocess
import xml.etree.ElementTree as ET
from urllib.parse import urlparse
from autopkglib import Processor, ProcessorError

MANIFEST = 'https://dymoreleasecontent.blob.core.windows.net/dymo-release/Software/dymoconnect/updates/Mac/Updates.xml'
HOST = 'dymoreleasecontent.blob.core.windows.net'
BASE = 'https://dymoreleasecontent.blob.core.windows.net/dymo-release/DCDMAC/'
VERSION_RE = re.compile(r'^\d+(?:\.\d+){3}$')


def discover(xml_data, arch):
    if arch not in ('arm64', 'x86_64'):
        raise ValueError('ARCH must be arm64 or x86_64')
    root = ET.fromstring(xml_data)
    if root.tag != 'Updates':
        raise ValueError('Unexpected XML root (expected Updates)')
    versions = []
    for item in root.findall('./DYMOConnect'):
        version = (item.findtext('Version') or '').strip()
        if VERSION_RE.fullmatch(version):
            versions.append(version)
    if not versions:
        raise ValueError('No DYMOConnect Version in XML')
    version = max(versions, key=lambda v: tuple(map(int, v.split('.'))))
    suffix = {'arm64': 'Arm64', 'x86_64': 'X64'}[arch]
    filename = 'DCDMac{}-{}.pkg'.format(version, suffix)
    return version, BASE + filename, filename


class DYMOConnectMacInfoProvider(Processor):
    description = __doc__
    input_variables = {
        'ARCH': {'required': True, 'description': 'arm64 or x86_64'},
        'DYMO_MAC_UPDATES_XML': {'required': False, 'description': 'DYMO macOS XML manifest URL'},
    }
    output_variables = {
        'version': {'description': 'Version from DYMO update manifest'},
        'url': {'description': 'Architecture-specific PKG URL'},
        'pkg_filename': {'description': 'PKG filename'},
        'munki_arch': {'description': 'Munki supported_architectures value'},
    }

    def main(self):
        try:
            arch = self.env['ARCH'].strip()
            manifest = self.env.get('DYMO_MAC_UPDATES_XML', MANIFEST)
            parsed = urlparse(manifest)
            if parsed.scheme != 'https' or parsed.hostname != HOST:
                raise ValueError('Manifest must be HTTPS on the official DYMO release host')
            # Use macOS curl: DYMO's Azure endpoint can reject Python urllib (HTTP 403)
            # even when curl on the same Mac succeeds (HTTP 200).
            result = subprocess.run(
                ['/usr/bin/curl', '--fail', '--silent', '--show-error',
                 '--location', '--max-time', '45', '--connect-timeout', '15',
                 '--proto', '=https', '--proto-redir', '=https', manifest],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=55,
                check=False,
            )
            if result.returncode:
                raise ValueError('curl failed (exit {}): {}'.format(
                    result.returncode, result.stderr.decode('utf-8', 'replace').strip()))
            data = result.stdout
            if len(data) > 2 * 1024 * 1024:
                raise ValueError('XML manifest exceeds 2 MiB')
            version, url, filename = discover(data, arch)
            self.env.update({'version': version, 'url': url, 'pkg_filename': filename, 'munki_arch': arch})
            self.output('DYMO Connect macOS version: {}'.format(version))
            self.output('Architecture: {}; package: {}'.format(arch, filename))
        except Exception as exc:
            raise ProcessorError('DYMO macOS update discovery failed: {}'.format(exc)) from exc


if __name__ == '__main__':
    PROCESSOR = DYMOConnectMacInfoProvider()
    PROCESSOR.execute_shell()
