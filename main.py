"""
Main Execution Script.
Reads target applications from a CSV, downloads them via Googlag Bucket,
normalizes filenames, and dynamically routes artifacts with selective proxying.
"""

import os
import sys
import random
from zipfile import ZipFile
import requests
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


def get_working_proxy() -> str:
    """
    Fetches free Indonesian proxies from a GitHub repository, tests them
    against the specific Google Play checkin endpoint, and returns the first 
    working proxy address. Returns an empty string if none are viable.
    """
    url = (
        "https://raw.githubusercontent.com/ProxyScrape/"
        "free-proxy-list/main/proxies/countries/id/data.json"
    )
    print("[INFO] Fetching proxy list from repository...")

    try:
        response = requests.get(url, timeout=10)
        if response.status_code != 200:
            print("[WARN] Failed to fetch proxy list.")
            return ""

        proxy_data = response.json()
        if not proxy_data:
            return ""

        random.shuffle(proxy_data)
        print(f"[INFO] Testing {min(10, len(proxy_data))} proxy candidates...")

        for entry in proxy_data[:10]:
            ip_addr = str(entry.get("ip", ""))
            port = str(entry.get("port", ""))

            if not ip_addr or not port:
                continue

            proxy_str = f"{ip_addr}:{port}"
            test_proxies = {
                "http": f"http://{proxy_str}",
                "https": f"http://{proxy_str}"
            }

            try:
                # Target the exact checkin API to ensure the proxy can handle the auth handshake
                checkin_url = "https://android.clients.google.com/checkin"
                requests.get(checkin_url, proxies=test_proxies, timeout=5)
                print(f"[SUCCESS] Active proxy secured: {proxy_str}")
                return proxy_str
            except (requests.exceptions.RequestException, ValueError):
                continue

        print("[WARN] All tested proxies are unresponsive.")

    except (requests.exceptions.RequestException, ValueError) as err:
        print(f"[WARN] Error during proxy acquisition: {err}")

    return ""


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
                print(f"[INFO] Uploading {final_filename} to HuggingFace: {hf_dataset}")
                try:
                    api = HfApi(token=hf_token)
                    api.upload_file(
                        path_or_fileobj=final_path,
                        path_in_repo=final_filename,
                        repo_id=hf_dataset,
                        repo_type="dataset"
                    )
                    print("[SUCCESS] Artifact uploaded to HuggingFace securely.")
                except (ValueError, OSError, RuntimeError, ConnectionError) as err:
                    print(f"[ERROR] HuggingFace upload sequence failed: {err}")
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


def process_target_app(
    row: pd.Series, downloader: GooglagDownloader, output_dir: str, active_proxy: str
) -> None:
    """
    Processes a single application entry, manages dynamic proxy injection,
    triggers the download, and normalizes the filename.
    """
    pkg_name = str(row['package_name'])

    # Intercept and evaluate skip logic immediately
    skip_raw = str(row.get('skip', 'false')).strip().lower()
    should_skip = skip_raw in ('true', 'yes', '1', 'y')

    if should_skip:
        print(f"\n[INFO] Skipping: {pkg_name} (Skip Flag: Active)")
        return

    target = str(row.get('upload_target', 'both')).strip().lower()
    use_proxy_raw = str(row.get('use_proxy', 'false')).strip().lower()
    requires_proxy = use_proxy_raw in ('true', 'yes', '1', 'y')

    print(f"\n[INFO] Processing: {pkg_name} (Target: {target}, Proxy: {requires_proxy})")

    # Inject proxy dynamically if requested and available
    if requires_proxy and active_proxy:
        os.environ["http_proxy"] = f"http://{active_proxy}"
        os.environ["https_proxy"] = f"http://{active_proxy}"
        print(f"[INFO] Proxy tunneling enabled for {pkg_name}.")
    else:
        # Ensure pure connection for non-proxy apps
        os.environ.pop("http_proxy", None)
        os.environ.pop("https_proxy", None)
        if requires_proxy and not active_proxy:
            print("[WARN] Proxy requested but unavailable. Proceeding directly.")

    dl_path = downloader.download(pkg_name, output_dir)

    # Clean up environment variables immediately after the download attempt
    os.environ.pop("http_proxy", None)
    os.environ.pop("https_proxy", None)

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

    active_proxy = ""

    # Filter active applications to determine if proxy acquisition is necessary
    if 'skip' in target_apps.columns:
        skip_mask = target_apps['skip'].astype(str).str.strip().str.lower().isin(
            ['true', 'yes', '1', 'y']
        )
        active_apps = target_apps[~skip_mask]
    else:
        active_apps = target_apps

    # Only fetch a proxy if at least one active app requires it
    if 'use_proxy' in active_apps.columns:
        proxy_needed = active_apps['use_proxy'].astype(str).str.strip().str.lower().isin(
            ['true', 'yes', '1', 'y']
        ).any()

        if proxy_needed:
            active_proxy = get_working_proxy()

    downloader = GooglagDownloader(email, aas, dev_b64)
    output_dir = os.path.join(os.getcwd(), "Release_Output")
    os.makedirs(output_dir, exist_ok=True)

    for _, row in target_apps.iterrows():
        process_target_app(row, downloader, output_dir, active_proxy)


if __name__ == "__main__":
    main()
