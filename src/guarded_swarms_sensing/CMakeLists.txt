cmake_minimum_required(VERSION 3.8)
project(guarded_swarms_sensing)

if(CMAKE_COMPILER_IS_GNUCXX OR CMAKE_CXX_COMPILER_ID MATCHES "Clang")
  add_compile_options(-Wall -Wextra -Wpedantic)
endif()

# find dependencies
find_package(ament_cmake REQUIRED)
find_package(rclcpp REQUIRED)
find_package(geometry_msgs REQUIRED)
find_package(guarded_swarms_msgs REQUIRED)
find_package(std_msgs REQUIRED)
find_package(px4_msgs REQUIRED)

# ============================================================================
# Consultant agents
#
# Each sensing modality of the coastal scenario (IET 5.1) is one node. They
# synthesise ObsTokens from target ground truth using a per-modality coverage
# and error model. The coverage geometry is a simulation model, not specified
# by the paper.
# ============================================================================
add_executable(radar_agent_node src/radar_agent_node.cpp)
target_include_directories(radar_agent_node PUBLIC
  $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
  $<INSTALL_INTERFACE:include>
)
ament_target_dependencies(radar_agent_node
  rclcpp geometry_msgs guarded_swarms_msgs
)
target_compile_features(radar_agent_node PUBLIC c_std_99 cxx_std_17)

add_executable(rf_agent_node src/rf_agent_node.cpp)
target_include_directories(rf_agent_node PUBLIC
  $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
  $<INSTALL_INTERFACE:include>
)
ament_target_dependencies(rf_agent_node
  rclcpp geometry_msgs std_msgs guarded_swarms_msgs
)
target_compile_features(rf_agent_node PUBLIC c_std_99 cxx_std_17)

add_executable(acoustic_agent_node src/acoustic_agent_node.cpp)
target_include_directories(acoustic_agent_node PUBLIC
  $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
  $<INSTALL_INTERFACE:include>
)
ament_target_dependencies(acoustic_agent_node
  rclcpp geometry_msgs guarded_swarms_msgs
)
target_compile_features(acoustic_agent_node PUBLIC c_std_99 cxx_std_17)

add_executable(eo_agent_node src/eo_agent_node.cpp)
target_include_directories(eo_agent_node PUBLIC
  $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
  $<INSTALL_INTERFACE:include>
)
ament_target_dependencies(eo_agent_node
  rclcpp geometry_msgs px4_msgs guarded_swarms_msgs
)
target_compile_features(eo_agent_node PUBLIC c_std_99 cxx_std_17)

install(TARGETS
  radar_agent_node
  rf_agent_node
  acoustic_agent_node
  eo_agent_node
  DESTINATION lib/${PROJECT_NAME}
)

install(DIRECTORY config launch
  DESTINATION share/${PROJECT_NAME}
)

if(BUILD_TESTING)
  find_package(ament_lint_auto REQUIRED)
  # the following line skips the linter which checks for copyrights
  # comment the line when a copyright and license is added to all source files
  set(ament_cmake_copyright_FOUND TRUE)
  # the following line skips cpplint (only works in a git repo)
  # comment the line when this package is in a git repo and when
  # a copyright and license is added to all source files
  set(ament_cmake_cpplint_FOUND TRUE)
  ament_lint_auto_find_test_dependencies()
endif()

ament_package()
