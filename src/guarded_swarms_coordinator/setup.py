from setuptools import find_packages, setup
import os
from glob import glob

package_name = 'guarded_swarms_coordinator'

setup(
    name=package_name,
    version='0.0.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages',
            ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        (os.path.join('share', package_name, 'launch'),
            glob('launch/*.py') if os.path.exists('launch') else []),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='Luca D\'Aurizio',
    maintainer_email='daurizio.lc@gmail.com',
    description='Token-based coordination system for Guarded Swarms',
    license='Apache-2.0',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'coordinator_node = guarded_swarms_coordinator.coordinator_node:main',
            'agent_node = guarded_swarms_coordinator.agent_node:main',
        ],
    },
)
