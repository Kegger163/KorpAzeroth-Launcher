
import sys
import socket
import shutil
import subprocess
from pathlib import Path
from datetime import datetime

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout,
    QHBoxLayout, QLabel, QPushButton, QLineEdit,
    QFileDialog, QMessageBox, QFrame, QTabWidget,
    QGridLayout, QComboBox
)
from PySide6.QtCore import Qt, QTimer, QSettings


# KORPAZEROTH CONFIGURATION
REALM_HOST = "korpazeroth.duckdns.org"
AUTH_PORT = 3724
EXPECTED_VERSION = "3.3.5.12340"

DEFAULT_GAME_PATH = str(
    Path.home() / "WoW/WoW_3.3.5a/WoW_3.3.5a"
)


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

        self.install_status = QLabel(
            "No installation selected."
        )
        self.install_status.setWordWrap(True)
        layout.addWidget(self.install_status)

        info = QLabel(
            "NEW PLAYER?\n\n"
            "Guided installation of compatible WoW 3.3.5a "
            "client files is planned for a future version.\n\n"
            "Players must obtain their game files through "
            "legitimate means."
        )
        info.setWordWrap(True)
        info.setObjectName("announcement")
        layout.addWidget(info)

        layout.addStretch()

        self.tabs.addTab(page, "INSTALLATION")

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
            "Version 0.3 Development\n\n"
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
