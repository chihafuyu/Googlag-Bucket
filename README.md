# Googlag Bucket Fetcher

A highly resilient, automated continuous integration pipeline designed to securely fetch mobile application packages from the Googlag Bucket ecosystem. This project leverages GitHub Actions to streamline the acquisition, validation, and dynamic routing of artifacts directly into GitHub Releases and Hugging Face Datasets.

Built with a focus on stealth, reliability, and cryptographic integrity, this tool ensures that your artifact retrieval process remains bulletproof against network interruptions, regional blocks, and external monitoring.

## Core Features

* **Dynamic Artifact Routing:** Automatically dispatches downloaded packages to GitHub Releases, Hugging Face Hub, or both, based on a flexible dataset configuration.
* **High-Performance Uploads:** Integrates `hf_transfer` to enable Xet storage high-performance mode, maximizing bandwidth utilization for massive application payloads.
* **Geo-Blocking Evasion:** Features an automated proxy rotation engine that fetches and validates region-specific proxies (e.g., ID region) to bypass server-side geographical restrictions.
* **Granular Execution Control:** Utilizes a modular CSV control panel allowing per-app configurations for targeted routing, proxy tunneling, or workflow skipping without altering the codebase.
* **Secure Acquisition Engine:** Utilizes the Rust-based `apkeep` binary to securely interface with the Googlag Bucket architecture without triggering rate limits.
* **Cryptographic Integrity:** Automatically generates and publishes `SHA256SUMS` manifests for all retrieved artifacts to ensure byte-for-byte verification.
* **Zero-Trace Eradication:** Includes an automated "Nuke" workflow (`cleanup.yml`) that globally purges execution logs, stale releases, and associated Git tags to maintain a pristine, low-profile repository.

## Configuration & Setup

### 1. Repository Secrets
Before triggering the workflow, configure the following environment variables in your repository settings (**Settings > Secrets and variables > Actions**):

| Secret Key | Description |
| :--- | :--- |
| `PLAY_EMAIL` | The primary account email address registered in the Googlag Bucket ecosystem. |
| `PLAY_AAS_TOKEN` | The valid Authentication Service (AAS) token associated with the account. |
| `DEVICE_B64` | A strictly Base64-encoded string containing your custom `device.properties` configuration. |
| `HF_TOKEN` | Hugging Face Access Token with `Write` permissions to push datasets. |
| `HF_DATASET_ID` | The target Hugging Face dataset identifier (e.g., `username/DatasetName`). |
| `GITHUB_TOKEN` | (Auto-generated) Required for the cleanup script to perform administrative API calls. |

### 2. Target Dataset (`apps.csv`)
Define the applications and their specific execution parameters in a comma-separated values file named `apps.csv` located in the root directory.

**Format & Parameters:**
```csv
package_name,upload_target,use_proxy,skip
com.zhiliaoapp.musically,huggingface,false,false
com.ss.android.ugc.trill,huggingface,true,false
com.google.android.apps.photos,github,false,true
```
- `package_name`: The exact application identifier.
- `upload_target`: Destination routing (github, huggingface, or both).
- `use_proxy`: Enable regional proxy tunneling (true or false).
- `skip`: Temporarily exclude the application from the execution pipeline (true or false).

### 3. Credits
- [ProxyScrape](https://github.com/ProxyScrape/free-proxy-list) - for providing free proxy list

## License

Distributed under the **MIT License**

**Copyright (c) 2026 chihafuyu**

> This project is intended strictly for educational purposes, personal archival, and automated deployment testing. The maintainers assume no liability for the misuse of this tool.
>
