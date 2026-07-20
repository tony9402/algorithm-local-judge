#!/usr/bin/env bash
# Install a signed Judge and Problem Studio release for one local user on macOS or Linux.
set -euo pipefail

repository="${ALJ_INSTALL_REPOSITORY:-tony9402/algorithm-local-judge}"
install_root="${ALJ_INSTALL_ROOT:-$HOME/.local/share/algorithm-local-judge}"
bin_dir="${ALJ_BIN_DIR:-$HOME/.local/bin}"
release_tag="${ALJ_INSTALL_RELEASE_TAG:-__ALJ_RELEASE_TAG__}"
dry_run=0

if [[ ! "$repository" =~ ^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$ ]]; then
    echo "Invalid ALJ_INSTALL_REPOSITORY: expected GitHub owner/name" >&2
    exit 2
fi

usage() {
    cat <<'EOF'
Usage: install_local.sh --release-tag TAG [--install-root PATH] [--bin-dir PATH] [--dry-run]

Downloads the signed Judge and Problem Studio standalone release for TAG,
verifies its SHA-256 digest and Sigstore publisher identity, and installs it
for the current user. No sudo permission is required.
EOF
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --release-tag)
            release_tag="$2"
            shift 2
            ;;
        --install-root)
            install_root="$2"
            shift 2
            ;;
        --bin-dir)
            bin_dir="$2"
            shift 2
            ;;
        --dry-run)
            dry_run=1
            shift
            ;;
        --help|-h)
            usage
            exit 0
            ;;
        *)
            echo "Unknown option: $1" >&2
            usage >&2
            exit 2
            ;;
    esac
done

os="$(uname -s)"
arch="$(uname -m)"
case "$os/$arch" in
    Darwin/arm64)
        platform="macos-arm64"
        ;;
    Darwin/x86_64)
        platform="macos-amd64"
        ;;
    Linux/x86_64|Linux/amd64)
        platform="linux-amd64"
        ;;
    *)
        echo "Unsupported platform: $os $arch" >&2
        echo "Windows users should use WSL Ubuntu until the native installer is available." >&2
        exit 1
        ;;
esac

if [[ "$release_tag" == "__ALJ_RELEASE_TAG__" ]]; then
    echo "A release tag is required: pass --release-tag v<version> or set ALJ_INSTALL_RELEASE_TAG." >&2
    exit 2
fi
if [[ ! "$release_tag" =~ ^v[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
    echo "Invalid release tag: expected v<major>.<minor>.<patch>" >&2
    exit 2
fi

asset="algorithm-local-judge-${platform}.tar.gz"
base_url="https://github.com/${repository}/releases/download/${release_tag}"
archive_url="${base_url}/${asset}"
checksum_url="${archive_url}.sha256"
bundle_url="${archive_url}.sigstore.json"
identity_pattern="^https://github\\.com/${repository//./\\.}/\\.github/workflows/release\\.yml@refs/tags/.+$"

if [[ "$dry_run" -eq 1 ]]; then
    cat <<EOF
Judge local installer dry run
  platform: $platform
  release tag: $release_tag
  archive: $archive_url
  install root: $install_root
  command links: $bin_dir/judge, $bin_dir/problem-studio
  required commands: curl, tar, cosign, shasum or sha256sum
EOF
    exit 0
fi

for command in curl tar cosign; do
    if ! command -v "$command" >/dev/null 2>&1; then
        echo "Required command is missing: $command" >&2
        if [[ "$command" == "cosign" ]]; then
            echo "macOS/Linuxbrew: brew install cosign" >&2
            echo "Linux packages: https://docs.sigstore.dev/cosign/system_config/installation/" >&2
        fi
        exit 1
    fi
done

if command -v sha256sum >/dev/null 2>&1; then
    hash_command="sha256sum"
elif command -v shasum >/dev/null 2>&1; then
    hash_command="shasum -a 256"
else
    echo "SHA-256 tool is missing: install sha256sum or shasum." >&2
    exit 1
fi

temporary="$(mktemp -d "${TMPDIR:-/tmp}/alj-install.XXXXXX")"
cleanup() {
    rm -rf "$temporary"
}
trap cleanup EXIT

echo "Downloading signed Judge release for $platform..."
curl --fail --show-error --location "$archive_url" --output "$temporary/$asset"
curl --fail --show-error --location "$checksum_url" --output "$temporary/$asset.sha256"
curl --fail --show-error --location "$bundle_url" --output "$temporary/$asset.sigstore.json"

expected="$(awk 'NR == 1 {print $1}' "$temporary/$asset.sha256")"
actual="$($hash_command "$temporary/$asset" | awk 'NR == 1 {print $1}')"
if [[ ! "$expected" =~ ^[0-9a-fA-F]{64}$ ]] || [[ "$expected" != "$actual" ]]; then
    echo "SHA-256 verification failed for $asset" >&2
    exit 1
fi

cosign verify-blob "$temporary/$asset" \
    --bundle "$temporary/$asset.sigstore.json" \
    --certificate-identity-regexp "$identity_pattern" \
    --certificate-oidc-issuer "https://token.actions.githubusercontent.com"

tar -xzf "$temporary/$asset" -C "$temporary"
staged="$temporary/algorithm-local-judge"
command_names=("judge" "problem-studio")
for command_name in "${command_names[@]}"; do
    if [[ ! -x "$staged/bin/$command_name" ]]; then
        echo "Verified archive does not contain executable algorithm-local-judge/bin/$command_name" >&2
        exit 1
    fi
done

mkdir -p "$(dirname "$install_root")" "$bin_dir"
for command_name in "${command_names[@]}"; do
    command_path="$bin_dir/$command_name"
    if [[ -d "$command_path" && ! -L "$command_path" ]]; then
        echo "Cannot install command link over directory: $command_path" >&2
        exit 1
    fi
done

backup="${install_root}.previous"
rm -rf "$backup"
if [[ -e "$install_root" ]]; then
    mv "$install_root" "$backup"
fi
if ! mv "$staged" "$install_root"; then
    if [[ -e "$backup" ]]; then
        mv "$backup" "$install_root"
    fi
    exit 1
fi

command_backup="$temporary/command-links.previous"
mkdir -p "$command_backup"

restore_command_links() {
    local restore_failed=0
    local command_name command_path installed_target previous_path
    for command_name in "${command_names[@]}"; do
        command_path="$bin_dir/$command_name"
        installed_target="$install_root/bin/$command_name"
        previous_path="$command_backup/$command_name"
        if [[ -L "$command_path" ]] && [[ "$(readlink "$command_path")" == "$installed_target" ]]; then
            if ! rm -f "$command_path"; then
                restore_failed=1
                continue
            fi
        fi
        if [[ -e "$previous_path" || -L "$previous_path" ]]; then
            if [[ -e "$command_path" || -L "$command_path" ]]; then
                echo "Could not restore command because its path changed: $command_path" >&2
                restore_failed=1
            elif ! mv "$previous_path" "$command_path"; then
                restore_failed=1
            fi
        fi
    done
    return "$restore_failed"
}

rollback_install() {
    if ! restore_command_links; then
        echo "Warning: one or more previous command links could not be restored." >&2
    fi
    rm -rf "$install_root"
    if [[ -e "$backup" ]]; then
        if ! mv "$backup" "$install_root"; then
            echo "Warning: previous installation could not be restored from $backup" >&2
        fi
    fi
}

for command_name in "${command_names[@]}"; do
    command_path="$bin_dir/$command_name"
    if [[ -e "$command_path" || -L "$command_path" ]]; then
        if ! mv "$command_path" "$command_backup/$command_name"; then
            rollback_install
            exit 1
        fi
    fi
done

for command_name in "${command_names[@]}"; do
    if ! ln -s "$install_root/bin/$command_name" "$bin_dir/$command_name"; then
        rollback_install
        exit 1
    fi
done

for command_name in "${command_names[@]}"; do
    if [[ ! -x "$bin_dir/$command_name" ]]; then
        echo "Installed command is not executable: $bin_dir/$command_name" >&2
        rollback_install
        exit 1
    fi
done

if [[ -e "$backup" ]]; then
    rm -rf "$backup"
fi

echo "Judge and Problem Studio installed: $install_root"
echo "Commands: $bin_dir/judge, $bin_dir/problem-studio"
if [[ ":$PATH:" != *":$bin_dir:"* ]]; then
    echo "Add this directory to PATH: $bin_dir"
fi
cat <<'EOF'

Next steps:
  judge setup
  problem-studio web
EOF
