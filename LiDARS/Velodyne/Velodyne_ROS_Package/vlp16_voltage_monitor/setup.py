from glob import glob

from setuptools import find_packages, setup

package_name = 'vlp16_voltage_monitor'

setup(
    name=package_name,
    version='0.0.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages',
            ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml', 'README.md']),
        ('share/' + package_name + '/launch', glob('launch/*.launch.py')),
        ('share/' + package_name + '/config', glob('config/*.yaml')),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='jankii',
    maintainer_email='januel.torres@upr.edu',
    description='Monitor component supply voltages with ROS topics and warnings.',
    license='TODO: License declaration',
    extras_require={
        'test': [
            'pytest',
        ],
    },
    entry_points={
        'console_scripts': [
            'voltage_monitor = vlp16_voltage_monitor.voltage_monitor:main',
            'voltage_topic_monitor = vlp16_voltage_monitor.topic_monitor:main',
        ],
    },
)
