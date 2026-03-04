from setuptools import find_packages, setup
import os
from glob import glob

package_name = "guarded_swarms_safety"

setup(
    name=package_name,
    version="0.0.0",
    packages=find_packages(exclude=["test"]),
    data_files=[
        ("share/ament_index/resource_index/packages", ["resource/" + package_name]),
        ("share/" + package_name, ["package.xml"]),
        (os.path.join("share", package_name, "launch"), glob("launch/*.py")),
    ],
    install_requires=["setuptools"],
    zip_safe=True,
    maintainer="Luca D'Aurizio",
    maintainer_email='"daurizio.lc@gmail.com"',
    description="Analog safety enforcement layer for Guarded Swarms",
    license="Apache-2.0",
    extras_require={"test": ["pytest"]},
    entry_points={
        "console_scripts": [
            "safety_board_node = guarded_swarms_safety.safety_board_node:main",
            "mock_sensor_publisher = guarded_swarms_safety.mock_sensor_publisher:main",
        ],
    },
)
