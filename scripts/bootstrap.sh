#!/usr/bin/env bash
set -euo pipefail

install_system_dependencies=false
extras="dev,review,browser,database"
platform="$(uname -s)"

for argument in "$@"; do
    case "$argument" in
        --install-system-dependencies)
            install_system_dependencies=true
            ;;
        --runtime)
            extras=""
            ;;
        --help)
            echo "Usage: ./scripts/bootstrap.sh [--install-system-dependencies] [--runtime]"
            echo "Creates .venv and installs the project with development and local browser extras."
            echo "Use --install-system-dependencies to install Python, ExifTool, and ffmpeg on macOS or Debian/Ubuntu."
            exit 0
            ;;
        *)
            echo "Unknown argument: $argument" >&2
            exit 2
            ;;
    esac
done

install_system_packages() {
    case "$platform" in
        Darwin)
            if ! command -v brew >/dev/null 2>&1; then
                echo "Homebrew is required for automatic macOS dependency installation." >&2
                echo "Install Homebrew from https://brew.sh, then rerun this command." >&2
                exit 1
            fi
            brew install python exiftool ffmpeg
            ;;
        Linux)
            if ! command -v apt-get >/dev/null 2>&1; then
                echo "Automatic Linux dependency installation supports Debian and Ubuntu only." >&2
                echo "Install Python 3, pip, venv, ExifTool, and ffmpeg with your package manager." >&2
                exit 1
            fi
            sudo apt-get update
            sudo apt-get install -y python3 python3-venv python3-pip libimage-exiftool-perl ffmpeg
            ;;
        *)
            echo "Automatic dependency installation is unsupported on: $platform" >&2
            echo "Install Python 3.11+, pip, venv, ExifTool, and ffmpeg manually." >&2
            exit 1
            ;;
    esac
}

if $install_system_dependencies; then
    install_system_packages
fi

if ! command -v python3 >/dev/null 2>&1; then
    echo "Python 3 is required but was not found." >&2
    echo "Run: ./scripts/bootstrap.sh --install-system-dependencies" >&2
    exit 1
fi

if ! python3 -m pip --version >/dev/null 2>&1 || ! python3 -m venv --help >/dev/null 2>&1; then
    echo "Python needs pip and venv support." >&2
    echo "Run: ./scripts/bootstrap.sh --install-system-dependencies" >&2
    exit 1
fi

if [ ! -x ".venv/bin/python" ]; then
    python3 -m venv .venv
fi

if [ -n "$extras" ]; then
    .venv/bin/python -m pip install --upgrade pip
    .venv/bin/python -m pip install -e ".[$extras]"
else
    .venv/bin/python -m pip install --upgrade pip
    .venv/bin/python -m pip install -e .
fi

echo "Installation complete."
echo "Run: source .venv/bin/activate"
echo "Then: media --help"
if ! command -v exiftool >/dev/null 2>&1 || ! command -v ffprobe >/dev/null 2>&1; then
    echo "ExifTool or ffprobe is not available. Metadata extraction will remain unavailable until installed." >&2
    echo "Run: ./scripts/bootstrap.sh --install-system-dependencies" >&2
fi
