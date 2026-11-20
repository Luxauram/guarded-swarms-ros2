cmake_minimum_required(VERSION 3.8)
project(guarded_swarms_supervisor)

if(CMAKE_COMPILER_IS_GNUCXX OR CMAKE_CXX_COMPILER_ID MATCHES "Clang")
  add_compile_options(-Wall -Wextra -Wpedantic)
endif()

# ============================================================================
# Dependencies
# ============================================================================
find_package(ament_cmake REQUIRED)
find_package(rclcpp REQUIRED)
find_package(guarded_swarms_msgs REQUIRED)

# ============================================================================
# Scripted supervisor
#
# Stands in for the human supervisor of the mission-release transition (T6) in
# automated runs: one decision per target, after a configurable delay in
# simulated time.
# ============================================================================
add_executable(scripted_supervisor_node src/scripted_supervisor_node.cpp)
ament_target_dependencies(scripted_supervisor_node
  rclcpp guarded_swarms_msgs
)
target_compile_features(scripted_supervisor_node PUBLIC c_std_99 cxx_std_17)

install(TARGETS
  scripted_supervisor_node
  DESTINATION lib/${PROJECT_NAME}
)

install(DIRECTORY launch
  DESTINATION share/${PROJECT_NAME}
)

if(BUILD_TESTING)
  find_package(ament_lint_auto REQUIRED)
  set(ament_cmake_copyright_FOUND TRUE)
  set(ament_cmake_cpplint_FOUND TRUE)
  ament_lint_auto_find_test_dependencies()
endif()

ament_package()
