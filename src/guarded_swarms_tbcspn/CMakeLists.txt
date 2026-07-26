cmake_minimum_required(VERSION 3.8)
project(guarded_swarms_tbcspn)

if(CMAKE_COMPILER_IS_GNUCXX OR CMAKE_CXX_COMPILER_ID MATCHES "Clang")
  add_compile_options(-Wall -Wextra -Wpedantic)
endif()

# find dependencies
find_package(ament_cmake REQUIRED)
find_package(rclcpp REQUIRED)
find_package(guarded_swarms_msgs REQUIRED)

# ============================================================================
# TB-CSPN transitions
# ============================================================================
add_executable(interpretation_node src/interpretation_node.cpp)
target_include_directories(interpretation_node PUBLIC
  $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
  $<INSTALL_INTERFACE:include>
)
ament_target_dependencies(interpretation_node
  rclcpp guarded_swarms_msgs
)
target_compile_features(interpretation_node PUBLIC c_std_99 cxx_std_17)

add_executable(candidate_transition_node src/candidate_transition_node.cpp)
target_include_directories(candidate_transition_node PUBLIC
  $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
  $<INSTALL_INTERFACE:include>
)
ament_target_dependencies(candidate_transition_node
  rclcpp guarded_swarms_msgs
)
target_compile_features(candidate_transition_node PUBLIC c_std_99 cxx_std_17)

add_executable(mission_transition_node src/mission_transition_node.cpp)
target_include_directories(mission_transition_node PUBLIC
  $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
  $<INSTALL_INTERFACE:include>
)
ament_target_dependencies(mission_transition_node
  rclcpp guarded_swarms_msgs
)
target_compile_features(mission_transition_node PUBLIC c_std_99 cxx_std_17)

install(TARGETS
  interpretation_node
  candidate_transition_node
  mission_transition_node
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
