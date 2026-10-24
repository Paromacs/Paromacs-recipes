#!/usr/bin/python3
"""Populate dynamic Munki metadata and keep architecture-specific pkginfo filenames."""
import os
import shutil
from autopkglib import Processor, ProcessorError

class AdvitronicsConversationManagerMunkiProcessor(Processor):
    description = __doc__
    input_variables = {
        "ACTION": {"required": True, "description": "preflight, prepare, or finalize"},
        "repo_subdirectory": {"required": False, "description": "Subdirectory under pkgsinfo"},
    }
    output_variables = {}

    def _paths(self):
        repo = self.env.get("MUNKI_REPO")
        if not repo:
            raise ProcessorError("MUNKI_REPO is not set; cannot safely rename pkginfo files")
        version = self.env.get("version")
        arch = self.env.get("munki_arch")
        if not version or arch not in ("arm64", "x86_64"):
            raise ProcessorError("Expected version and munki_arch from the download recipe")
        subdir = self.env.get("repo_subdirectory", "apps/Advitronics").strip("/")
        folder = os.path.join(os.path.abspath(os.path.expanduser(repo)), "pkgsinfo", subdir)
        generic = os.path.join(folder, "ConversationManager-{}.plist".format(version))
        specific = os.path.join(folder, "ConversationManager-{}-{}.plist".format(version, arch))
        return folder, generic, specific

    def main(self):
        action = self.env["ACTION"].strip().lower()
        if action == "prepare":
            pkginfo = self.env.get("pkginfo")
            if not isinstance(pkginfo, dict):
                raise ProcessorError("Recipe Input 'pkginfo' must be a dictionary")
            arch = self.env.get("munki_arch")
            version = self.env.get("version")
            if not version or arch not in ("arm64", "x86_64"):
                raise ProcessorError("Expected version and munki_arch from the download recipe")
            pkginfo["version"] = version
            pkginfo["supported_architectures"] = [arch]
            self.env["pkginfo"] = pkginfo
            self.output("Prepared pkginfo for {} ({})".format(version, arch))
            return
        if action not in ("preflight", "finalize"):
            raise ProcessorError("Unsupported ACTION: {}".format(action))
        folder, generic, specific = self._paths()
        if action == "preflight":
            if os.path.isfile(generic):
                os.makedirs(folder, exist_ok=True)
                if os.path.exists(specific):
                    os.remove(generic)
                    self.output("Removed duplicate generic pkginfo; keeping {}".format(os.path.basename(specific)))
                else:
                    shutil.move(generic, specific)
                    self.output("Renamed existing pkginfo to {}".format(os.path.basename(specific)))
            return
        if not os.path.isdir(folder):
            raise ProcessorError("Munki pkginfo directory does not exist: {}".format(folder))
        if os.path.isfile(generic):
            if os.path.exists(specific):
                os.remove(specific)
            shutil.move(generic, specific)
            self.output("Renamed pkginfo to {}".format(os.path.basename(specific)))
        elif not os.path.isfile(specific):
            raise ProcessorError("Expected pkginfo not found: {}".format(generic))

if __name__ == "__main__":
    PROCESSOR = AdvitronicsConversationManagerMunkiProcessor()
    PROCESSOR.execute_shell()
