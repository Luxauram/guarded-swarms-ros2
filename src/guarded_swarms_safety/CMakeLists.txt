cmake_minimum_required(VERSION 3.8)
project(guarded_swarms_safety)

if(CMAKE_COMPILER_IS_GNUCXX OR CMAKE_CXX_COMPILER_ID MATCHES "Clang")
  add_compile_options(-Wall -Wextra -Wpedantic)
endif()

# ============================================================================
# Dependencies
# ============================================================================
find_package(ament_cmake REQUIRED)
find_package(rclcpp REQUIRED)
find_package(sensor_msgs REQUIRED)
find_package(std_msgs REQUIRED)

# ============================================================================
# Executable: safety_board_node
# ============================================================================
add_executable(safety_board_node
  src/safety_board_node.cpp
)

target_include_directories(safety_board_node PUBLIC
  $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
  $<INSTALL_INTERFACE:include>
)

ament_target_dependencies(safety_board_node
  rclcpp
  sensor_msgs
  std_msgs
)

target_compile_features(safety_board_node PUBLIC cxx_std_17)

# ============================================================================
# Executable: mock_sensor_publisher
# ============================================================================
add_executable(mock_sensor_publisher
  src/mock_sensor_publisher.cpp
)

target_include_directories(mock_sensor_publisher PUBLIC
  $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
  $<INSTALL_INTERFACE:include>
)

ament_target_dependencies(mock_sensor_publisher
  rclcpp
  sensor_msgs
  std_msgs
)

target_compile_features(mock_sensor_publisher PUBLIC cxx_std_17)

# ============================================================================
# Install
# ============================================================================
install(TARGETS
  safety_board_node
  mock_sensor_publisher
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
