from pathlib import Path
from datetime import date

# Paths
PROJECT_ROOT = Path(__file__).resolve().parent.parent
PLAN_FILE = PROJECT_ROOT / "plan.json"
DATA_DIR = PROJECT_ROOT / "data"
ACTIVITIES_DIR = DATA_DIR / "activities"
REPORTS_DIR = DATA_DIR / "reports"

# Race info
RACE_DATE = date(2026, 10, 2)
RACE_NAME = "Ultra Trail Tarahumara 59km"
RACE_DISTANCE_KM = 59
RACE_VERT_M = 2400
PLAN_START = date(2026, 3, 2)  # Monday of week 1
TOTAL_WEEKS = 30

# Alert thresholds
HR_DRIFT_BPM = 10          # easy run HR above 4-week rolling avg
VOLUME_SPIKE_PCT = 10       # unplanned increase over previous week
LONG_RUN_RATIO_PCT = 30     # longest run as % of weekly volume
RECOVERY_REDUCTION_PCT = 20  # minimum reduction expected in recovery weeks

# Compliance score weights
COMPLIANCE_WEIGHTS = {
    "distance": 0.30,
    "vert": 0.20,
    "long_run": 0.20,
    "gym": 0.15,
    "series": 0.15,
}

# Garmin activity type mapping
RUNNING_TYPES = {"running", "trail_running", "treadmill_running"}
GYM_TYPES = {"strength_training", "indoor_cardio"}
