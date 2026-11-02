"""Tema oscuro de la aplicación (hoja de estilos Qt, parecida a CSS).

Los colores se definen una sola vez aquí. El significado nunca depende solo
del color: victorias, derrotas, equipos y avisos llevan siempre texto.
"""

BG = "#0b0e13"
SURFACE = "#12161d"
SURFACE_2 = "#19202a"
SURFACE_3 = "#212a36"
BORDER = "#232b37"
TEXT = "#e9edf2"
MUTED = "#8a94a3"
ACCENT = "#1ed3b0"
ACCENT_HOVER = "#17b596"
ACCENT_SOFT = "rgba(30, 211, 176, 0.12)"
ALLY = "#4c8dff"
ENEMY = "#ff5468"
WARNING = "#f5b941"
GOLD = "#f5b941"
WIN = "#4c8dff"
WIN_BG = "#13213a"
LOSS = "#ff5468"
LOSS_BG = "#2a1620"
ACE = "#b48cff"

TIER_COLORS = {
    "IRON": "#6b6b6b", "BRONZE": "#a5694f", "SILVER": "#9fb1bd", "GOLD": "#e6b54a",
    "PLATINUM": "#3fb6a8", "EMERALD": "#2ecc71", "DIAMOND": "#5aa9ff", "MASTER": "#b06bff",
    "GRANDMASTER": "#ff5468", "CHALLENGER": "#f5d76e",
}

ICON_FONT = "Segoe Fluent Icons"
FALLBACK_ICON_FONT = "Segoe MDL2 Assets"

STYLESHEET = f"""
QWidget {{ font-family: "Segoe UI Variable Text", "Segoe UI"; font-size: 10pt; color: {TEXT}; background: transparent; }}
QMainWindow, QDialog {{ background: {BG}; }}
QStackedWidget, QScrollArea, QScrollArea > QWidget > QWidget {{ background: {BG}; border: none; }}
QToolTip {{ background: {SURFACE_3}; color: {TEXT}; border: 1px solid {BORDER}; padding: 6px; border-radius: 6px; }}

/* Barra lateral */
QFrame#sidebar {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #10141b, stop:1 #0c0f14);
    border-right: 1px solid {BORDER};
}}
QLabel#brand {{ font-size: 16pt; font-weight: 800; letter-spacing: 0.5px; }}
QLabel#brandSub {{ color: {MUTED}; font-size: 8.5pt; }}
QListWidget#nav {{ background: transparent; border: none; outline: none; font-size: 10.5pt; }}
QListWidget#nav::item {{ padding: 9px 12px; margin: 2px 10px; border-radius: 8px; color: {MUTED}; }}
QListWidget#nav::item:selected {{ background: {ACCENT_SOFT}; color: {TEXT}; }}
QListWidget#nav::item:hover:!selected {{ background: {SURFACE_2}; color: {TEXT}; }}

/* Textos */
QLabel#title {{ font-family: "Segoe UI Variable Display", "Segoe UI"; font-size: 21pt; font-weight: 700; }}
QLabel#subtitle {{ color: {MUTED}; }}
QLabel#sectionTitle {{ font-size: 11.5pt; font-weight: 700; padding-top: 4px; }}
QLabel#heroTitle {{ font-family: "Segoe UI Variable Display", "Segoe UI"; font-size: 24pt; font-weight: 800; }}
QLabel#heroSub {{ color: #c9d1db; font-size: 10.5pt; }}
QLabel#statValue {{ font-family: "Segoe UI Variable Display", "Segoe UI"; font-size: 19pt; font-weight: 700; }}
QLabel#statCaption {{ color: {MUTED}; font-size: 8.5pt; letter-spacing: 0.5px; }}
QLabel#notice {{
    background: #2a2412; border: 1px solid #5c4a17; border-radius: 8px; padding: 9px 12px; color: #f3dfa6;
}}
QLabel#teamAlly {{ color: {ALLY}; font-weight: 800; letter-spacing: 1.5px; font-size: 9pt; }}
QLabel#teamEnemy {{ color: {ENEMY}; font-weight: 800; letter-spacing: 1.5px; font-size: 9pt; }}
QLabel#badge {{
    background: {ACCENT}; color: #04110e; border-radius: 5px; padding: 1px 7px; font-weight: 800; font-size: 8pt;
}}
QLabel#confidence {{
    border: 1px solid {BORDER}; border-radius: 6px; padding: 2px 8px; color: {MUTED}; font-size: 8.5pt;
}}

/* Tarjetas y paneles */
QFrame#card, QGroupBox {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #151a22, stop:1 #11151b);
    border: 1px solid {BORDER}; border-radius: 12px;
}}
QFrame#card:hover {{ border-color: #2c3644; }}
QFrame#tile {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #161c25, stop:1 #12161d);
    border: 1px solid {BORDER}; border-radius: 12px;
}}
QGroupBox {{ margin-top: 18px; padding: 14px 12px 12px 12px; font-weight: 700; }}
QGroupBox::title {{ subcontrol-origin: margin; left: 14px; padding: 0 4px; color: {MUTED}; }}
QGroupBox QLabel, QGroupBox QCheckBox {{ font-weight: normal; }}

/* Casillas del draft */
QFrame#slot {{ background: {SURFACE}; border: 1px solid {BORDER}; border-radius: 10px; }}
QFrame#slot:hover {{ border-color: #33404f; background: {SURFACE_2}; }}
QFrame#slot:focus {{ border-color: {ACCENT}; }}
QFrame#slot[me="true"] {{ background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #10302a, stop:1 {SURFACE}); }}
QFrame#slot[active="true"] {{ border: 2px solid {ACCENT}; }}

/* Controles */
QPushButton {{
    background: {SURFACE_2}; border: 1px solid {BORDER}; border-radius: 8px; padding: 7px 15px; font-weight: 600;
}}
QPushButton:hover {{ border-color: {ACCENT}; background: {SURFACE_3}; }}
QPushButton:focus {{ border: 1px solid {ACCENT}; }}
QPushButton:disabled {{ color: #555c66; }}
QPushButton#primary {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #21dcb8, stop:1 #14b69a);
    color: #04110e; border: none; font-weight: 800;
}}
QPushButton#primary:hover {{ background: {ACCENT_HOVER}; }}
QPushButton#primary:disabled {{ background: {SURFACE_2}; color: #555c66; border: 1px solid {BORDER}; }}
QPushButton#link {{ background: transparent; border: none; color: {ACCENT}; padding: 2px 0; text-align: left; }}
QPushButton#chip {{ border-radius: 14px; padding: 4px 12px; font-weight: 600; }}
QPushButton#chip:checked {{ background: {ACCENT_SOFT}; border-color: {ACCENT}; color: {TEXT}; }}

QLineEdit, QComboBox, QPlainTextEdit, QTextBrowser, QListWidget, QTableWidget, QSpinBox {{
    background: {SURFACE}; border: 1px solid {BORDER}; border-radius: 8px; padding: 5px 8px;
    selection-background-color: {ACCENT}; selection-color: #04110e;
}}
QLineEdit:focus, QComboBox:focus, QPlainTextEdit:focus, QSpinBox:focus {{ border-color: {ACCENT}; }}
QLineEdit:disabled, QComboBox:disabled, QSpinBox:disabled {{ color: #555c66; background: {BG}; }}
QComboBox::drop-down {{ border: none; width: 22px; }}
QComboBox QAbstractItemView {{ background: {SURFACE_2}; border: 1px solid {BORDER}; border-radius: 8px; padding: 4px; }}
QListWidget#grid {{ background: {SURFACE}; padding: 8px; border-radius: 12px; }}
QListWidget#grid::item {{ border-radius: 8px; padding: 4px; color: {TEXT}; }}
QListWidget#grid::item:hover {{ background: {SURFACE_2}; }}
QListWidget#grid::item:selected {{ background: {ACCENT_SOFT}; color: {TEXT}; }}
QListWidget#grid::item:disabled {{ color: #4b525c; }}
QHeaderView::section {{
    background: {SURFACE_2}; color: {MUTED}; border: none; padding: 7px 8px; font-weight: 700; font-size: 8.5pt;
}}
QTableWidget {{ gridline-color: transparent; alternate-background-color: #141920; border-radius: 12px; }}
/* Sin regla general para ::item: anularía el color de fondo por fila (victoria/derrota). */
QTabWidget::pane {{ border: none; top: -1px; }}
QTabBar::tab {{
    background: transparent; color: {MUTED}; padding: 8px 16px; border: none; border-bottom: 2px solid transparent;
    font-weight: 600;
}}
QTabBar::tab:selected {{ color: {TEXT}; border-bottom: 2px solid {ACCENT}; }}
QTabBar::tab:hover:!selected {{ color: {TEXT}; }}
QCheckBox::indicator {{ width: 16px; height: 16px; }}

QProgressBar {{
    background: {SURFACE_2}; border: none; border-radius: 5px; text-align: center;
    color: {TEXT}; font-size: 8.5pt; font-weight: 700; max-height: 16px;
}}
QProgressBar::chunk {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #14b69a, stop:1 #2ee6c4); border-radius: 5px;
}}

QScrollBar:vertical {{ background: transparent; width: 9px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: #2a3340; border-radius: 4px; min-height: 30px; }}
QScrollBar::handle:vertical:hover {{ background: #3a4554; }}
QScrollBar:horizontal {{ background: transparent; height: 9px; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: #2a3340; border-radius: 4px; min-width: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}
QSplitter::handle {{ background: {BG}; }}
QStatusBar {{ background: #0e1218; color: {MUTED}; border-top: 1px solid {BORDER}; }}
"""
