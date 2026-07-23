#!/usr/bin/env bash
cd "$HOME/PX4-Autopilot" && \
  __NV_PRIME_RENDER_OFFLOAD=1 __GLX_VENDOR_LIBRARY_NAME=nvidia MESA_GL_VERSION_OVERRIDE=4.5 \
  PX4_GZ_WORLD=urban_uav \
  GZ_SIM_RESOURCE_PATH="$1" \
  make px4_sitl gz_x500_lidar_front