#!/usr/bin/env bash
cd "$HOME/PX4-Autopilot/build/px4_sitl_default" && \
  PX4_GZ_STANDALONE=1 \
  PX4_SYS_AUTOSTART=4009 \
  PX4_SIM_MODEL=r1_rover \
  PX4_GZ_WORLD=urban_uav \
  PX4_GZ_MODEL_POSE="10,10" \
  ./bin/px4 -i 1