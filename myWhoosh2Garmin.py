#!/usr/bin/env python3
"""
Script name: myWhoosh2Garmin.py
Usage: "python3 myWhoosh2Garmin.py"
Description:    Checks for MyNewActivity-<myWhooshVersion>.fit
                Adds avg power and heartrade
                Removes temperature
                Creates backup for the file with a timestamp as a suffix
Credits:        Garth by matin - for authenticating and uploading with 
                Garmin Connect.
                https://github.com/matin/garth
                Fit_tool by mtucker - for parsing the fit file.
                https://bitbucket.org/stagescycling/python_fit_tool.git/src
                mw2gc by embeddedc - used as an example to fix the avg's. 
                https://github.com/embeddedc/mw2gc
"""
import os
import json
import subprocess
import sys
import logging
import tkinter as tk
from datetime import datetime
from getpass import getpass
from pathlib import Path
import importlib.util

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
file_handler = logging.FileHandler('myWhoosh2Garmin.log')
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)


def get_pip_command():
    """
    Check if pip is available and return the pip command.

    Returns:
        list or None: A list containing the pip command if available, 
                      otherwise None.
    """
    try:
        subprocess.check_call(
            [sys.executable, "-m", "pip", "--version"], 
            stdout=subprocess.PIPE, 
            stderr=subprocess.PIPE
        )
        return [sys.executable, "-m", "pip"]  
    except subprocess.CalledProcessError:
        return None


def install_package(package):
    """
    Install the specified package using pip.

    Args:
        package (str): The name of the package to install.

    Returns:
        None
    """
    pip_command = get_pip_command()
    if pip_command:
        try:
            logger.error(f"Installing missing package: {package}")
            subprocess.check_call(
                pip_command + ["install", package],
                stdout=subprocess.PIPE, 
                stderr=subprocess.PIPE
            )
        except subprocess.CalledProcessError as e:
            logger.error(f"Error installing {package}: {e}")
    else:
        logger.info("pip is not available. Unable to install packages.")


def ensure_packages():
    """
    Ensure all required packages are installed. If a package is missing,
    it will attempt to install it.

    Returns:
        None
    """
    required_packages = [
        "garth",
        "fit_tool",
        "tkinter",
    ]
    for package in required_packages:
        if not importlib.util.find_spec(package):
            print(f"Installing missing package: {package}")
            install_package(package)

import garth
from garth.exc import GarthException, GarthHTTPError
from fit_tool.fit_file import FitFile
from fit_tool.fit_file_builder import FitFileBuilder
from fit_tool.profile.messages.file_creator_message import FileCreatorMessage
from fit_tool.profile.messages.record_message import (
    RecordMessage,
    RecordTemperatureField
)
from fit_tool.profile.messages.session_message import SessionMessage
from fit_tool.profile.messages.lap_message import LapMessage


TOKENS_PATH = Path(".garth")
FILE_DIALOG_TITLE = "MyWhoosh2Garmin"
MYWHOOSH_PREFIX_WINDOWS = "MyWhooshTechnologyService.MyWhoosh_"


def get_fitfile_location() -> Path:
    """
    Get the location of the FIT file directory based on the operating system.

    Returns:
        Path: The path to the FIT file directory.

    Raises:
        RuntimeError: If the operating system is unsupported.
        SystemExit: If the target path does not exist.
    """
    if os.name == "posix":  # macOS and Linux
        target_path = (
            Path.home()
            / "Library"
            / "Containers"
            / "com.whoosh.whooshgame"
            / "Data"
            / "Library"
            / "Application Support"
            / "Epic"
            / "MyWhoosh"
            / "Content"
            / "Data"
        )
        if target_path.is_dir():
            return target_path
        else:
            logger.error(f"Target path {target_path} does not exist. "
                         "Check your MyWhoosh installation.")
            sys.exit(1)
    elif os.name == "nt":  # Windows
        base_path = Path.home() / "AppData" / "Local" / "Packages"
        for directory in base_path.iterdir():
            if (directory.is_dir() and 
                    directory.name.startswith(MYWHOOSH_PREFIX_WINDOWS)):
                target_path = (
                        directory
                        / "LocalCache"
                        / "Local"
                        / "MyWhoosh"
                        / "Content"
                        / "Data"
                )
                if target_path.is_dir():
                    return target_path
                else:
                    logger.error(f"Target path {target_path} does not exist."
                                 "Check your MyWhoosh installation.")
                    sys.exit(1)
    else:
        raise RuntimeError("Unsupported operating system")
        return None


def get_backup_path(json_file='backup_path.json') -> Path:
    """
    This function checks if a backup path already exists in a JSON file.
    If it does, it returns the stored path. If the file does not exist, 
    it prompts the user to select a directory via a file dialog, saves 
    the selected path to the JSON file, and returns it.

    Args:
        json_file (str): Path to the JSON file containing the backup path.

    Returns:
        str or None: The selected backup path or None if no path was selected.
    """
    if os.path.exists(json_file):
        with open(json_file, 'r') as f:
            backup_path = json.load(f).get('backup_path')
        if backup_path and os.path.isdir(backup_path):
            logger.info(f"Using backup path from JSON: {backup_path}")
            return Path(backup_path)
        else:
            logger.error("Invalid backup path stored in JSON.")
            sys.exit(1)
    else:
        root = tk.Tk()
        root.withdraw() 
        backup_path = filedialog.askdirectory(title=f"Select {FILE_DIALOG_TITLE} Directory")
        if not backup_path:
            logger.info("No directory selected, exiting.")
            return None
        with open(json_file, 'w') as f:
            json.dump({'backup_path': backup_path}, f)
        logger.info(f"Backup path saved to {json_file}")
    return Path(backup_path)


FITFILE_LOCATION = get_fitfile_location()
BACKUP_FITFILE_LOCATION = get_backup_path()


def get_credentials_for_garmin():
    """
    Prompt the user for Garmin credentials and authenticate using Garth.

    Returns:
        None

    Exits:
        Exits with status 1 if authentication fails.
    """
    username = input("Username: ")
    password = getpass("Password: ")
    logger.info("Authenticating...")
    try:
        garth.login(username, password)
        garth.save(".garth")
        logger.info("Successfully authenticated!")
    except GarthHTTPError:
        logger.info("Wrong credentials. Please check username and password.")
        sys.exit(1)


def authenticate_to_garmin():
    """
    Authenticate the user to Garmin by checking for existing tokens and 
    resuming the session, or prompting for credentials if no session 
    exists or the session is expired.

    Returns:
        None

    Exits:
        Exits with status 1 if authentication fails.
    """
    try:
        if TOKENS_PATH.exists():
            garth.resume(".garth")
            try:
                logger.info(f"Authenticated as: {garth.client.username}")
            except GarthException:
                logger.info("Session expired. Re-authenticating...")
                get_credentials_for_garmin()
        else:
            logger.info("No existing session. Please log in.")
            get_credentials_for_garmin()
    except GarthException as e:
        logger.info(f"Authentication error: {e}")
        sys.exit(1)


def cleanup_fit_file(fit_file_path: Path, new_file_path: Path) -> None:
    """
    Clean up the FIT file by processing and removing unnecessary fields.
    Also, calculate average values for cadence, power, and heart rate.

    Args:
        fit_file_path (Path): The path to the input FIT file.
        new_file_path (Path): The path to save the processed FIT file.

    Returns:
        None
    """
    builder = FitFileBuilder()
    fit_file = FitFile.from_file(str(fit_file_path))
    cadence_values = []
    power_values = []
    heart_rate_values = []

    for record in fit_file.records:
        message = record.message
        if isinstance(message, (FileCreatorMessage, LapMessage)):
            continue
        if isinstance(message, RecordMessage):
            message.remove_field(RecordTemperatureField.ID)
            cadence_values.append(message.cadence 
                                  if message.cadence 
                                  else 0)
            power_values.append(message.power 
                                if message.power 
                                else 0)
            heart_rate_values.append(message.heart_rate 
                                     if message.heart_rate 
                                     else 0)
        if isinstance(message, SessionMessage):
            if not message.avg_cadence:
                message.avg_cadence = (
                    sum(cadence_values) / len(cadence_values)
                    if cadence_values
                    else 0
                )
            if not message.avg_power:
                message.avg_power = (
                    sum(power_values) / len(power_values)
                    if power_values
                    else 0
                )
            if not message.avg_heart_rate:
                message.avg_heart_rate = (
                    sum(heart_rate_values) / len(heart_rate_values)
                    if heart_rate_values
                    else 0
                )
            cadence_values = []
            power_values = []
            heart_rate_values = []
        builder.add(message)
    out_file = builder.build()
    out_file.to_file(str(new_file_path))
    logger.info(f"Cleaned-up file saved as {new_file_path.name}")


def cleanup_and_save_fit_file(fitfile_location: Path) -> Path:
    """
    Clean up the most recent .fit file in a directory and save it 
    with a timestamped filename.

    Args:
        fitfile_location (Path): The directory containing the .fit files.

    Returns:
        Path: The path to the newly saved and cleaned .fit file, 
        or an empty Path if no .fit file is found or if the path is invalid.
    """
    if fitfile_location.is_dir():
        logger.debug(f"Checking for .fit files in directory: "
                     f"{fitfile_location}")
        fit_files = list(fitfile_location.glob("*.fit"))
        if fit_files:
            logger.debug("Found the following .fit files:")
            fit_file = max(fit_files, key=lambda f: f.stat().st_mtime)
            timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
            new_filename = f"{fit_file.stem}_{timestamp}.fit"
            if not BACKUP_FITFILE_LOCATION.exists():
                logger.error(f"{BACKUP_FITFILE_LOCATION} does not exist. "
                             "Did you delete it?")
            new_file_path = BACKUP_FITFILE_LOCATION / new_filename
            logger.info(f"Cleaning up {new_file_path}")
            try:
                cleanup_fit_file(fit_file, new_file_path)  
                logger.info(f"Successfully cleaned {fit_file.name}" 
                            f"and saved the file as {new_file_path.name}.")
                return new_file_path
            except Exception as e:
                logger.error(f"Failed to process {fit_file.name}: {e}")
        else:
            logger.info("No .fit files found.")
            return Path()
    else:
        logger.info(f"The specified path is not a directory:" 
                    f"{fitfile_location}")
        return Path()


def upload_fit_file_to_garmin(new_file_path: Path):
    """
    Upload a .fit file to Garmin using the Garth client.

    Args:
        new_file_path (Path): The path to the .fit file to upload.

    Returns:
        None
    """
    try:
        if new_file_path and new_file_path.exists():
            with open(new_file_path, "rb") as f:
                uploaded = garth.client.upload(f)
                logger.debug(uploaded)
        else:
            logger.info(f"Invalid file path: {new_file_path}")
    except GarthHTTPError:
        logger.info("Duplicate activity found.")


def main():
    """
    Main function to ensure required packages are installed, 
    authenticate to Garmin, clean and save the FIT file, 
    and upload it to Garmin.

    Returns:
        None
    """
    ensure_packages()
    authenticate_to_garmin()
    new_file_path = cleanup_and_save_fit_file(FITFILE_LOCATION)
    if new_file_path:
        upload_fit_file_to_garmin(new_file_path)


if __name__ == "__main__":
    main()
