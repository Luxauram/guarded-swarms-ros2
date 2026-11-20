cmake_minimum_required(VERSION 3.8)
project(guarded_swarms_gz)

find_package(ament_cmake REQUIRED)

# Install world files to share/guarded_swarms_gz/worlds/
install(
  DIRECTORY worlds/
  DESTINATION share/${PROJECT_NAME}/worlds
)

# Install model files to share/guarded_swarms_gz/models/
install(
  DIRECTORY models/
  DESTINATION share/${PROJECT_NAME}/models
)

ament_package()
