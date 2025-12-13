#!/bin/bash

# Base directory for venvs
VENV_DIR="/home/admin/projects/slarc/venvs"

# Create base directory
mkdir -p "$VENV_DIR"

echo "🔧 Checking and creating virtual environments..."

# Function to create venv if it doesn't exist
create_venv() {
    local name=$1
    local path="$VENV_DIR/$name"
    local site_packages=$2

    if [ -d "$path" ]; then
        echo "✅ Venv '$name' already exists. Skipping creation."
    else
        echo "🆕 Creating venv '$name'..."
        if [ "$site_packages" = true ]; then
            python3 -m venv "$path" --system-site-packages
        else
            python3 -m venv "$path"
        fi
    fi
}

# Create venvs
create_venv "slarc_base" false
create_venv "vision" true
create_venv "ai" true
create_venv "sensors" false
create_venv "motion_control" false
create_venv "slam" false

echo "📦 Installing packages..."

# Helper to install packages if venv exists
install_packages() {
    local name=$1
    shift
    local path="$VENV_DIR/$name"
    if [ -d "$path" ]; then
        source "$path/bin/activate"
        pip install "$@"
        deactivate
    else
        echo "⚠️ Venv '$name' not found. Skipping package installation."
    fi
}

# Package installations
install_packages "slarc_base" posix_ipc
install_packages "vision" opencv-python --no-deps pyzmq moderngl glcontext posix_ipc
install_packages "ai" opencv-python onnxruntime posix_ipc llama-cpp-python numpy==2.2.6
install_packages "sensors" smbus2 numpy==1.24 matplotlib icm20948 scipy==1.11.4 posix_ipc
install_packages "motion_control" RPi.GPIO posix_ipc
install_packages "slam" opencv-python matplotlib numpy==1.24 posix_ipc

echo "🎉 All venvs checked, created if needed, and configured successfully."
