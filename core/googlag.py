"""
Googlag Bucket Downloader Module.
Handles secure APK acquisition via apkeep and supports Base64 device properties.
"""

import base64
import glob
import os
import shutil
import subprocess
import tempfile
from typing import Optional, List


class GooglagDownloader:
    """Securely interacts with Googlag Bucket to download target packages."""

    def __init__(self, email: str, aas_token: str, device_b64: Optional[str] = None):
        """
        Initializes the downloader with required credentials.

        Args:
            email (str): Googlag account email.
            aas_token (str): AAS token for authentication.
            device_b64 (Optional[str]): Base64 encoded device properties string.
        """
        self.email = email
        self.aas_token = aas_token
        self.device_b64 = device_b64

    def verify_environment(self) -> bool:
        """
        Validates the execution environment to ensure all external dependencies
        required by the downloader are present in the system.

        Returns:
            bool: True if dependencies are satisfied, False otherwise.
        """
        if shutil.which("apkeep") is None:
            print("[FATAL] The 'apkeep' binary was not found in the system PATH.")
            return False
        return True

    def _find_and_package_apk(self, tmp_dir: str, dl_dir: str, pkg_name: str) -> Optional[str]:
        """
        Finds the downloaded artifact and packages split APKs if necessary.
        """
        for ext in ("*.xapk", "*.apkm", "*.apks", "*.zip"):
            found = glob.glob(os.path.join(tmp_dir, ext))
            if found:
                dst = os.path.join(dl_dir, os.path.basename(found[0]))
                shutil.copy2(found[0], dst)
                return dst

        apk_files = glob.glob(os.path.join(tmp_dir, "*.apk"))
        if apk_files:
            if len(apk_files) == 1:
                dst = os.path.join(dl_dir, os.path.basename(apk_files[0]))
                shutil.copy2(apk_files[0], dst)
                return dst

            pack_dir = os.path.join(tmp_dir, "split_pack")
            os.makedirs(pack_dir, exist_ok=True)
            for apk in apk_files:
                shutil.move(apk, pack_dir)

            base_name = os.path.join(dl_dir, pkg_name)
            shutil.make_archive(base_name, "zip", pack_dir)
            dst_apks = f"{base_name}.apks"
            os.replace(f"{base_name}.zip", dst_apks)
            return dst_apks

        for item in os.listdir(tmp_dir):
            item_path = os.path.join(tmp_dir, item)
            if os.path.isdir(item_path):
                base_name = os.path.join(dl_dir, item)
                shutil.make_archive(base_name, "zip", item_path)
                dst_apks = f"{base_name}.apks"
                os.replace(f"{base_name}.zip", dst_apks)
                return dst_apks

        return None

    def _build_command(self, pkg_name: str, tmp_dir: str) -> List[str]:
        """
        Constructs the apkeep CLI command string with dynamic device properties.
        """
        # Note: The '-d google-play' argument remains unchanged because the
        # apkeep upstream binary strictly requires this identifier to function.
        cmd = [
            "apkeep",
            "-a", pkg_name,
            "-d", "google-play",
            "-e", self.email,
            "-t", self.aas_token
        ]

        options = ["split_apk=true"]

        if self.device_b64:
            try:
                props_path = os.path.join(tmp_dir, "device.properties")
                with open(props_path, "wb") as f_obj:
                    f_obj.write(base64.b64decode(self.device_b64))
                options.extend(["device=default", f"device_properties_file={props_path}"])
            except (ValueError, TypeError) as err:
                print(f"[WARN] Failed to decode Base64 device properties: {err}. Using default.")

        cmd.extend(["-o", ",".join(options)])
        cmd.append(tmp_dir)

        return cmd

    def download(self, pkg_name: str, output_dir: str) -> Optional[str]:
        """
        Executes the download process using a temporary staging directory.

        Args:
            pkg_name (str): The target application package name.
            output_dir (str): The final destination for the downloaded file.

        Returns:
            Optional[str]: The absolute path to the downloaded file, or None if failed.
        """
        os.makedirs(output_dir, exist_ok=True)

        with tempfile.TemporaryDirectory(prefix="apkeep-") as tmp:
            try:
                cmd = self._build_command(pkg_name, tmp)
                result = subprocess.run(cmd, capture_output=True, text=True, check=False)

                if result.returncode != 0:
                    print(f"[ERROR] Failed to fetch {pkg_name}: {result.stderr.strip()}")
                    return None

                copied_file = self._find_and_package_apk(tmp, output_dir, pkg_name)
                if not copied_file:
                    print(f"[WARN] No valid APK payload found for {pkg_name}.")
                    return None

                return copied_file

            except OSError as err:
                print(f"[FATAL] System error during execution: {err}")
                return None
