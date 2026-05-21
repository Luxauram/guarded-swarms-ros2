cmake_minimum_required(VERSION 3.8)
project(guarded_swarms_bringup)

find_package(ament_cmake REQUIRED)

# Install all launch files
install(DIRECTORY launch/
  DESTINATION share/${PROJECT_NAME}/launch
)

ament_package()