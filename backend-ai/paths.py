"""Where the application keeps its files. The only module allowed to look at __file__.

HOME is the root of everything the app writes or reads at run time: data/, output/ and the
credentials .env. By default it is the folder this file lives in (today: backend-ai/), exactly
as before. Set FORECASTER_HOME to keep data somewhere else, so moving or packaging the code
never changes where saved data is found.

CODE_DIR is where the Python modules live. Worker processes start there (python -m <module>).
FORECASTER_DB_PATH still overrides the serving database only, as before.
"""
import os
from pathlib import Path

CODE_DIR = Path(__file__).resolve().parent


def _home():
    override = (os.environ.get('FORECASTER_HOME') or '').strip()
    return Path(override).expanduser().resolve() if override else CODE_DIR


def _live_db(home):
    override = (os.environ.get('FORECASTER_DB_PATH') or '').strip()
    return Path(override).expanduser().resolve() if override else home / 'data' / 'joolan_live.db'


HOME = _home()
DATA_DIR = HOME / 'data'
RAW_DIR = DATA_DIR / 'raw'
SYNC_DIR = DATA_DIR / 'joolan_sync'
OUTPUT_DIR = HOME / 'output'
ENV_FILE = HOME / '.env'

LIVE_DB = _live_db(HOME)
SOURCE_DB = DATA_DIR / 'joolan_source.db'
HISTORY_DB = DATA_DIR / 'history.db'
