#!/usr/bin/env bash
# ==============================================================================
# Copyright 2026 Luca D'Aurizio
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# Guarded Swarms - installation script.
#
# Installs every dependency and builds the workspace on a fresh Ubuntu 22.04
# LTS system. Run once:
#
#     chmod +x install.sh
#     ./install.sh
#
# Steps:
#   1. ROS 2 Humble
#   2. Gazebo Harmonic
#   3. Micro-XRCE-DDS Agent (the PX4 <-> ROS 2 transport)
#   4. PX4 dependencies and SITL, pinned to the commit px4_msgs was generated from
#   5. rosbridge (the supervisor console's WebSocket bridge)
#   6. The ROS 2 workspace
#   7. Scenario assets and the generated coastal world
#   8. ~/.bashrc
# ==============================================================================
set -e

# ------------------------------------------------------------------------------
# Terminal colours for the log helpers.
# ------------------------------------------------------------------------------
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ------------------------------------------------------------------------------
# PX4 firmware pin.
#
# px4_msgs (pinned by git) is generated from this exact PX4 commit. Cloning PX4
# main instead would produce mismatched uORB message definitions: the uXRCE-DDS
# bridge then fails silently on some topics and vehicles never move. Do not bump
# this without regenerating px4_msgs to match.
# ------------------------------------------------------------------------------
PX4_COMMIT="091ac918b133d518da8b73e395243ea0e0d087b5"
PX4_BRANCH="guarded-swarms-pin"

TOTAL_STEPS=8

log()  { echo -e "${BLUE}[install]${NC} $1"; }
ok()   { echo -e "${GREEN}[ok]${NC} $1"; }
warn() { echo -e "${YELLOW}[warn]${NC} $1"; }
fail() { echo -e "${RED}[error]${NC} $1"; exit 1; }

# ------------------------------------------------------------------------------
# System check: Ubuntu 22.04.
# ------------------------------------------------------------------------------
log "Checking system..."
OS=$(lsb_release -si 2>/dev/null || echo "Unknown")
VER=$(lsb_release -sr 2>/dev/null || echo "0")
if [ "$OS" != "Ubuntu" ]; then
    fail "This script requires Ubuntu. Detected: $OS"
fi
if [ "$VER" != "22.04" ]; then
    warn "This script is tested on Ubuntu 22.04. Detected: $VER. Proceeding anyway..."
fi
ok "System: Ubuntu $VER"

# ------------------------------------------------------------------------------
# Step 1: ROS 2 Humble.
# ------------------------------------------------------------------------------
log "Step 1/${TOTAL_STEPS}: Installing ROS 2 Humble..."
if [ -f /opt/ros/humble/setup.bash ]; then
    ok "ROS 2 Humble already installed. Skipping."
else
    sudo apt-get update
    sudo apt-get install -y software-properties-common curl
    sudo curl -sSL https://raw.githubusercontent.com/ros/rosdistro/master/ros.key \
        -o /usr/share/keyrings/ros-archive-keyring.gpg
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/ros-archive-keyring.gpg] \
        http://packages.ros.org/ros2/ubuntu jammy main" \
        | sudo tee /etc/apt/sources.list.d/ros2.list > /dev/null
    sudo apt-get update
    sudo apt-get install -y \
        ros-humble-desktop \
        ros-humble-ros-gzharmonic-bridge \
        python3-colcon-common-extensions \
        python3-rosdep
    ok "ROS 2 Humble installed."
fi

# ------------------------------------------------------------------------------
# Step 2: Gazebo Harmonic.
# ------------------------------------------------------------------------------
log "Step 2/${TOTAL_STEPS}: Installing Gazebo Harmonic..."
if command -v gz >/dev/null 2>&1; then
    ok "Gazebo already installed. Skipping."
else
    sudo curl -sSL https://packages.osrfoundation.org/gazebo.gpg \
        | sudo tee /usr/share/keyrings/pkgs-osrf-archive-keyring.gpg > /dev/null
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/pkgs-osrf-archive-keyring.gpg] \
        http://packages.osrfoundation.org/gazebo/ubuntu-stable jammy main" \
        | sudo tee /etc/apt/sources.list.d/gazebo-stable.list > /dev/null
    sudo apt-get update
    sudo apt-get install -y gz-harmonic
    ok "Gazebo Harmonic installed."
fi

# ------------------------------------------------------------------------------
# Step 3: Micro-XRCE-DDS Agent.
# ------------------------------------------------------------------------------
log "Step 3/${TOTAL_STEPS}: Installing Micro-XRCE-DDS Agent..."
if command -v MicroXRCEAgent >/dev/null 2>&1; then
    ok "MicroXRCEAgent already installed. Skipping."
else
    sudo apt-get install -y git cmake build-essential
    cd /tmp
    git clone --depth 1 https://github.com/eProsima/Micro-XRCE-DDS-Agent.git
    cd Micro-XRCE-DDS-Agent
    mkdir build && cd build
    cmake ..
    make -j"$(nproc)"
    sudo make install
    sudo ldconfig /usr/local/lib/
    cd "$REPO_DIR"
    ok "MicroXRCEAgent installed."
fi

# ------------------------------------------------------------------------------
# Step 4: PX4 dependencies and SITL.
# ------------------------------------------------------------------------------
log "Step 4/${TOTAL_STEPS}: Installing PX4 dependencies and building SITL..."
sudo apt-get install -y \
    bc \
    libeigen3-dev \
    libopencv-dev \
    pkg-config \
    protobuf-compiler \
    gstreamer1.0-plugins-bad \
    gstreamer1.0-plugins-base \
    gstreamer1.0-plugins-good \
    gstreamer1.0-plugins-ugly \
    gstreamer1.0-libav \
    libgstreamer-plugins-base1.0-dev \
    xterm \
    expect

PX4_DIR="$HOME/PX4-Autopilot"
if [ -d "$PX4_DIR" ]; then
    CURRENT_COMMIT=$(git -C "$PX4_DIR" rev-parse HEAD 2>/dev/null || echo "unknown")
    if [ "$CURRENT_COMMIT" = "$PX4_COMMIT" ]; then
        ok "PX4-Autopilot already at pinned commit ${PX4_COMMIT:0:8}."
    else
        warn "PX4-Autopilot exists but is at ${CURRENT_COMMIT:0:8}, expected ${PX4_COMMIT:0:8}."
        warn "This WILL break uXRCE-DDS topic bridging (vehicles arm but never move)."
        warn "To fix:"
        warn "    cd $PX4_DIR"
        warn "    git fetch --unshallow --tags   # only if the clone is shallow"
        warn "    git checkout -B $PX4_BRANCH $PX4_COMMIT"
        warn "    git submodule update --init --recursive"
        warn "    make distclean && make px4_sitl_default"
        fail "Refusing to continue with a mismatched PX4 version."
    fi
else
    log "Cloning PX4-Autopilot at pinned commit ${PX4_COMMIT:0:8}..."
    cd "$HOME"
    # Blobless clone: full history (needed to check out an arbitrary commit)
    # but blobs fetched on demand, so it stays fast.
    git clone --filter=blob:none https://github.com/PX4/PX4-Autopilot.git
    cd "$PX4_DIR"
    git checkout -B "$PX4_BRANCH" "$PX4_COMMIT"
    git submodule update --init --recursive
    ok "PX4-Autopilot cloned and pinned."
fi

cd "$PX4_DIR"
if [ -f "$PX4_DIR/build/px4_sitl_default/bin/px4" ]; then
    ok "PX4 already built. Skipping."
else
    log "Installing PX4 dependencies (this may take a few minutes)..."
    cd "$PX4_DIR"
    bash ./Tools/setup/ubuntu.sh --no-nuttx --no-sim-tools
    log "Building PX4 SITL (this will take 10-20 minutes)..."
    make px4_sitl_default
    ok "PX4 SITL built."
fi
cd "$REPO_DIR"

# ------------------------------------------------------------------------------
# Step 5: rosbridge.
#
# The supervisor console (console/decision_panel.html) reaches ROS 2 over a
# WebSocket served by rosbridge. Launch it with the workspace sourced so it
# knows the custom message types; see scripts/demo_console.sh.
# ------------------------------------------------------------------------------
log "Step 5/${TOTAL_STEPS}: Installing rosbridge (supervisor console bridge)..."
if [ -f /opt/ros/humble/share/rosbridge_server/package.xml ]; then
    ok "rosbridge already installed. Skipping."
else
    sudo apt-get install -y ros-humble-rosbridge-suite
    ok "rosbridge installed."
fi

# ------------------------------------------------------------------------------
# Optional: NVIDIA utilities (skipped on non-NVIDIA systems).
# ------------------------------------------------------------------------------
log "Checking for NVIDIA GPU..."
if lspci 2>/dev/null | grep -qi nvidia; then
    log "NVIDIA GPU detected. Installing nvidia-utils..."
    # Try to install the utilities package; non-fatal if it fails
    # (e.g. driver version mismatch or VM without GPU passthrough).
    sudo apt-get install -y nvidia-utils-570 2>/dev/null || \
    sudo apt-get install -y nvidia-utils-535 2>/dev/null || \
    warn "nvidia-utils not installed - nvidia-smi will not be available. This is non-fatal."
else
    warn "No NVIDIA GPU detected (VM or unsupported hardware). Skipping nvidia-utils."
    warn "Gazebo lidar rendering requires a physical NVIDIA GPU."
fi

# ------------------------------------------------------------------------------
# Step 6: Build the ROS 2 workspace.
#
# Messages first (everything else depends on them), then the rest.
# ------------------------------------------------------------------------------
log "Step 6/${TOTAL_STEPS}: Building the ROS 2 workspace..."
cd "$REPO_DIR"
git submodule update --init --recursive
source /opt/ros/humble/setup.bash

log "Building messages and px4_msgs first..."
colcon build \
    --packages-select guarded_swarms_msgs px4_msgs \
    --symlink-install \
    --event-handlers console_direct+
source "$REPO_DIR/install/setup.bash"

log "Building the remaining packages..."
colcon build \
    --packages-select \
        guarded_swarms_safety \
        guarded_swarms_control \
        guarded_swarms_sensing \
        guarded_swarms_tbcspn \
        guarded_swarms_bringup \
    --symlink-install \
    --event-handlers console_direct+
ok "ROS 2 workspace built."

# ------------------------------------------------------------------------------
# Step 7: Scenario assets and coastal world.
#
# Installs the rover airframe/model and world assets into the (pinned) PX4 tree,
# then generates the coastal world. This is what makes a fresh clone demo-ready:
# without it, `make demo-coastal` has no rover airframe and no coastal.sdf to
# load.
# ------------------------------------------------------------------------------
log "Step 7/${TOTAL_STEPS}: Installing scenario assets and generating the coastal world..."
source "$REPO_DIR/install/setup.bash"
if make -C "$REPO_DIR" setup-ugv setup-worlds gen-coastal; then
    ok "Scenario assets installed and coastal world generated."
else
    warn "Asset setup did not complete cleanly. You can re-run it later with:"
    warn "    make setup-ugv setup-worlds gen-coastal"
    warn "This is non-fatal for the software-only demos, but demo-coastal needs it."
fi
cd "$REPO_DIR"

# ------------------------------------------------------------------------------
# Step 8: Configure ~/.bashrc.
# ------------------------------------------------------------------------------
log "Step 8/${TOTAL_STEPS}: Configuring ~/.bashrc..."
BASHRC="$HOME/.bashrc"
add_to_bashrc() {
    local line="$1"
    if ! grep -qF "$line" "$BASHRC"; then
        echo "$line" >> "$BASHRC"
    fi
}
add_to_bashrc "source /opt/ros/humble/setup.bash"
add_to_bashrc "source $REPO_DIR/install/setup.bash"
ok "~/.bashrc configured."

# ------------------------------------------------------------------------------
# Make the utility scripts executable.
# ------------------------------------------------------------------------------
log "Configuring scripts..."
chmod +x "$REPO_DIR/scripts/"*.sh 2>/dev/null || true
ok "Scripts configured."

# ------------------------------------------------------------------------------
# Done.
# ------------------------------------------------------------------------------
echo ""
echo -e "${GREEN}============================================================${NC}"
echo -e "${GREEN}  Installation complete!${NC}"
echo -e "${GREEN}============================================================${NC}"
echo ""
echo "  Restart your terminal or run:"
echo "    source ~/.bashrc"
echo ""
echo "  The coastal case study (2 UAV + 1 UGV, sensing -> action):"
echo "    make demo-coastal            # terminal 1: the world (needs a GPU)"
echo "    ./scripts/test_pipeline.sh   # terminal 2: intruder, sensing, TB-CSPN,"
echo "                                 #             auto-authorise, report"
echo ""
echo "  Software-only safety demos (no PX4 / no Gazebo):"
echo "    make demo-safety-board       # + make demo-safety-sensors"
echo ""
echo "  Health check:  make check-coastal"
echo "  See README.md for full documentation."
echo ""