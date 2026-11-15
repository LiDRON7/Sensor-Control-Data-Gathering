"""Keep synthetic camera traffic separate from a running physical camera."""

import os

import pytest


@pytest.fixture(autouse=True)
def isolated_ros_domain(monkeypatch):
    monkeypatch.setenv('ROS_DOMAIN_ID', os.environ.get('OAK_TEST_ROS_DOMAIN_ID', '101'))
