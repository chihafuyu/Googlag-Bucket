"""
Main Execution Script.
Reads target applications from a CSV, downloads them via Googlag Bucket,
normalizes filenames, and dynamically routes artifacts with selective proxying.
"""

import os
import sys
import time
import random
import hashlib
import uuid
from zipfile import ZipFile
import requests
import pandas as pd

# Handle cross-version path changes between Androguard v3.x and v4.x
try:
    from androguard.core.apk import APK
except ImportError:
    from androguard.core.bytecodes.apk import APK

# Handle symmetric encryption for package name obfuscation
try:
    from cryptography.fernet import Fernet, InvalidToken
    FERNET_AVAILABLE = True
except ImportError:
    FERNET_AVAILABLE = False

# Gracefully handle the optional HuggingFace dependency
try:
    from huggingface_hub import HfApi
    HF_AVAILABLE = True
except ImportError:
    HF_AVAILABLE = False

# Handle optional AES-256 ZIP encryption dependency
try:
    import pyzipper
    PYZIPPER_AVAILABLE = True
except ImportError:
    PYZIPPER_AVAILABLE = False

from core.googlag import GooglagDownloader


def get_working_proxy() -> str:
    """
    Fetches free Indonesian proxies from a GitHub repository, sorts them by lowest
    latency, tests them against the specific Google Play checkin endpoint, 
    and returns the first working proxy address. Returns an empty string if none are viable.
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

        valid_proxies = [p for p in proxy_data if p.get("ip") and p.get("port")]
        valid_proxies.sort(key=lambda x: int(x.get("latency_ms") or 99999))

        top_candidates = valid_proxies[:50]
        random.shuffle(top_candidates)

        limit_test = min(30, len(top_candidates))
        print(f"[INFO] Testing {limit_test} low-latency proxy candidates...")

        for entry in top_candidates[:limit_test]:
            ip_addr = str(entry.get("ip"))
            port = str(entry.get("port"))
            proxy_str = f"{ip_addr}:{port}"

            test_proxies = {
                "http": f"http://{proxy_str}",
                "https": f"http://{proxy_str}"
            }

            try:
                checkin_url = "https://android.clients.google.com/checkin"
                requests.get(checkin_url, proxies=test_proxies, timeout=8)
                latency = entry.get('latency_ms', 'Unknown')
                print(
                    f"[SUCCESS] Active proxy secured: {proxy_str} "
                    f"(Latency: {latency}ms)"
                )
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


def _decrypt_package(raw_target: str, obfuscate: bool) -> str:
    """Decrypts the package name using Fernet if obfuscation is enabled."""
    if not obfuscate:
        return raw_target
    if not FERNET_AVAILABLE or not os.getenv("FERNET_KEY"):
        print("[ERROR] Cryptography module or FERNET_KEY missing.")
        return ""
    try:
        return Fernet(os.getenv("FERNET_KEY").encode('utf-8')).decrypt(
            raw_target.encode('utf-8')
        ).decode('utf-8')
    except InvalidToken:
        print("[WARN] Invalid Fernet token. Decryption failed.")
        return ""


def _normalize_filename(
    dl_path: str, real_pkg: str, output_dir: str, obfuscate: bool
) -> str:
    """Generates the final filename, applying SHA-256 hashing if obfuscated."""
    version = extract_version_name(dl_path)
    ext = '.apks' if dl_path.endswith('.apks') else '.apk'

    if obfuscate:
        hash_str = hashlib.sha256(
            f"{real_pkg}_{version}".encode('utf-8')
        ).hexdigest()[:16]
        pkg_name = f"secure_build_{hash_str}"
    else:
        pkg_name = f"{real_pkg}_{version}"

    final_path = os.path.join(output_dir, f"{pkg_name}{ext}")
    os.replace(dl_path, final_path)
    return final_path


def _encrypt_artifact(final_path: str, output_dir: str) -> str:
    """Encrypts the downloaded artifact into an AES-256 ZIP vault."""
    zip_pwd = os.getenv("ZIP_PASSWORD")
    if not zip_pwd or not PYZIPPER_AVAILABLE:
        print("[ERROR] ZIP config missing. Aborting encryption.")
        os.remove(final_path)
        return ""

    vault_path = os.path.join(output_dir, f"vault_{uuid.uuid4().hex[:12]}.zip")
    try:
        with pyzipper.AESZipFile(
            vault_path, 'w',
            compression=pyzipper.ZIP_DEFLATED,
            encryption=pyzipper.WZ_AES
        ) as vault:
            vault.setpassword(zip_pwd.encode('utf-8'))
            vault.write(final_path, os.path.basename(final_path))
        os.remove(final_path)
        return vault_path
    except OSError as err:
        print(f"[ERROR] Encryption failed: {err}")
        return ""


def process_target_app(
    row: pd.Series, downloader: GooglagDownloader, output_dir: str, proxy: str
) -> None:
    """
    Processes a single application entry, manages dynamic proxy injection with
    a guided auto-retry mechanism, triggers the download, and encrypts the artifact.
    """
    use_proxy = str(row.get('use_proxy', 'false')).strip().lower() in ('true', 'yes', '1', 'y')
    obfuscate = str(row.get('obfuscate', 'false')).strip().lower() in ('true', 'yes', '1', 'y')
    target = str(row.get('upload_target', 'both')).strip().lower()

    real_pkg = _decrypt_package(str(row['package_name']).strip(), obfuscate)
    if not real_pkg:
        return

    if str(row.get('skip', 'false')).strip().lower() in ('true', 'yes', '1', 'y'):
        print(f"\n[INFO] Skipping: {'Encrypted_Target' if obfuscate else real_pkg}")
        return

    print(f"\n[INFO] Processing: {'Encrypted_Target' if obfuscate else real_pkg}")

    active_proxy = proxy
    max_attempts = 4 if use_proxy else 2

    for attempt in range(1, max_attempts):
        if use_proxy and active_proxy:
            os.environ["http_proxy"] = f"http://{active_proxy}"
            os.environ["https_proxy"] = f"http://{active_proxy}"
            print(f"[INFO] Proxy tunneling enabled (Attempt {attempt})")
        else:
            os.environ.pop("http_proxy", None)
            os.environ.pop("https_proxy", None)

        dl_path = downloader.download(real_pkg, output_dir)

        os.environ.pop("http_proxy", None)
        os.environ.pop("https_proxy", None)

        if not dl_path:
            if attempt < (max_attempts - 1):
                print("[WARN] Download failed. Cooldown 30s...")
                time.sleep(30)
                active_proxy = get_working_proxy()
                continue
            break

        final_path = _normalize_filename(dl_path, real_pkg, output_dir, obfuscate)

        try:
            if os.path.getsize(final_path) < 1048576:
                print(f"[WARN] Artifact {os.path.basename(final_path)} is suspiciously small.")
                os.remove(final_path)
                if attempt < (max_attempts - 1):
                    print("[WARN] Discarded payload. Cooldown 30s...")
                    time.sleep(30)
                    active_proxy = get_working_proxy()
                    continue
                print("[ERROR] Max retries exhausted.")
                break
        except OSError as err:
            print(f"[WARN] Verification failed: {err}")
            break

        if obfuscate:
            final_path = _encrypt_artifact(final_path, output_dir)
            if not final_path:
                break

        print(f"[SUCCESS] Saved artifact: {os.path.basename(final_path)}")
        handle_artifact_routing(final_path, os.path.basename(final_path), target)
        break


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

    if 'skip' in target_apps.columns:
        skip_mask = target_apps['skip'].astype(str).str.strip().str.lower().isin(
            ['true', 'yes', '1', 'y']
        )
        active_apps = target_apps[~skip_mask]
    else:
        active_apps = target_apps

    if 'use_proxy' in active_apps.columns:
        if active_apps['use_proxy'].astype(str).str.strip().str.lower().isin(
            ['true', 'yes', '1', 'y']
        ).any():
            active_proxy = get_working_proxy()

    downloader = GooglagDownloader(email, aas, dev_b64)
    output_dir = os.path.join(os.getcwd(), "Release_Output")
    os.makedirs(output_dir, exist_ok=True)

    for _, row in target_apps.iterrows():
        process_target_app(row, downloader, output_dir, active_proxy)


if __name__ == "__main__":
    main()
