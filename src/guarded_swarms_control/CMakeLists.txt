cmake_minimum_required(VERSION 3.8)
project(guarded_swarms_control)

if(CMAKE_COMPILER_IS_GNUCXX OR CMAKE_CXX_COMPILER_ID MATCHES "Clang")
  add_compile_options(-Wall -Wextra -Wpedantic)
endif()

# ============================================================================
# Dependencies
# ============================================================================
find_package(ament_cmake REQUIRED)
find_package(rclcpp REQUIRED)
find_package(px4_msgs REQUIRED)
find_package(geometry_msgs REQUIRED)
find_package(std_msgs REQUIRED)
find_package(sensor_msgs REQUIRED)
find_package(nav_msgs REQUIRED)
find_package(guarded_swarms_msgs REQUIRED)

# ============================================================================
# Executable: offboard_control_node
# ============================================================================
add_executable(offboard_control_node
  src/offboard_control_node.cpp
)

target_include_directories(offboard_control_node PUBLIC
  $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
  $<INSTALL_INTERFACE:include>
)

ament_target_dependencies(offboard_control_node
  rclcpp px4_msgs geometry_msgs
)

target_compile_features(offboard_control_node PUBLIC c_std_99 cxx_std_17)

# ============================================================================
# Executable: command_bridge_node
# ============================================================================
add_executable(command_bridge_node
  src/command_bridge_node.cpp
)

target_include_directories(command_bridge_node PUBLIC
  $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
  $<INSTALL_INTERFACE:include>
)

ament_target_dependencies(command_bridge_node
  rclcpp std_msgs guarded_swarms_msgs
)

target_compile_features(command_bridge_node PUBLIC c_std_99 cxx_std_17)

# ============================================================================
# Executable: px4_safety_bridge_node
# ============================================================================
add_executable(px4_safety_bridge_node
  src/px4_safety_bridge_node.cpp
)

target_include_directories(px4_safety_bridge_node PUBLIC
  $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
  $<INSTALL_INTERFACE:include>
)

ament_target_dependencies(px4_safety_bridge_node
  rclcpp px4_msgs sensor_msgs std_msgs
)

target_compile_features(command_bridge_node PUBLIC c_std_99 cxx_std_17)

# ============================================================================
# Executable: rover_control_node
# ============================================================================
add_executable(rover_control_node
  src/rover_control_node.cpp
)
target_include_directories(rover_control_node PUBLIC
  $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
  $<INSTALL_INTERFACE:include>
)
ament_target_dependencies(rover_control_node
  rclcpp px4_msgs std_msgs
)
target_compile_features(rover_control_node PUBLIC c_std_99 cxx_std_17) 

# ============================================================================
# Executable: intruder_node
#
# Scenario machinery, not part of the swarm: it plays the hostile aerial
# target so the sensing and coordination layers have something to react to.
# ============================================================================
add_executable(intruder_node
  src/intruder_node.cpp
)
target_include_directories(intruder_node PUBLIC
  $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
  $<INSTALL_INTERFACE:include>
)
ament_target_dependencies(intruder_node
  rclcpp geometry_msgs nav_msgs std_msgs
)
target_compile_features(intruder_node PUBLIC c_std_99 cxx_std_17)

add_executable(uav_worker_node src/uav_worker_node.cpp)
target_include_directories(uav_worker_node PUBLIC
  $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
  $<INSTALL_INTERFACE:include>
)
ament_target_dependencies(uav_worker_node
  rclcpp px4_msgs guarded_swarms_msgs
)
target_compile_features(uav_worker_node PUBLIC c_std_99 cxx_std_17)

# ============================================================================
# Install
# ============================================================================
install(TARGETS
  offboard_control_node
  command_bridge_node
  px4_safety_bridge_node
  rover_control_node
  intruder_node
  uav_worker_node
DESTINATION lib/${PROJECT_NAME}
)

install(DIRECTORY include/
  DESTINATION include
)

# ============================================================================
# Testing
# ============================================================================
if(BUILD_TESTING)
  find_package(ament_lint_auto REQUIRED)
  set(ament_cmake_copyright_FOUND TRUE)
  set(ament_cmake_cpplint_FOUND TRUE)
  ament_lint_auto_find_test_dependencies()
endif()

ament_package()
