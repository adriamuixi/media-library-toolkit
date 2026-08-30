#!/usr/bin/env bash
set -euo pipefail

install_system_dependencies=false
extras="dev,review"

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
            echo "Creates .venv and installs the project with development and review extras."
            echo "Use --install-system-dependencies on Debian or Ubuntu when Python lacks pip or venv."
            exit 0
            ;;
        *)
            echo "Unknown argument: $argument" >&2
            exit 2
            ;;
    esac
done

if ! command -v python3 >/dev/null 2>&1; then
    echo "Python 3 is required but was not found." >&2
    echo "On Debian or Ubuntu run: sudo apt-get install python3 python3-venv python3-pip" >&2
    exit 1
fi

if ! python3 -m pip --version >/dev/null 2>&1 || ! python3 -m venv --help >/dev/null 2>&1; then
    if ! $install_system_dependencies; then
        echo "Python needs the pip and venv system packages." >&2
        echo "Run: ./scripts/bootstrap.sh --install-system-dependencies" >&2
        echo "This installs python3-venv and python3-pip using apt on Debian or Ubuntu." >&2
        exit 1
    fi
    if ! command -v apt-get >/dev/null 2>&1; then
        echo "Automatic system dependency installation is supported only on Debian or Ubuntu." >&2
        echo "Install the Python pip and venv packages using your operating system package manager." >&2
        exit 1
    fi
    sudo apt-get update
    sudo apt-get install -y python3-venv python3-pip
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
