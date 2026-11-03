
import sys
import socket
import shutil
import subprocess
import zipfile
import hashlib
import os
import stat
import urllib.request
from pathlib import Path
from datetime import datetime

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout,
    QHBoxLayout, QLabel, QPushButton, QLineEdit,
    QFileDialog, QMessageBox, QFrame, QTabWidget,
    QGridLayout, QComboBox, QProgressBar
)
from PySide6.QtCore import Qt, QTimer, QSettings, QThread, Signal


# KORPAZEROTH CONFIGURATION
REALM_HOST = "korpazeroth.duckdns.org"
AUTH_PORT = 3724
EXPECTED_VERSION = "3.3.5.12340"
CLIENT_DOWNLOAD_URL = (
    "https://korpazeroth-downloads.duckdns.org/"
    "clients/KorpAzeroth-WoW-3.3.5a.zip"
)
CLIENT_SHA256 = "644a8e6b49aef8f32c7ae529614ab6c07c266c2af1ad5355140da55556ff8262"
CLIENT_ARCHIVE_NAME = "KorpAzeroth-WoW-3.3.5a.zip"

DEFAULT_GAME_PATH = str(
    Path.home() / "WoW/WoW_3.3.5a/WoW_3.3.5a"
)

def verify_archive(path, status=None, progress=None):
    """Verify the archive against the checksum of the server copy."""
    digest = hashlib.sha256()
    size = path.stat().st_size
    processed = 0
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(4 * 1024 * 1024), b""):
            digest.update(chunk)
            processed += len(chunk)
            if progress and size:
                progress(int(processed * 100 / size))
    if digest.hexdigest().lower() != CLIENT_SHA256:
        raise ValueError("Archive checksum mismatch. The download may be incomplete or damaged.")
    return True


class ClientDownloadWorker(QThread):
    progress = Signal(int)
    status = Signal(str)
    completed = Signal(str)
    failed = Signal(str)

    def __init__(self, url, destination):
        super().__init__()
        self.url = url
        self.destination = Path(destination)

    def run(self):
        partial = self.destination.with_name(self.destination.name + ".part")
        try:
            self.destination.parent.mkdir(parents=True, exist_ok=True)
            if self.destination.is_file():
                self.status.emit("Checking existing archive...")
                try:
                    verify_archive(self.destination, progress=self.progress.emit)
                except (ValueError, OSError):
                    self.status.emit("Existing archive is invalid; downloading a fresh copy...")
                else:
                    self.completed.emit(str(self.destination))
                    return

            self.status.emit("Connecting to download server...")
            # Restart interrupted downloads safely; never mistake .part for a valid ZIP.
            request = urllib.request.Request(
                self.url, headers={"User-Agent": "KorpAzeroth-Launcher"}
            )
            with urllib.request.urlopen(request, timeout=60) as response:
                if response.status != 200:
                    raise IOError(f"Unexpected HTTP status: {response.status}")
                total = int(response.headers.get("Content-Length", "0"))
                downloaded = 0
                with partial.open("wb") as output:
                    while True:
                        chunk = response.read(1024 * 1024)
                        if not chunk:
                            break
                        output.write(chunk)
                        downloaded += len(chunk)
                        if total:
                            self.progress.emit(min(100, int(downloaded * 100 / total)))
            if total and downloaded != total:
                raise IOError("Download ended before all bytes were received.")
            self.status.emit("Verifying SHA-256 checksum...")
            self.progress.emit(0)
            verify_archive(partial, progress=self.progress.emit)
            os.replace(partial, self.destination)
            self.completed.emit(str(self.destination))
        except Exception as error:
            self.failed.emit(str(error))


class ClientExtractionWorker(QThread):
    progress = Signal(int)
    status = Signal(str)
    completed = Signal(str)
    failed = Signal(str)

    def __init__(self, archive_path, install_dir):
        super().__init__()
        self.archive_path = Path(archive_path)
        self.install_dir = Path(install_dir)

    def run(self):
        import tempfile
        try:
            if self.install_dir.exists():
                raise FileExistsError(
                    f"Installation destination already exists: {self.install_dir}"
                )
            self.install_dir.parent.mkdir(parents=True, exist_ok=True)
            self.status.emit("Checking ZIP contents...")
            with zipfile.ZipFile(self.archive_path) as archive:
                files = archive.infolist()
                if not files:
                    raise ValueError("Game archive is empty.")
                # Restrict paths and reject symbolic links and special files.
                staging_root = Path("WoW_3.3.5a")
                for entry in files:
                    name = entry.filename.replace("\\", "/")
                    parts = name.split("/")
                    if (name.startswith("/") or
                            any(part in ("..", "") for part in parts[:-1]) or
                            (parts and ":" in parts[0]) or
                            any(part == ".." for part in parts) or
                            (entry.create_system == 3 and
                             stat.S_ISLNK(entry.external_attr >> 16))):
                        raise ValueError(f"Unsafe archive entry: {entry.filename}")
                    if not name.startswith("WoW_3.3.5a/"):
                        raise ValueError("Unexpected folder layout in game archive.")
                self.status.emit("Extracting game files...")
                with tempfile.TemporaryDirectory(
                    prefix=".korpazeroth-install-", dir=self.install_dir.parent
                ) as temporary:
                    staging = Path(temporary)
                    root = staging.resolve()
                    total_bytes = sum(e.file_size for e in files if not e.is_dir())
                    processed = 0
                    for entry in files:
                        target = (staging / entry.filename).resolve()
                        if not target.is_relative_to(root):
                            raise ValueError("Unsafe extraction path.")
                        if entry.is_dir():
                            target.mkdir(parents=True, exist_ok=True)
                            continue
                        target.parent.mkdir(parents=True, exist_ok=True)
                        with archive.open(entry) as source, target.open("wb") as output:
                            while True:
                                chunk = source.read(1024 * 1024)
                                if not chunk:
                                    break
                                output.write(chunk)
                                processed += len(chunk)
                                if total_bytes:
                                    self.progress.emit(min(100, int(processed * 100 / total_bytes)))
                    extracted = staging / "WoW_3.3.5a"
                    if not (extracted / "Wow.exe").is_file():
                        raise ValueError("Wow.exe not found in extracted client.")
                    for name in ("common.MPQ", "expansion.MPQ", "lichking.MPQ"):
                        if not (extracted / "Data" / name).is_file():
                            raise ValueError(f"Required game file missing: {name}")

                    locale_dir = extracted / "Data" / "enUS"

                    for name in (
                        "locale-enUS.MPQ",
                        "base-enUS.MPQ",
                        "expansion-locale-enUS.MPQ",
                        "lichking-locale-enUS.MPQ",
                    ):
                        file = locale_dir / name
                        if not file.is_file() or file.stat().st_size == 0:
                            raise ValueError(f"Required language file missing: Data/enUS/{name}")
                    if self.install_dir.exists():
                        raise FileExistsError("Installation folder already exists.")
                    extracted.rename(self.install_dir)
            self.completed.emit(str(self.install_dir))
        except Exception as error:
            self.failed.emit(str(error))


class KorpAzerothLauncher(QMainWindow):

    def __init__(self):
        super().__init__()

        self.settings = QSettings(
            "KorpAzeroth", "Launcher"
        )

        self.setWindowTitle("KorpAzeroth")
        self.resize(1100, 780)
        self.setMinimumSize(850, 650)

        self.create_interface()

        self.path_input.setText(
            self.settings.value("game_path", DEFAULT_GAME_PATH)
        )

        self.launch_method.setCurrentText(
            self.settings.value("launch_method", "Lutris")
        )

        self.lutris_id.setText(
            self.settings.value("lutris_id", "")
        )

        self.wine_command.setText(
            self.settings.value("wine_command", "wine")
        )

        self.check_game()
        self.check_server()

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.check_server)
        self.timer.start(30000)

    def panel(self):
        frame = QFrame()
        frame.setObjectName("panel")
        return frame

    def create_interface(self):

        central = QWidget()
        self.setCentralWidget(central)

        root = QVBoxLayout(central)
        root.setContentsMargins(28, 22, 28, 22)
        root.setSpacing(16)

        header = QHBoxLayout()
        branding = QVBoxLayout()

        title = QLabel("KORPAZEROTH")
        title.setObjectName("title")
        branding.addWidget(title)

        subtitle = QLabel(
            "WRATH OF THE LICH KING  •  3.3.5a"
        )
        subtitle.setObjectName("subtitle")
        branding.addWidget(subtitle)

        header.addLayout(branding)
        header.addStretch()

        self.header_status = QLabel("CHECKING REALM")
        self.header_status.setObjectName("headerStatus")
        header.addWidget(self.header_status)

        root.addLayout(header)

        separator = QFrame()
        separator.setObjectName("separator")
        separator.setFixedHeight(2)
        root.addWidget(separator)

        self.tabs = QTabWidget()

        self.create_play_tab()
        self.create_installation_tab()
        self.create_settings_tab()
        self.create_about_tab()

        root.addWidget(self.tabs)

        footer = QLabel(
            "KORPAZEROTH  •  YOUR ADVENTURE BEGINS IN NORTHREND"
        )
        footer.setObjectName("footer")
        footer.setAlignment(Qt.AlignCenter)
        root.addWidget(footer)

        self.apply_style()

    def create_play_tab(self):

        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(12, 20, 12, 12)
        layout.setSpacing(16)

        hero = self.panel()
        hero_layout = QVBoxLayout(hero)
        hero_layout.setContentsMargins(25, 24, 25, 24)

        hero_title = QLabel("THE FROZEN NORTH AWAITS")
        hero_title.setObjectName("heroTitle")
        hero_title.setAlignment(Qt.AlignCenter)
        hero_layout.addWidget(hero_title)

        hero_text = QLabel(
            "Enter Northrend. Forge your legend. "
            "Defend Azeroth."
        )
        hero_text.setObjectName("heroText")
        hero_text.setAlignment(Qt.AlignCenter)
        hero_layout.addWidget(hero_text)

        layout.addWidget(hero)

        realm = self.panel()
        realm_layout = QVBoxLayout(realm)
        realm_layout.setContentsMargins(20, 16, 20, 16)

        realm_title = QLabel("REALM INFORMATION")
        realm_title.setObjectName("sectionTitle")
        realm_layout.addWidget(realm_title)

        realm_grid = QGridLayout()

        details = [
            ("Realm name", "KorpAzeroth"),
            ("Expansion", "Wrath of the Lich King"),
            ("Version", "3.3.5a"),
            ("Address", REALM_HOST)
        ]

        for row, (label, value) in enumerate(details):
            realm_grid.addWidget(QLabel(label), row, 0)
            realm_grid.addWidget(QLabel(value), row, 1)

        realm_layout.addLayout(realm_grid)
        layout.addWidget(realm)

        announcement = self.panel()
        announcement_layout = QVBoxLayout(announcement)
        announcement_layout.setContentsMargins(20, 14, 20, 14)

        announcement_title = QLabel("REALM ANNOUNCEMENTS")
        announcement_title.setObjectName("sectionTitle")
        announcement_layout.addWidget(announcement_title)

        announcement_text = QLabel(
            "Welcome to KorpAzeroth!\n\n"
            "Your journey through Northrend begins here. "
            "Prepare your character and join the adventure."
        )
        announcement_text.setWordWrap(True)
        announcement_text.setObjectName("announcement")
        announcement_layout.addWidget(announcement_text)

        layout.addWidget(announcement)
        layout.addStretch()

        self.play_button = QPushButton("PLAY")
        self.play_button.setObjectName("playButton")
        self.play_button.setMinimumHeight(68)
        self.play_button.setEnabled(False)
        self.play_button.clicked.connect(self.launch_game)

        layout.addWidget(self.play_button)

        self.game_status = QLabel("Checking installation...")
        self.game_status.setObjectName("gameStatus")
        self.game_status.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.game_status)

        self.tabs.addTab(page, "PLAY")

    def create_installation_tab(self):

        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(20, 25, 20, 20)
        layout.setSpacing(18)

        title = QLabel("GAME INSTALLATION")
        title.setObjectName("sectionTitle")
        layout.addWidget(title)

        layout.addWidget(QLabel(
            "Select your World of Warcraft 3.3.5a folder."
        ))

        self.path_input = QLineEdit()
        self.path_input.setPlaceholderText(
            "Select your WoW installation folder..."
        )
        self.path_input.textChanged.connect(self.check_game)
        layout.addWidget(self.path_input)

        browse = QPushButton("BROWSE FOR GAME")
        browse.clicked.connect(self.browse_game)
        layout.addWidget(browse)
        self.download_button = QPushButton(
            "DOWNLOAD & INSTALL WOW 3.3.5a"
        )
        self.download_button.setEnabled(True)
        self.download_button.setToolTip(
            "Download, verify, and install the WoW 3.3.5a client."
        )
        self.download_button.clicked.connect(
            self.start_client_download
        )
        layout.addWidget(self.download_button)
        self.download_progress = QProgressBar()
        self.download_progress.setRange(0, 100)
        self.download_progress.setValue(0)
        self.download_progress.setVisible(False)
        layout.addWidget(self.download_progress)

        self.download_status = QLabel("")
        self.download_status.setWordWrap(True)
        layout.addWidget(self.download_status)    

        self.install_status = QLabel(
            "No installation selected."
        )
        self.install_status.setWordWrap(True)
        layout.addWidget(self.install_status)

        
        info = QLabel(
            "NEW PLAYER? GET STARTED\n\n"
            "1. Obtain a compatible World of Warcraft "
            "3.3.5a (build 12340) client.\n\n"
            "2. Extract or install the game into a folder "
            "on your computer.\n\n"
            "3. Click BROWSE FOR GAME above and select "
            "the folder containing Wow.exe.\n\n"
            "4. The launcher will verify your game version "
            "and required data files.\n\n"
            "5. Once verified, open the PLAY tab and "
            "click PLAY. The launcher will automatically "
            "configure the KorpAzeroth realmlist.\n\n"
            "6. Log in using your KorpAzeroth game account."
        )

        info.setWordWrap(True)
        info.setObjectName("announcement")
        layout.addWidget(info)

        layout.addStretch()

        self.tabs.addTab(page, "INSTALLATION")
    def start_client_download(self):
        install_dir = Path.home() / "Games" / "KorpAzeroth"
        if install_dir.exists():
            QMessageBox.warning(
                self, "Installation Exists",
                f"The destination already exists:\n{install_dir}\n\n"
                "Select an existing game using Browse, or move the folder first."
            )
            return
        destination = Path.home() / "Downloads" / CLIENT_ARCHIVE_NAME
        self.download_button.setEnabled(False)
        self.download_progress.setValue(0)
        self.download_progress.setVisible(True)
        self.download_status.setText("Starting download...")
        self.download_worker = ClientDownloadWorker(CLIENT_DOWNLOAD_URL, destination)
        self.download_worker.progress.connect(self.download_progress.setValue)
        self.download_worker.status.connect(self.download_status.setText)
        self.download_worker.completed.connect(self.client_download_completed)
        self.download_worker.failed.connect(self.client_download_failed)
        self.download_worker.start()

    def client_download_completed(self, archive_path):
        self.download_progress.setValue(0)
        self.download_status.setText("Archive verified. Preparing installation...")
        install_dir = Path.home() / "Games" / "KorpAzeroth"
        self.extraction_worker = ClientExtractionWorker(archive_path, install_dir)
        self.extraction_worker.progress.connect(self.download_progress.setValue)
        self.extraction_worker.status.connect(self.download_status.setText)
        self.extraction_worker.completed.connect(self.client_installation_completed)
        self.extraction_worker.failed.connect(self.client_download_failed)
        self.extraction_worker.start()

    def client_installation_completed(self, install_path):
        self.download_progress.setValue(100)
        self.download_status.setText("Installation complete!")
        self.path_input.setText(install_path)
        self.check_game()
        self.download_button.setEnabled(True)
        QMessageBox.information(
            self, "Installation Complete",
            f"World of Warcraft 3.3.5a installed to:\n{install_path}\n\n"
            "The launcher has selected this installation."
        )

    def client_download_failed(self, error):
        self.download_status.setText(f"Download or installation failed: {error}")
        self.download_button.setEnabled(True)
        QMessageBox.warning(
            self, "Installation Failed", f"Could not install the WoW client:\n\n{error}"
        )

    def create_settings_tab(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(20, 25, 20, 20)
        layout.setSpacing(16)

        title = QLabel("LAUNCHER SETTINGS")
        title.setObjectName("sectionTitle")
        layout.addWidget(title)

        layout.addWidget(QLabel("Linux launch method"))

        self.launch_method = QComboBox()
        self.launch_method.addItems(["Lutris", "Wine"])
        self.launch_method.currentTextChanged.connect(
            self.save_settings
        )
        layout.addWidget(self.launch_method)

        layout.addWidget(QLabel("Lutris game ID"))

        self.lutris_id = QLineEdit()
        self.lutris_id.setPlaceholderText(
            "Enter your Lutris game ID"
        )
        self.lutris_id.textChanged.connect(
            self.save_settings
        )
        layout.addWidget(self.lutris_id)

        layout.addWidget(QLabel("Wine executable"))

        self.wine_command = QLineEdit()
        self.wine_command.setPlaceholderText("wine")
        self.wine_command.textChanged.connect(
            self.save_settings
        )
        layout.addWidget(self.wine_command)

        layout.addWidget(QLabel(
            "Windows users launch the selected game directly."
        ))

        layout.addWidget(QLabel(
            "Linux users can choose Lutris or Wine."
        ))

        layout.addStretch()

        self.tabs.addTab(page, "SETTINGS")

    def create_about_tab(self):

        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(20, 25, 20, 20)

        title = QLabel("ABOUT KORPAZEROTH")
        title.setObjectName("sectionTitle")
        layout.addWidget(title)

        about = QLabel(
            "KorpAzeroth Launcher\n\n"
            "Version 0.5 Development\n\n"
            "A custom launcher for the KorpAzeroth "
            "Wrath of the Lich King realm.\n\n"
            "Client: World of Warcraft 3.3.5a\n"
            "Expected build: 12340"
        )
        about.setWordWrap(True)
        layout.addWidget(about)
        layout.addStretch()

        self.tabs.addTab(page, "ABOUT")

    def apply_style(self):

        self.setStyleSheet("""
            QMainWindow, QWidget {
                background-color: #101a29;
                color: #d9e5ef;
                font-family: Georgia;
                font-size: 14px;
            }

            QLabel#title {
                color: #e8c16a;
                font-size: 37px;
                font-weight: bold;
                letter-spacing: 3px;
            }

            QLabel#subtitle {
                color: #91b9dc;
                font-size: 12px;
                letter-spacing: 2px;
            }

            QLabel#headerStatus {
                color: #79dba1;
                font-size: 12px;
                font-weight: bold;
            }

            QFrame#separator {
                background-color: #a88748;
            }

            QFrame#panel {
                background-color: #19283a;
                border: 1px solid #705b36;
                border-radius: 7px;
            }

            QLabel#heroTitle {
                color: #e8c16a;
                font-size: 27px;
                font-weight: bold;
            }

            QLabel#heroText {
                color: #a9c8e5;
                font-size: 15px;
            }

            QLabel#sectionTitle {
                color: #e8c16a;
                font-size: 17px;
                font-weight: bold;
            }

            QLabel#announcement {
                color: #c0d0df;
                font-size: 14px;
            }

            QLabel#gameStatus {
                color: #9db3c8;
                font-size: 12px;
            }

            QLabel#footer {
                color: #8297aa;
                font-size: 10px;
                letter-spacing: 2px;
            }

            QTabWidget::pane {
                border: 1px solid #705b36;
                background-color: #142235;
                border-radius: 5px;
            }

            QTabBar::tab {
                background-color: #19283a;
                color: #b9c9d8;
                border: 1px solid #705b36;
                padding: 12px 22px;
                margin-right: 4px;
            }

            QTabBar::tab:selected {
                background-color: #315577;
                color: #f1d18a;
                border-bottom: 2px solid #e8c16a;
            }

            QLineEdit, QComboBox {
                background-color: #19283a;
                border: 1px solid #8b713e;
                border-radius: 5px;
                padding: 10px;
                color: white;
            }

            QPushButton {
                background-color: #243c59;
                color: #e8c16a;
                border: 1px solid #a88748;
                border-radius: 5px;
                padding: 11px 18px;
                font-weight: bold;
            }

            QPushButton:hover {
                background-color: #345579;
            }

            QPushButton#playButton {
                background-color: #174c7a;
                color: #f4d58c;
                border: 2px solid #c19b50;
                border-radius: 7px;
                font-size: 28px;
                font-weight: bold;
            }

            QPushButton#playButton:hover {
                background-color: #246ba5;
            }

            QPushButton#playButton:disabled {
                background-color: #26313d;
                color: #777777;
                border-color: #555555;
            }
        """)

    def save_settings(self, *_):

        self.settings.setValue(
            "launch_method", self.launch_method.currentText()
        )
        self.settings.setValue(
            "lutris_id", self.lutris_id.text()
        )
        self.settings.setValue(
            "wine_command", self.wine_command.text()
        )

    def browse_game(self):

        folder = QFileDialog.getExistingDirectory(
            self,
            "Select World of Warcraft 3.3.5a Folder",
            self.path_input.text()
        )

        if folder:
            self.path_input.setText(folder)

    def get_game_executable(self):

        folder = Path(
            self.path_input.text()
        ).expanduser()

        executable = folder / "Wow.exe"

        if executable.is_file():
            return executable

        return None

    def get_realmlist(self, executable):

        data = executable.parent / "Data"

        candidates = sorted(
            data.glob("*/realmlist.wtf")
        )

        for candidate in candidates:
            if candidate.parent.name.lower() == "enus":
                return candidate

        if candidates:
            return candidates[0]

        return None

    def get_version(self, executable):

        try:
            if sys.platform == "win32":
                command = [
                    "powershell",
                    "-NoProfile",
                    "-Command",
                    (
                        f"(Get-Item -LiteralPath "
                        f"'{str(executable)}').VersionInfo.FileVersion"
                    )
                ]
            else:
                command = [
                    "exiftool",
                    "-s3",
                    "-FileVersionNumber",
                    str(executable)
                ]

            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=10
            )

            if result.returncode != 0:
                return None

            return result.stdout.strip()

        except (OSError, subprocess.TimeoutExpired):
            return None

    def validate_game(self, executable):

        data = executable.parent / "Data"

        required = [
            "common.MPQ",
            "expansion.MPQ",
            "lichking.MPQ"
        ]

        missing = [
            name for name in required
            if not (data / name).is_file()
        ]

        if missing:
            return False, "Missing game data: " + ", ".join(missing)

        locale_dir = data / "enUS"
        required_locale = (
            "locale-enUS.MPQ",
            "base-enUS.MPQ",
            "expansion-locale-enUS.MPQ",
            "lichking-locale-enUS.MPQ",
        )
        for name in required_locale:
            file = locale_dir / name
            if not file.is_file() or file.stat().st_size == 0:
                return False, f"Missing language file: Data/enUS/{name}"

        version = self.get_version(executable)

        if not version:
            return False, (
                "Could not read executable version. "
                "Ensure ExifTool is installed on Linux."
            )

        if EXPECTED_VERSION not in version:
            return False, (
                f"Incompatible client version: {version}. "
                f"Expected {EXPECTED_VERSION}."
            )

        return True, f"Verified WoW client {version}"

    def check_game(self, *_):

        executable = self.get_game_executable()

        if not executable:
            message = "Select a valid WoW installation folder."
            valid = False

        else:
            valid, message = self.validate_game(executable)

        self.play_button.setEnabled(valid)

        colour = "#79dba1" if valid else "#e8a65b"

        self.game_status.setText(message)
        self.install_status.setText(message)

        self.game_status.setStyleSheet(
            f"color: {colour};"
        )
        self.install_status.setStyleSheet(
            f"color: {colour};"
        )

        self.settings.setValue(
            "game_path", self.path_input.text()
        )

    def check_server(self):

        try:
            with socket.create_connection(
                (REALM_HOST, AUTH_PORT), timeout=3
            ):
                self.header_status.setText("● AUTH SERVER ONLINE")
                self.header_status.setStyleSheet(
                    "color: #79dba1;"
                )

        except OSError:
            self.header_status.setText("● AUTH SERVER OFFLINE")
            self.header_status.setStyleSheet(
                "color: #e87979;"
            )

    def configure_realmlist(self, executable):

        data = executable.parent / "Data"

        realmlist = self.get_realmlist(executable)

        if realmlist is None:
            locale = data / "enUS"
            locale.mkdir(parents=True, exist_ok=True)
            realmlist = locale / "realmlist.wtf"

        new_content = f"set realmlist {REALM_HOST}\n"

        if realmlist.exists():
            current = realmlist.read_text(
                encoding="utf-8", errors="replace"
            )

            if current.strip() == new_content.strip():
                return

            timestamp = datetime.now().strftime(
                "%Y%m%d-%H%M%S"
            )

            backup = realmlist.with_name(
                f"realmlist.wtf.bak.{timestamp}"
            )

            shutil.copy2(realmlist, backup)

        realmlist.write_text(
            new_content, encoding="utf-8"
        )

    def launch_game(self):

        executable = self.get_game_executable()

        if not executable:
            QMessageBox.warning(
                self, "Game Not Found",
                "Select a valid WoW installation."
            )
            return

        valid, message = self.validate_game(executable)

        if not valid:
            QMessageBox.warning(
                self, "Client Validation Failed", message
            )
            return

        try:
            self.configure_realmlist(executable)

            if sys.platform == "win32":

                subprocess.Popen(
                    [str(executable)],
                    cwd=str(executable.parent)
                )

            elif sys.platform.startswith("linux"):

                method = self.launch_method.currentText()

                if method == "Lutris":

                    game_id = self.lutris_id.text().strip()

                    if not game_id.isdigit():
                        QMessageBox.warning(
                            self,
                            "Lutris Configuration",
                            "Enter your Lutris game ID in Settings."
                        )
                        return

                    subprocess.Popen([
                        "lutris",
                        f"lutris:rungameid/{game_id}"
                    ])

                else:

                    wine = self.wine_command.text().strip()

                    if not wine:
                        wine = "wine"

                    subprocess.Popen(
                        [wine, str(executable)],
                        cwd=str(executable.parent)
                    )

            else:
                raise RuntimeError("Unsupported operating system.")

        except Exception as error:

            QMessageBox.critical(
                self, "Launch Error",
                f"Could not launch KorpAzeroth:\n\n{error}"
            )


if __name__ == "__main__":

    app = QApplication(sys.argv)
    app.setApplicationName("KorpAzeroth Launcher")

    window = KorpAzerothLauncher()
    window.show()

    sys.exit(app.exec())
