#!/usr/bin/env python3
"""Complete override-editable Munki pkginfo with DYMO version and architecture."""
from copy import deepcopy
from autopkglib import Processor, ProcessorError

class DYMOPkginfoResolver(Processor):
    description = __doc__
    input_variables = {
        'pkginfo': {'required': True, 'description': 'Editable Munki pkginfo dictionary'},
        'version': {'required': True, 'description': 'Version discovered from DYMO XML'},
        'munki_arch': {'required': True, 'description': 'arm64 or x86_64'},
    }
    output_variables = {'pkginfo': {'description': 'Resolved Munki pkginfo dictionary'}}

    def main(self):
        info = self.env.get('pkginfo')
        version = self.env.get('version')
        arch = self.env.get('munki_arch')
        if not isinstance(info, dict):
            raise ProcessorError('pkginfo must be a dictionary in recipe Input/override')
        if arch not in ('arm64', 'x86_64') or not version:
            raise ProcessorError('Missing or invalid DYMO version/architecture')
        info = deepcopy(info)
        info['version'] = version
        info['supported_architectures'] = [arch]
        installs = info.get('installs', [])
        if not isinstance(installs, list):
            raise ProcessorError('pkginfo.installs must be an array')
        for item in installs:
            if isinstance(item, dict) and item.get('path') == '/Applications/DYMO Connect.app':
                item['CFBundleShortVersionString'] = version
                item['CFBundleVersion'] = version
        if not isinstance(info.get('catalogs'), list):
            raise ProcessorError('pkginfo.catalogs must be an array')
        self.env['pkginfo'] = info
        self.output('Resolved pkginfo: version={}, architecture={}, catalogs={}'.format(version, arch, info['catalogs']))

if __name__ == '__main__':
    PROCESSOR = DYMOPkginfoResolver()
    PROCESSOR.execute_shell()
