# Copyright 2026 Luca D'Aurizio
# Licensed under Apache-2.0
# Guarded Swarms ROS2 Development Container

FROM osrf/ros:humble-desktop

ENV DEBIAN_FRONTEND=noninteractive
WORKDIR /workspace

# ============================================================================
# LAYER 1: Essential Tools + OpenGL Support
# ============================================================================
RUN apt-get update && apt-get install -y \
    python3-colcon-common-extensions \
    python3-pip \
    python3-rosdep \
    git \
    wget \
    curl \
    cmake \
    build-essential \
    mesa-utils \
    libgl1-mesa-glx \
    libegl1-mesa \
    libgles2-mesa \
    && rm -rf /var/lib/apt/lists/*

# ============================================================================
# LAYER 2: Gazebo Harmonic
# ============================================================================
RUN wget -q https://packages.osrfoundation.org/gazebo.gpg \
    -O /usr/share/keyrings/pkgs-osrf-archive-keyring.gpg && \
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/pkgs-osrf-archive-keyring.gpg] \
    http://packages.osrfoundation.org/gazebo/ubuntu-stable $(lsb_release -cs) main" \
    | tee /etc/apt/sources.list.d/gazebo-stable.list > /dev/null && \
    apt-get update && apt-get install -y \
    gz-harmonic \
    ros-humble-ros-gzharmonic \
    && rm -rf /var/lib/apt/lists/*

# ============================================================================
# LAYER 3: Micro-XRCE-DDS Agent (PX4 Bridge)
# ============================================================================
RUN cd /tmp && \
    git clone --depth 1 https://github.com/eProsima/Micro-XRCE-DDS-Agent.git && \
    cd Micro-XRCE-DDS-Agent && \
    mkdir build && cd build && \
    cmake .. && \
    make -j$(nproc) && \
    make install && \
    ldconfig /usr/local/lib/ && \
    cd / && \
    rm -rf /tmp/Micro-XRCE-DDS-Agent

# ============================================================================
# LAYER 4: PX4 Dependencies
# ============================================================================
RUN apt-get update && apt-get install -y \
    bc \
    gstreamer1.0-plugins-bad \
    gstreamer1.0-plugins-base \
    gstreamer1.0-plugins-good \
    gstreamer1.0-plugins-ugly \
    gstreamer1.0-libav \
    libeigen3-dev \
    libgstreamer-plugins-base1.0-dev \
    libopencv-dev \
    libxml2-utils \
    pkg-config \
    protobuf-compiler \
    && rm -rf /var/lib/apt/lists/*

# ============================================================================
# LAYER 5: Web Dashboard Backend Dependencies
# ============================================================================
RUN pip3 install --no-cache-dir \
    fastapi==0.104.1 \
    uvicorn[standard]==0.24.0 \
    websockets==12.0 \
    pydantic==2.5.0 \
    python-multipart==0.0.6

# ============================================================================
# LAYER 6: Frontend Tools (Bun + TypeScript)
# ============================================================================
RUN curl -fsSL https://bun.sh/install | bash && \
    ln -s /root/.bun/bin/bun /usr/local/bin/bun && \
    ln -s /root/.bun/bin/bunx /usr/local/bin/bunx && \
    /root/.bun/bin/bun add -g typescript

ENV BUN_INSTALL="/root/.bun"
ENV PATH="${BUN_INSTALL}/bin:${PATH}"

# ============================================================================
# LAYER 7: Auto-source ROS 2 Workspace
# ============================================================================
RUN echo "source /opt/ros/humble/setup.bash" >> ~/.bashrc && \
    echo "if [ -f /workspace/install/setup.bash ]; then source /workspace/install/setup.bash; fi" >> ~/.bashrc

CMD ["/bin/bash"]
