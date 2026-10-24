#!/usr/bin/env python3
"""Migrate legacy Munki pkginfo and give new imports architecture-specific filenames."""
import os
import plistlib
import re
from autopkglib import Processor, ProcessorError

class DYMOMunkiArchPkginfo(Processor):
    description = __doc__
    input_variables = {
        'ACTION': {'required': True, 'description': 'preflight or finalize'},
        'MUNKI_REPO': {'required': True, 'description': 'Local Munki repository path'},
        'repo_subdirectory': {'required': True, 'description': 'Subdirectory of pkgsinfo'},
        'version': {'required': True, 'description': 'Version from XML'},
        'munki_arch': {'required': True, 'description': 'arm64 or x86_64'},
        'pkginfo_repo_path': {'required': False, 'description': 'Path output by MunkiImporter'},
    }
    output_variables = {'pkginfo_repo_path': {'description': 'Final architecture-specific pkginfo path'}}

    def main(self):
        action = self.env['ACTION']
        arch = self.env['munki_arch']
        version = self.env['version']
        if action not in ('preflight', 'finalize') or arch not in ('arm64', 'x86_64'):
            raise ProcessorError('Invalid ACTION or architecture')
        if not re.fullmatch(r'\d+(?:\.\d+){3}', version):
            raise ProcessorError('Invalid version')
        repo = os.path.realpath(self.env['MUNKI_REPO'])
        subdir = self.env['repo_subdirectory']
        if os.path.isabs(subdir) or '..' in subdir.split('/'):
            raise ProcessorError('Unsafe repository subdirectory')
        directory = os.path.realpath(os.path.join(repo, 'pkgsinfo', subdir))
        if os.path.commonpath((repo, directory)) != repo:
            raise ProcessorError('Unsafe repository path')
        legacy = os.path.join(directory, 'DCDMac-{}.plist'.format(version))
        target = os.path.join(directory, 'DCDMac-{}-{}.plist'.format(version, arch))
        if action == 'preflight':
            if os.path.exists(legacy):
                with open(legacy, 'rb') as f:
                    info = plistlib.load(f)
                existing_arch = info.get('supported_architectures')
                if existing_arch not in (['arm64'], ['x86_64']):
                    raise ProcessorError('Legacy pkginfo has no unambiguous architecture: {}'.format(legacy))
                existing_target = os.path.join(directory, 'DCDMac-{}-{}.plist'.format(version, existing_arch[0]))
                if os.path.exists(existing_target):
                    raise ProcessorError('Both legacy and arch-specific pkginfo exist: {}'.format(existing_target))
                os.rename(legacy, existing_target)
                self.output('Migrated legacy pkginfo to {}'.format(existing_target))
            return
        imported = self.env.get('pkginfo_repo_path', '')
        if not imported:
            self.output('MunkiImporter did not import a new item; no rename needed')
            return
        if os.path.realpath(imported) != os.path.realpath(legacy):
            raise ProcessorError('Unexpected imported pkginfo path: {}'.format(imported))
        with open(imported, 'rb') as f:
            info = plistlib.load(f)
        if info.get('name') != 'DCDMac' or info.get('supported_architectures') != [arch]:
            raise ProcessorError('Imported pkginfo has unexpected name or supported_architectures')
        if os.path.exists(target):
            raise ProcessorError('Refusing to overwrite existing architecture-specific pkginfo: {}'.format(target))
        os.rename(imported, target)
        self.env['pkginfo_repo_path'] = target
        summary = self.env.get('munki_importer_summary_result')
        if isinstance(summary, dict) and isinstance(summary.get('data'), dict):
            summary['data']['pkginfo_path'] = os.path.relpath(target, os.path.join(repo, 'pkgsinfo'))
        self.output('Architecture-specific pkginfo: {}'.format(target))

if __name__ == '__main__':
    PROCESSOR = DYMOMunkiArchPkginfo()
    PROCESSOR.execute_shell()
