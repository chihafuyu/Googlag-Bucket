# Googlag Bucket Fetcher

A highly resilient, automated continuous integration pipeline designed to securely fetch mobile application packages from the Googlag Bucket ecosystem. This project leverages GitHub Actions to streamline the acquisition, validation, and deployment of artifacts directly into GitHub Releases.

Built with a focus on stealth, reliability, and cryptographic integrity, this tool ensures that your artifact retrieval process remains bulletproof against network interruptions and external monitoring.

## Core Features

* **Secure Acquisition Engine:** Utilizes the Rust-based `apkeep` binary to securely interface with the Googlag Bucket architecture without triggering rate limits or automated flags.
* **Smart Asset Packaging:** Automatically evaluates fetched binaries. If a multi-part split architecture is detected, it seamlessly repacks the components into a unified `.apks` or `.xapk` container.
* **Cryptographic Integrity:** Automatically generates and publishes `SHA256SUMS` manifests for all retrieved artifacts to ensure byte-for-byte verification.
* **Hardware Spoofing via Base64:** Supports advanced device profiling by injecting Base64-encoded property files, allowing the fetcher to bypass hardware-specific distribution restrictions.
* **Zero-Trace Eradication:** Includes an automated "Nuke" workflow (`cleanup.yml`) that globally purges execution logs, stale releases, and associated Git tags to maintain a pristine, low-profile repository.

## Configuration & Setup

### 1. Repository Secrets
Before triggering the workflow, you must configure the following environment variables in your repository settings (**Settings > Secrets and variables > Actions**):

| Secret Key | Description |
| :--- | :--- |
| `PLAY_EMAIL` | The primary account email address registered in the Googlag Bucket ecosystem. |
| `PLAY_AAS_TOKEN` | The valid Authentication Service (AAS) token associated with the account. |
| `DEVICE_B64` | A strictly Base64-encoded string containing your custom `device.properties` configuration. |
| `GITHUB_TOKEN` | (Auto-generated) Required for the cleanup script to perform administrative API calls. |

### 2. Target Dataset (`apps.csv`)
Define the applications you wish to fetch in a comma-separated values file named `apps.csv` located in the root directory. 

**Format:**
```csv
app_name,package_name,arch
SecureMessenger,com.secure.msg,arm64-v8a
CloudDrive,com.cloud.storage,armeabi-v7a
```

## License

Distributed under the **MIT License**

**Copyright (c) 2026 chihafuyu**

> This project is intended strictly for educational purposes, personal archival, and automated deployment testing. The maintainers assume no liability for the misuse of this tool.
>
