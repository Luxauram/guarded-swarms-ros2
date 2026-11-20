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
# Installs every dependency and builds the workspace on Ubuntu 22.04 LTS. Run
# it from the root of a clone, as your user: it calls sudo where it needs to.
#
#     ./install.sh
#
# Steps:
#   1. ROS 2 Humble, rosbridge and the Python libraries of the scripts
#   2. Gazebo Harmonic and its ROS 2 bridge
#   3. Micro XRCE-DDS Agent, the transport between PX4 and ROS 2
#   4. PX4 SITL, at the commit px4_msgs was generated from
#   5. The ROS 2 workspace: the submodules, the dependencies (rosdep), the build
#   6. ~/.bashrc
#
# Each step skips what is already in place, so the script can run again after
# a failure, or on a machine that already has part of the stack.
# ==============================================================================
set -eo pipefail

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
PX4_DIR="${PX4_DIR:-$HOME/PX4-Autopilot}"

# The release of Micro XRCE-DDS Agent that the PX4 documentation installs.
XRCE_AGENT_TAG="v2.4.3"

TOTAL_STEPS=6

log()  { echo -e "${BLUE}[install]${NC} $1"; }
ok()   { echo -e "${GREEN}[ok]${NC} $1"; }
warn() { echo -e "${YELLOW}[warn]${NC} $1"; }
fail() { echo -e "${RED}[error]${NC} $1"; exit 1; }

# apt without questions: a configuration file changed locally is kept.
apt_install() {
    sudo DEBIAN_FRONTEND=noninteractive apt-get install -y \
        -o Dpkg::Options::=--force-confdef -o Dpkg::Options::=--force-confold "$@"
}

# ------------------------------------------------------------------------------
# System check: Ubuntu 22.04, as a normal user.
# ------------------------------------------------------------------------------
log "Checking the system..."
if [ "$(id -u)" -eq 0 ]; then
    fail "Run this script as your user, not as root: it calls sudo where it needs to."
fi
# shellcheck disable=SC1091
. /etc/os-release
CODENAME="${UBUNTU_CODENAME:-${VERSION_CODENAME:-}}"
if [ "${ID:-}" != "ubuntu" ] || [ "${VERSION_ID:-}" != "22.04" ]; then
    fail "This script requires Ubuntu 22.04, the release ROS 2 Humble is packaged for. Detected: ${PRETTY_NAME:-unknown}"
fi
ok "System: ${PRETTY_NAME}"

sudo apt-get update
apt_install ca-certificates curl git software-properties-common

# ------------------------------------------------------------------------------
# Step 1: ROS 2 Humble.
#
# The apt source is set up as the ROS 2 documentation does it, with the
# ros2-apt-source package, which also keeps the signing key up to date.
# rosbridge serves the supervisor console; matplotlib, NumPy and PyYAML are
# used by the scripts under scripts/.
# ------------------------------------------------------------------------------
log "Step 1/${TOTAL_STEPS}: ROS 2 Humble..."
if [ -f /etc/apt/sources.list.d/ros2.sources ] || [ -f /etc/apt/sources.list.d/ros2.list ]; then
    ok "ROS 2 apt source already configured."
else
    sudo add-apt-repository -y universe
    ROS_APT_SOURCE_VERSION=$(curl -fsSL https://api.github.com/repos/ros-infrastructure/ros-apt-source/releases/latest \
        | grep -F '"tag_name"' | awk -F'"' '{print $4}')
    [ -n "$ROS_APT_SOURCE_VERSION" ] || fail "Could not read the latest release of ros-apt-source."
    curl -fsSL -o /tmp/ros2-apt-source.deb \
        "https://github.com/ros-infrastructure/ros-apt-source/releases/download/${ROS_APT_SOURCE_VERSION}/ros2-apt-source_${ROS_APT_SOURCE_VERSION}.${CODENAME}_all.deb"
    sudo dpkg -i /tmp/ros2-apt-source.deb
    rm -f /tmp/ros2-apt-source.deb
    sudo apt-get update
    # On a fresh 22.04 the systemd and udev packages must be up to date before
    # ROS 2 is installed, or apt can remove critical system packages.
    sudo DEBIAN_FRONTEND=noninteractive apt-get upgrade -y \
        -o Dpkg::Options::=--force-confdef -o Dpkg::Options::=--force-confold
    ok "ROS 2 apt source added."
fi
apt_install \
    ros-humble-desktop \
    ros-humble-rosbridge-suite \
    python3-colcon-common-extensions \
    python3-rosdep \
    python3-matplotlib \
    python3-numpy \
    python3-yaml
ok "ROS 2 Humble installed."

# ------------------------------------------------------------------------------
# Step 2: Gazebo Harmonic.
#
# Its ROS 2 bridge, ros-humble-ros-gzharmonic, comes from the Gazebo
# repository: the ros-humble-ros-gz packages of ROS 2 are built for Gazebo
# Fortress, and conflict with it.
# ------------------------------------------------------------------------------
log "Step 2/${TOTAL_STEPS}: Gazebo Harmonic..."
if [ -f /etc/apt/sources.list.d/gazebo-stable.list ]; then
    ok "Gazebo apt source already configured."
else
    sudo curl -fsSL https://packages.osrfoundation.org/gazebo.gpg \
        -o /usr/share/keyrings/pkgs-osrf-archive-keyring.gpg
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/pkgs-osrf-archive-keyring.gpg] http://packages.osrfoundation.org/gazebo/ubuntu-stable ${CODENAME} main" \
        | sudo tee /etc/apt/sources.list.d/gazebo-stable.list > /dev/null
    sudo apt-get update
    ok "Gazebo apt source added."
fi
apt_install gz-harmonic ros-humble-ros-gzharmonic
ok "Gazebo Harmonic and its ROS 2 bridge installed."

# ------------------------------------------------------------------------------
# Step 3: Micro XRCE-DDS Agent, built from its release tag.
# ------------------------------------------------------------------------------
log "Step 3/${TOTAL_STEPS}: Micro XRCE-DDS Agent..."
if command -v MicroXRCEAgent >/dev/null 2>&1; then
    ok "MicroXRCEAgent already installed."
else
    apt_install build-essential cmake
    AGENT_SRC="$(mktemp -d)"
    git clone --depth 1 --branch "$XRCE_AGENT_TAG" \
        https://github.com/eProsima/Micro-XRCE-DDS-Agent.git "$AGENT_SRC"
    (
        cd "$AGENT_SRC"
        mkdir build
        cd build
        cmake ..
        make -j"$(nproc)"
        sudo make install
    )
    sudo ldconfig /usr/local/lib/
    rm -rf "$AGENT_SRC"
    ok "MicroXRCEAgent ${XRCE_AGENT_TAG} installed."
fi

# ------------------------------------------------------------------------------
# Step 4: PX4 SITL.
#
# The libraries the PX4 build needs for its Gazebo plugins, and xterm, in which
# make demo-coastal opens Gazebo, the agents and the PX4 instances. Tools/setup/
# ubuntu.sh installs the rest; --no-sim-tools keeps it from installing Gazebo,
# which step 2 did.
# ------------------------------------------------------------------------------
log "Step 4/${TOTAL_STEPS}: PX4 SITL at ${PX4_COMMIT:0:8}..."
apt_install \
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
    xterm

if [ -d "$PX4_DIR" ]; then
    CURRENT_COMMIT=$(git -C "$PX4_DIR" rev-parse HEAD 2>/dev/null || echo "unknown")
    if [ "$CURRENT_COMMIT" = "$PX4_COMMIT" ]; then
        ok "PX4-Autopilot already at the pinned commit."
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
    log "Cloning PX4-Autopilot at the pinned commit..."
    # Blobless clone: the full history, needed to check out an arbitrary
    # commit, with the file contents fetched on demand, so it stays fast.
    git clone --filter=blob:none https://github.com/PX4/PX4-Autopilot.git "$PX4_DIR"
    git -C "$PX4_DIR" checkout -B "$PX4_BRANCH" "$PX4_COMMIT"
    git -C "$PX4_DIR" submodule update --init --recursive
    ok "PX4-Autopilot cloned and pinned."
fi

if [ -f "$PX4_DIR/build/px4_sitl_default/bin/px4" ]; then
    ok "PX4 SITL already built."
else
    log "Installing the dependencies of PX4 (this may take a few minutes)..."
    (cd "$PX4_DIR" && bash ./Tools/setup/ubuntu.sh --no-nuttx --no-sim-tools)
    log "Building PX4 SITL (this will take 10-20 minutes)..."
    make -C "$PX4_DIR" px4_sitl_default
    ok "PX4 SITL built."
fi

# ------------------------------------------------------------------------------
# Step 5: The ROS 2 workspace.
#
# rosdep installs what the package manifests declare. It skips ros_gz_sim and
# ros_gz_bridge, which step 2 installed: rosdep would install their Fortress
# builds instead. colcon builds the packages in the order of their
# dependencies.
# ------------------------------------------------------------------------------
log "Step 5/${TOTAL_STEPS}: The ROS 2 workspace..."
git -C "$REPO_DIR" submodule update --init --recursive
if [ ! -f /etc/ros/rosdep/sources.list.d/20-default.list ]; then
    sudo rosdep init
fi
rosdep update --rosdistro humble
# shellcheck disable=SC1091
source /opt/ros/humble/setup.bash
rosdep install --from-paths "$REPO_DIR/src" --ignore-src -y --rosdistro humble \
    --skip-keys "ros_gz_sim ros_gz_bridge"
(cd "$REPO_DIR" && colcon build --symlink-install)
ok "ROS 2 workspace built."

# ------------------------------------------------------------------------------
# Step 6: Configure ~/.bashrc.
# ------------------------------------------------------------------------------
log "Step 6/${TOTAL_STEPS}: Configuring ~/.bashrc..."
BASHRC="$HOME/.bashrc"
add_to_bashrc() {
    local line="$1"
    if ! grep -qF "$line" "$BASHRC" 2>/dev/null; then
        echo "$line" >> "$BASHRC"
    fi
}
add_to_bashrc "source /opt/ros/humble/setup.bash"
add_to_bashrc "source $REPO_DIR/install/setup.bash"
ok "$BASHRC configured."

if [ ! -e /proc/driver/nvidia/version ]; then
    warn "The NVIDIA driver is not loaded. Gazebo renders the lidars on the GPU,"
    warn "with the OpenGL driver of this machine: make check-gpu shows the GPU."
fi

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
echo "    make demo-coastal                     # terminal 1: the world (needs a GPU)"
echo "    ./scripts/pipeline/test_pipeline.sh   # terminal 2: intruder, sensing, TB-CSPN,"
echo "                                          #   auto-authorise, report"
echo ""
echo "  Software-only safety demos (no PX4 / no Gazebo):"
echo "    make demo-safety-board                # + make demo-safety-sensors"
echo ""
echo "  Health check:  make check-coastal"
echo "  See docs/README.md for the full documentation."
echo ""