"""Register the mounted font; preserve all frozen calculations and view settings."""
from pathlib import Path
from matplotlib.font_manager import fontManager
import rfix_tables
fonts=list(Path('/fonts').glob('*Regular.ttc'))
if fonts:fontManager.addfont(str(fonts[0]))
rfix_tables.main()
