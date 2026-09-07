"""
Main Execution Script.
Reads target applications from a CSV, downloads them via Googlag Bucket,
and normalizes the filenames for GitHub Releases.
"""

import os
import sys
from zipfile import ZipFile
import pandas as pd

# ---------------------------------------------------------
# Dynamic module resolution for Androguard (Bulletproof)
# Resolves cross-version compatibility between v3.x and v4.x
# without enforcing strict dependency version constraints.
# ---------------------------------------------------------
try:
    # Modern import structure for Androguard v4.0.0 and above
    from androguard.core.apk import APK
except ImportError:
    # Legacy fallback path for Androguard versions below v4.0.0
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
        # Standard stand-alone APK processing
        if file_path.endswith('.apk'):
            apk_obj = APK(file_path)
            return str(apk_obj.get_androidversion_name())

        # Split APK bundle processing (APKS or XAPK formats)
        if file_path.endswith('.apks') or file_path.endswith('.xapk'):
            # Iterate dynamically over all internal APKs to find the primary manifest
            with ZipFile(file_path, 'r') as bundle:
                internal_apks = [f for f in bundle.namelist() if f.endswith('.apk')]
                for apk_name in internal_apks:
                    try:
                        apk_data = bundle.read(apk_name)
                        apk_obj = APK(apk_data, raw=True)
                        version_name = apk_obj.get_androidversion_name()
                        if version_name:
                            return str(version_name)
                    except (ValueError, KeyError, IndexError, TypeError):
                        # Safely bypass configuration splits or invalid artifacts
                        # that do not contain standard version manifest components.
                        continue

    except (ValueError, OSError, KeyError, ImportError) as err:
        print(f"[WARN] Version parsing failed for {file_path}: {err}")

    return "unknown"


def process_target_app(row: pd.Series, downloader: GooglagDownloader, output_dir: str) -> None:
    """
    Processes a single application entry from the dataset.
    Downloads the artifact and normalizes its filename.

    Args:
        row (pd.Series): The dataset row containing application metadata.
        downloader (GooglagDownloader): The instantiated downloader client.
        output_dir (str): The directory where artifacts are saved.
    """
    app_name = str(row['app_name']).replace(' ', '_')
    pkg_name = str(row['package_name'])
    arch = str(row['arch'])

    print(f"\n[INFO] Processing: {app_name} ({pkg_name})")

    dl_path = downloader.download(pkg_name, output_dir)
    if not dl_path:
        return

    # Extract semantics and build the standardized artifact filename
    version = extract_version_name(dl_path)
    ext = ".apks" if dl_path.endswith(".apks") else ".apk"

    # Format mapping: AppName_PackageName_Version_Architecture.extension
    final_filename = f"{app_name}_{pkg_name}_{version}_{arch}{ext}"
    final_path = os.path.join(output_dir, final_filename)

    os.replace(dl_path, final_path)
    print(f"[SUCCESS] Saved artifact: {final_filename}")


def main() -> None:
    """
    Entry point for the automation workflow.
    Validates environment variables, parses the input dataset, and triggers downloads.
    """
    email = os.getenv("PLAY_EMAIL")
    aas = os.getenv("PLAY_AAS_TOKEN")
    dev_b64 = os.getenv("DEVICE_B64")

    # Validate essential environment variables
    if not email or not aas:
        print("[FATAL] Required credentials (PLAY_EMAIL, PLAY_AAS_TOKEN) are missing.")
        sys.exit(1)

    dataset_path = "apps.csv"

    # Ensure the target CSV index exists before proceeding
    if not os.path.exists(dataset_path):
        print(f"[FATAL] Configuration file {dataset_path} not found.")
        sys.exit(1)

    # Safely parse the CSV dataset
    try:
        target_apps = pd.read_csv(dataset_path)
    except pd.errors.EmptyDataError:
        print("[FATAL] The provided CSV file is empty.")
        sys.exit(1)

    # Initialize the core downloader mechanism
    downloader = GooglagDownloader(email, aas, dev_b64)
    output_dir = os.path.join(os.getcwd(), "Release_Output")
    os.makedirs(output_dir, exist_ok=True)

    # Iterate through the application index and process each entry
    for _, row in target_apps.iterrows():
        process_target_app(row, downloader, output_dir)


if __name__ == "__main__":
    main()
