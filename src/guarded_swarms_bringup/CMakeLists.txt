cmake_minimum_required(VERSION 3.8)
project(guarded_swarms_bringup)

find_package(ament_cmake REQUIRED)

# Install all launch files, and the fleet file of the coastal scenario
install(DIRECTORY launch/
  DESTINATION share/${PROJECT_NAME}/launch
)
install(DIRECTORY config/
  DESTINATION share/${PROJECT_NAME}/config
)

ament_package()
