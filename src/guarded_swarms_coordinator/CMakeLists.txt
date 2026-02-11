cmake_minimum_required(VERSION 3.8)
project(guarded_swarms_coordinator)

if(CMAKE_COMPILER_IS_GNUCXX OR CMAKE_CXX_COMPILER_ID MATCHES "Clang")
  add_compile_options(-Wall -Wextra -Wpedantic)
endif()

find_package(ament_cmake REQUIRED)
find_package(ament_cmake_python REQUIRED)
find_package(rclpy REQUIRED)
find_package(std_msgs REQUIRED)
find_package(rosidl_default_generators REQUIRED)

rosidl_generate_interfaces(${PROJECT_NAME}
  "msg/Token.msg"
  "msg/GeometryToken.msg"
  "msg/AuthToken.msg"
  DEPENDENCIES std_msgs
)

ament_python_install_package(${PROJECT_NAME})

install(PROGRAMS
  DESTINATION lib/${PROJECT_NAME}
)

# ============================================================================
# Install
# ============================================================================
install(DIRECTORY
  launch
  DESTINATION share/${PROJECT_NAME}/
)

# ============================================================================
# Testing
# ============================================================================
if(BUILD_TESTING)
  find_package(ament_lint_auto REQUIRED)
  ament_lint_auto_find_test_dependencies()
endif()

ament_package()
