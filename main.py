"""
Main Execution Script.
Reads target applications from a CSV, downloads them via Googlag Bucket,
and normalizes the filenames for GitHub Releases.
"""

import os
import sys
from zipfile import ZipFile
import pandas as pd
from androguard.core.bytecodes.apk import APK
from core.googlag import GooglagDownloader


def extract_version_name(file_path: str) -> str:
    """
    Extracts the human-readable version string from an APK or APKS structure.

    Args:
        file_path (str): The path to the downloaded APK or APKS file.

    Returns:
        str: The extracted version name, or 'unknown' if parsing fails.
    """
    try:
        if file_path.endswith('.apk'):
            apk_obj = APK(file_path)
            return str(apk_obj.get_androidversion_name())

        if file_path.endswith('.apks') or file_path.endswith('.xapk'):
            # Extract the base APK from the split bundle to read the manifest
            with ZipFile(file_path, 'r') as bundle:
                base_apk_name = next(
                    (f for f in bundle.namelist() if "base.apk" in f or "base.master.apk" in f), 
                    None
                )
                if base_apk_name:
                    apk_data = bundle.read(base_apk_name)
                    apk_obj = APK(apk_data, raw=True)
                    return str(apk_obj.get_androidversion_name())
    except (ValueError, OSError, KeyError, ImportError) as err:
        print(f"[WARN] Version parsing failed for {file_path}: {err}")
        
    return "unknown"


def main() -> None:
    """
    Entry point for the automation workflow.
    Validates environment variables, parses the input dataset, and triggers downloads.
    """
    email = os.getenv("PLAY_EMAIL")
    aas = os.getenv("PLAY_AAS_TOKEN")
    dev_b64 = os.getenv("DEVICE_B64")

    if not email or not aas:
        print("[FATAL] Required credentials (PLAY_EMAIL, PLAY_AAS_TOKEN) are missing.")
        sys.exit(1)

    dataset_path = "apps.csv"
    if not os.path.exists(dataset_path):
        print(f"[FATAL] Configuration file {dataset_path} not found.")
        sys.exit(1)

    try:
        target_apps = pd.read_csv(dataset_path)
    except pd.errors.EmptyDataError:
        print("[FATAL] The provided CSV file is empty.")
        sys.exit(1)

    downloader = GooglagDownloader(email, aas, dev_b64)
    output_dir = os.path.join(os.getcwd(), "Release_Output")
    os.makedirs(output_dir, exist_ok=True)

    for _, row in target_apps.iterrows():
        app_name = str(row['app_name']).replace(' ', '_')
        pkg_name = str(row['package_name'])
        arch = str(row['arch'])

        print(f"\n[INFO] Processing: {app_name} ({pkg_name})")
        
        dl_path = downloader.download(pkg_name, output_dir)
        if not dl_path:
            continue

        version = extract_version_name(dl_path)
        ext = ".apks" if dl_path.endswith(".apks") else ".apk"
        
        # Format: app name_package name_version_architecture
        final_filename = f"{app_name}_{pkg_name}_{version}_{arch}{ext}"
        final_path = os.path.join(output_dir, final_filename)
        
        os.replace(dl_path, final_path)
        print(f"[SUCCESS] Saved artifact: {final_filename}")


if __name__ == "__main__":
    main()
