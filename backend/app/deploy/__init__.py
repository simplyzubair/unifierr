"""Unifierr deployment engine package."""
from app.deploy.catalog import CATALOG, AppSpec
from app.deploy.detect import DetectedApp, detect_apps
from app.deploy.docker_manager import ContainerInfo, DockerManager
from app.deploy.environment import EnvironmentReport, detect_environment
from app.deploy.folders import FolderReport, check_folders, prepare_folders
from app.deploy.keys import (
    generate_api_key,
    preseed_arr_config,
    preseed_qbittorrent,
    read_arr_api_key,
    read_bazarr_api_key,
)

__all__ = [
    "AppSpec",
    "CATALOG",
    "ContainerInfo",
    "DetectedApp",
    "DockerManager",
    "EnvironmentReport",
    "FolderReport",
    "check_folders",
    "detect_apps",
    "detect_environment",
    "generate_api_key",
    "prepare_folders",
    "preseed_arr_config",
    "preseed_qbittorrent",
    "read_arr_api_key",
    "read_bazarr_api_key",
]
