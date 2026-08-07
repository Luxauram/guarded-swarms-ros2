cmake_minimum_required(VERSION 3.8)
project(guarded_swarms_tbcspn)

if(CMAKE_COMPILER_IS_GNUCXX OR CMAKE_CXX_COMPILER_ID MATCHES "Clang")
  add_compile_options(-Wall -Wextra -Wpedantic)
endif()

# ============================================================================
# Dependencies
# ============================================================================
find_package(ament_cmake REQUIRED)
find_package(rclcpp REQUIRED)
find_package(guarded_swarms_msgs REQUIRED)
find_package(px4_msgs REQUIRED)

# ============================================================================
# TB-CSPN transitions
#
# The seven transitions of Figure 4, instantiated by parameters over four node
# types: interpretation (T1/T2/T4), candidate join (T3/T5), mission release
# (T6), dispatch (T7). Only dispatch depends on px4_msgs: it reads the live UAV
# positions to assign the nearest one.
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

add_executable(dispatch_transition_node src/dispatch_transition_node.cpp)
target_include_directories(dispatch_transition_node PUBLIC
  $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
  $<INSTALL_INTERFACE:include>
)
ament_target_dependencies(dispatch_transition_node
  rclcpp guarded_swarms_msgs px4_msgs
)
target_compile_features(dispatch_transition_node PUBLIC c_std_99 cxx_std_17)

install(TARGETS
  interpretation_node
  candidate_transition_node
  mission_transition_node
  dispatch_transition_node
  DESTINATION lib/${PROJECT_NAME}
)

install(DIRECTORY config launch
  DESTINATION share/${PROJECT_NAME}
)

if(BUILD_TESTING)
  find_package(ament_lint_auto REQUIRED)
  set(ament_cmake_copyright_FOUND TRUE)
  set(ament_cmake_cpplint_FOUND TRUE)
  ament_lint_auto_find_test_dependencies()
endif()

ament_package()
