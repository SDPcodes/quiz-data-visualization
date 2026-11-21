"""Project-wide settings: file paths, cleaning thresholds and the colour palette.

Keeping these in one place means every script uses the same rules, and a
reader can see all the important choices without digging through the code.
"""
from pathlib import Path

# ---------------------------------------------------------------- paths
ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "dataset"
OUT_DIR = ROOT / "outputs"
FIG_DIR = OUT_DIR / "figures"
TABLE_DIR = OUT_DIR / "tables"

QUIZ_FILES = {
    1: DATA_DIR / "quiz1" / "quiz1_marks.csv",
    2: DATA_DIR / "quiz2" / "quiz2_marks.csv",
    3: DATA_DIR / "quiz3" / "quiz3_marks.csv",
}

QUESTIONS = ["Q1", "Q2", "Q3", "Q4", "Q5"]
MARK_PER_QUESTION = 2.0

# ---------------------------------------------------------------- cleaning
# The quiz has no time limit, so some attempts stay "open" for hours or days
# (the browser tab is left open). These do not show real working time.
# Attempts longer than this are kept in the data but flagged, and they are
# left out of every analysis that uses time.
MAX_ACTIVE_MINUTES = 60

# Student performance tiers, based on the average FIRST-attempt mark across
# the three quizzes: Low < 4, Medium 4 to < 6, High >= 6 (out of 10).
TIER_LABELS = ["Low", "Medium", "High"]
TIER_CUTS = (4.0, 6.0)

RANDOM_SEED = 5805

# ---------------------------------------------------------------- palette
# Colour-blind-safe categorical colours (validated with a CVD checker).
QUIZ_COLORS = {1: "#2a78d6", 2: "#eb6834", 3: "#1baf7a"}
# Ordered tiers use one hue from light to dark (ordinal ramp).
TIER_COLORS = {"Low": "#86b6ef", "Medium": "#2a78d6", "High": "#104281"}
# Diverging pair for "went down / no change / went up".
DOWN_COLOR = "#e34948"
NEUTRAL_COLOR = "#c3c2b7"
UP_COLOR = "#2a78d6"
ACCENT = "#eb6834"          # used sparingly to highlight one thing
SEQ_CMAP_COLORS = ["#f4f8fd", "#cde2fb", "#9ec5f4", "#6da7ec",
                   "#3987e5", "#256abf", "#184f95", "#0d366b"]

INK = "#0b0b0b"
INK_2 = "#52514e"
MUTED = "#898781"
GRID = "#e1e0d9"
AXIS = "#c3c2b7"
