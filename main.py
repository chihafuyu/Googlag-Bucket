"""
Main Execution Script.
Reads target applications from a CSV, downloads them via Googlag Bucket,
normalizes filenames, and dynamically routes artifacts to GitHub and/or HuggingFace.
"""

import os
import sys
from zipfile import ZipFile
import pandas as pd

# Handle cross-version path changes between Androguard v3.x and v4.x
try:
    from androguard.core.apk import APK
except ImportError:
    from androguard.core.bytecodes.apk import APK

# Gracefully handle the optional HuggingFace dependency
try:
    from huggingface_hub import HfApi
    HF_AVAILABLE = True
except ImportError:
    HF_AVAILABLE = False

from core.googlag import GooglagDownloader


def extract_version_name(file_path: str) -> str:
    """
    Extracts the human-readable version string from an APK or APKS structure.
    """
    try:
        if file_path.endswith('.apk'):
            apk_obj = APK(file_path)
            return str(apk_obj.get_androidversion_name())

        if file_path.endswith('.apks') or file_path.endswith('.xapk'):
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
                        continue

    except (ValueError, OSError, KeyError, ImportError) as err:
        print(f"[WARN] Version parsing failed for {file_path}: {err}")

    return "unknown"


def handle_artifact_routing(final_path: str, final_filename: str, target: str) -> None:
    """
    Routes the artifact to HuggingFace and manages local file cleanup for GitHub.
    """
    upload_to_hf = target in ('both', 'huggingface')
    keep_for_github = target in ('both', 'github')

    if upload_to_hf:
        hf_token = os.getenv("HF_TOKEN")
        hf_dataset = os.getenv("HF_DATASET_ID")

        if hf_token and hf_dataset:
            if not HF_AVAILABLE:
                print("[WARN] HF_TOKEN found but huggingface_hub missing. Skipping upload.")
            else:
                print(f"[INFO] Uploading artifact to HuggingFace: {hf_dataset}")
                try:
                    api = HfApi(token=hf_token)
                    api.upload_file(
                        path_or_fileobj=final_path,
                        path_in_repo=final_filename,
                        repo_id=hf_dataset,
                        repo_type="dataset"
                    )
                    print("[SUCCESS] Artifact uploaded to HuggingFace.")
                except (ValueError, OSError, RuntimeError) as err:
                    print(f"[ERROR] HuggingFace upload failed: {err}")
        else:
            print("[WARN] HuggingFace credentials missing. Skipping upload.")

    if not keep_for_github:
        print(
            f"[INFO] Target is HuggingFace only. "
            f"Removing {final_filename} from GitHub release pool."
        )
        try:
            os.remove(final_path)
        except OSError as err:
            print(f"[WARN] Failed to purge artifact locally: {err}")


def process_target_app(row: pd.Series, downloader: GooglagDownloader, output_dir: str) -> None:
    """
    Processes a single application entry, triggers the download, and normalizes the filename.
    """
    pkg_name = str(row['package_name'])
    target = str(row.get('upload_target', 'both')).strip().lower()

    print(f"\n[INFO] Processing: {pkg_name} (Routing Target: {target})")

    dl_path = downloader.download(pkg_name, output_dir)
    if not dl_path:
        return

    version = extract_version_name(dl_path)
    ext = ".apks" if dl_path.endswith(".apks") else ".apk"
    final_filename = f"{pkg_name}_{version}{ext}"
    final_path = os.path.join(output_dir, final_filename)

    os.replace(dl_path, final_path)
    print(f"[SUCCESS] Saved primary artifact: {final_filename}")

    handle_artifact_routing(final_path, final_filename, target)


def main() -> None:
    """
    Entry point for the automation workflow.
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
        process_target_app(row, downloader, output_dir)


if __name__ == "__main__":
    main()
