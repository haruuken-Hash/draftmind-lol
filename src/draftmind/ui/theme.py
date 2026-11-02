"""Tema oscuro de la aplicación (hoja de estilos Qt, parecida a CSS).

Los colores se definen una sola vez aquí. El significado nunca depende solo
del color: los equipos, valoraciones y avisos llevan siempre texto.
"""

BG = "#0d0f12"
SURFACE = "#15181d"
SURFACE_2 = "#1c2027"
BORDER = "#272c35"
TEXT = "#e8eaed"
MUTED = "#8b929c"
ACCENT = "#17c3a5"
ACCENT_HOVER = "#12a68c"
ALLY = "#4c8dff"
ENEMY = "#ff5c6c"
WARNING = "#f0b429"

STYLESHEET = f"""
QWidget {{ font-family: "Segoe UI"; font-size: 10pt; color: {TEXT}; background: transparent; }}
QMainWindow, QDialog {{ background: {BG}; }}
QStackedWidget, QScrollArea, QScrollArea > QWidget > QWidget {{ background: {BG}; border: none; }}
QToolTip {{ background: {SURFACE_2}; color: {TEXT}; border: 1px solid {BORDER}; padding: 4px; }}

/* Barra lateral */
QFrame#sidebar {{ background: {SURFACE}; border-right: 1px solid {BORDER}; }}
QLabel#brand {{ font-size: 15pt; font-weight: 700; padding: 18px 18px 4px 18px; }}
QLabel#brandSub {{ color: {MUTED}; padding: 0 18px 12px 18px; font-size: 9pt; }}
QListWidget#nav {{ background: transparent; border: none; outline: none; font-size: 10.5pt; }}
QListWidget#nav::item {{ padding: 10px 18px; border-left: 3px solid transparent; color: {MUTED}; }}
QListWidget#nav::item:selected {{ background: {SURFACE_2}; color: {TEXT}; border-left: 3px solid {ACCENT}; }}
QListWidget#nav::item:hover:!selected {{ color: {TEXT}; }}

/* Textos */
QLabel#title {{ font-size: 18pt; font-weight: 700; }}
QLabel#subtitle, QLabel.muted {{ color: {MUTED}; }}
QLabel#sectionTitle {{ font-size: 11pt; font-weight: 600; }}
QLabel#notice {{
    background: #2a2412; border: 1px solid #5c4a17; border-radius: 6px; padding: 8px 10px; color: #f3dfa6;
}}
QLabel#teamAlly {{ color: {ALLY}; font-weight: 700; letter-spacing: 1px; }}
QLabel#teamEnemy {{ color: {ENEMY}; font-weight: 700; letter-spacing: 1px; }}
QLabel#badge {{
    background: {ACCENT}; color: #04110e; border-radius: 4px; padding: 1px 6px; font-weight: 700; font-size: 8pt;
}}
QLabel#confidence {{
    border: 1px solid {BORDER}; border-radius: 4px; padding: 1px 6px; color: {MUTED}; font-size: 8.5pt;
}}

/* Tarjetas y paneles */
QFrame#card, QGroupBox {{
    background: {SURFACE}; border: 1px solid {BORDER}; border-radius: 8px;
}}
QGroupBox {{ margin-top: 16px; padding: 12px 10px 10px 10px; font-weight: 600; }}
QGroupBox::title {{ subcontrol-origin: margin; left: 12px; padding: 0 4px; color: {MUTED}; }}
QGroupBox QLabel, QGroupBox QCheckBox {{ font-weight: normal; }}

/* Casillas del draft */
QFrame#slot {{ background: {SURFACE}; border: 1px solid {BORDER}; border-radius: 8px; }}
QFrame#slot:hover {{ border-color: #3a414d; }}
QFrame#slot:focus {{ border-color: {ACCENT}; }}
QFrame#slot[me="true"] {{ background: #12201d; }}
QFrame#slot[active="true"] {{ border: 2px solid {ACCENT}; }}

/* Controles */
QPushButton {{
    background: {SURFACE_2}; border: 1px solid {BORDER}; border-radius: 6px; padding: 6px 14px;
}}
QPushButton:hover {{ border-color: {ACCENT}; }}
QPushButton:focus {{ border: 1px solid {ACCENT}; }}
QPushButton:disabled {{ color: #555c66; }}
QPushButton#primary {{ background: {ACCENT}; color: #04110e; border: none; font-weight: 700; }}
QPushButton#primary:hover {{ background: {ACCENT_HOVER}; }}
QPushButton#primary:disabled {{ background: {SURFACE_2}; color: #555c66; border: 1px solid {BORDER}; }}
QLineEdit:disabled, QComboBox:disabled, QSpinBox:disabled {{ color: #555c66; background: {SURFACE}; }}
QPushButton#link {{ background: transparent; border: none; color: {ACCENT}; padding: 2px 0; text-align: left; }}

QLineEdit, QComboBox, QPlainTextEdit, QTextBrowser, QListWidget, QTableWidget {{
    background: {SURFACE_2}; border: 1px solid {BORDER}; border-radius: 6px; padding: 4px 6px;
    selection-background-color: {ACCENT}; selection-color: #04110e;
}}
QLineEdit:focus, QComboBox:focus, QPlainTextEdit:focus {{ border-color: {ACCENT}; }}
QComboBox QAbstractItemView {{ background: {SURFACE_2}; border: 1px solid {BORDER}; }}
QListWidget#grid {{ background: {SURFACE}; padding: 6px; }}
QListWidget#grid::item {{ border-radius: 6px; padding: 4px; color: {TEXT}; }}
QListWidget#grid::item:hover {{ background: {SURFACE_2}; }}
QListWidget#grid::item:selected {{ background: #163a34; color: {TEXT}; }}
QListWidget#grid::item:disabled {{ color: #4b525c; }}
QHeaderView::section {{ background: {SURFACE_2}; color: {MUTED}; border: none; padding: 6px; font-weight: 600; }}
QTableWidget {{ gridline-color: {BORDER}; }}
QCheckBox::indicator {{ width: 15px; height: 15px; }}

QProgressBar {{
    background: {SURFACE_2}; border: 1px solid {BORDER}; border-radius: 4px; text-align: center;
    color: {TEXT}; font-size: 8.5pt; max-height: 16px;
}}
QProgressBar::chunk {{ background: {ACCENT}; border-radius: 3px; }}

QScrollBar:vertical {{ background: transparent; width: 10px; margin: 0; }}
QScrollBar::handle:vertical {{ background: #2e343e; border-radius: 5px; min-height: 30px; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 0; }}
QScrollBar::handle:horizontal {{ background: #2e343e; border-radius: 5px; min-width: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QSplitter::handle {{ background: {BG}; }}
QStatusBar {{ background: {SURFACE}; color: {MUTED}; border-top: 1px solid {BORDER}; }}
"""
