from glob import glob

from setuptools import find_packages, setup


setup(
    name='oak_d_ros2',
    version='0.2.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/oak_d_ros2']),
        ('share/oak_d_ros2', ['package.xml']),
        ('share/oak_d_ros2/launch', glob('launch/*.launch.py')),
        ('share/oak_d_ros2/config', glob('config/*.yaml')),
        ('share/oak_d_ros2/scripts', [
            '../../Object_Detection_With_Distance.py',
        ]),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='lidron',
    maintainer_email='lidron@users.noreply.github.com',
    description='Distance-only ROS bridge for the original OAK-D viewer',
    license='MIT',
    entry_points={'console_scripts': [
        'distances = oak_d_ros2.node:main',
        'detector = oak_d_ros2.node:main',
        'distance_subscriber = oak_d_ros2.subscriber:main',
    ]},
)
