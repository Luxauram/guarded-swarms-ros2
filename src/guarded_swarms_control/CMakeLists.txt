cmake_minimum_required(VERSION 3.8)
project(guarded_swarms_control)

if(CMAKE_COMPILER_IS_GNUCXX OR CMAKE_CXX_COMPILER_ID MATCHES "Clang")
  add_compile_options(-Wall -Wextra -Wpedantic)
endif()

# find dependencies
find_package(ament_cmake REQUIRED)
find_package(rclcpp REQUIRED)
find_package(px4_msgs REQUIRED)
find_package(geometry_msgs REQUIRED)

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
  rclcpp
  px4_msgs
  geometry_msgs
)

target_compile_features(offboard_control_node PUBLIC c_std_99 cxx_std_17)

# ============================================================================
# Install
# ============================================================================
install(TARGETS offboard_control_node
  DESTINATION lib/${PROJECT_NAME}
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
