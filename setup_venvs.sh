#!/bin/bash

# Base directory for venvs
VENV_DIR="/home/admin/projects/slarc/venvs"
LLAMA_REPO_DIR="llama-cpp-python" # Directory for the cloned repo

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
create_venv "ai" true # This venv will host the custom llama-cpp-python build
create_venv "sensors" false
create_venv "motion_control" false
create_venv "slam" false

echo "📦 Installing standard packages..."

# Helper to install packages if venv exists (for simple pip installs)
install_packages() {
    local name=$1
    shift
    local path="$VENV_DIR/$name"
    if [ -d "$path" ]; then
        echo "   -> Installing standard packages for '$name'..."
        source "$path/bin/activate"
        # Using --disable-pip-version-check to clean up output
        pip install --disable-pip-version-check "$@"
        deactivate
    else
        echo "⚠️ Venv '$name' not found. Skipping package installation."
    fi
}

# --- 🎯 NEW CUSTOM INSTALLATION FUNCTION ---
install_llama_cpp_custom() {
    local venv_name="ai"
    local path="$VENV_DIR/$venv_name"

    if [ ! -d "$path" ]; then
        echo "⚠️ Venv '$venv_name' not found. Skipping custom llama-cpp-python build."
        return 1
    fi

    echo "⚙️ Starting custom build and installation of llama-cpp-python for '$venv_name'..."

    # 1. Activate the target venv
    source "$path/bin/activate"

    # 2. Pre-install dependencies for the build system
    echo "   -> Installing build dependencies (scikit-build-core, cmake, ninja)..."
    pip install --disable-pip-version-check "scikit-build-core[pyproject]" cmake ninja

    # 3. Handle cloning and directory
    if [ -d "$LLAMA_REPO_DIR" ]; then
        echo "   -> Found existing local repository. Cleaning and updating..."
        cd "$LLAMA_REPO_DIR"
        git fetch origin
        git reset --hard origin/main # Reset to main branch to ensure clean state
        git submodule update --init --recursive
    else
        echo "   -> Cloning repository and submodules..."
        git clone --recursive https://github.com/abetlen/llama-cpp-python.git
        cd "$LLAMA_REPO_DIR"
    fi

    # 4. Clean any previous cached builds in this directory
    echo "   -> Cleaning cached build files..."
    rm -rf _skbuild dist build

    # 5. Remove any existing installation inside the venv
    # NOTE: This is crucial as it prevents issues where an older wheel might be picked up.
    echo "   -> Removing any previous llama-cpp-python installation from venv..."
    pip uninstall -y llama-cpp-python

    # 6. Build and install using the local source with CMAKE_ARGS
    echo "   -> Building and installing with OpenBLAS acceleration..."
    # The CMAKE_ARGS are passed to scikit-build-core
    # Using --no-cache-dir and --verbose as requested
    CMAKE_ARGS="-DGGML_BLAS=ON -DGGML_BLAS_VENDOR=OpenBLAS" pip install . --no-cache-dir --verbose

    # 7. Go back to the original directory and deactivate
    cd ..
    deactivate

    echo "✅ Custom llama-cpp-python build complete for '$venv_name'."
}
# --- ⬆️ END NEW CUSTOM INSTALLATION FUNCTION ---


# --- PACKAGE INSTALLATION CALLS ---
install_packages "slarc_base" posix_ipc
install_packages "vision" opencv-python --no-deps pyzmq moderngl glcontext posix_ipc

# Call the custom function for the 'ai' venv
install_llama_cpp_custom

# Install other packages in the 'ai' venv
install_packages "ai" opencv-python onnxruntime posix_ipc numpy==2.2.6 tabulate

# Note: numpy==2.2.6 and opencv-python are installed here after the custom llama-cpp-python build.
# This avoids installing them *before* the build, which could potentially conflict.
# The custom function installed llama-cpp-python; this ensures the other requirements are met.

install_packages "sensors" smbus2 numpy==1.24 matplotlib icm20948 scipy==1.11.4 posix_ipc
install_packages "motion_control" RPi.GPIO posix_ipc
install_packages "slam" opencv-python matplotlib numpy==1.24 posix_ipc

echo "🎉 All venvs checked, created if needed, and configured successfully."