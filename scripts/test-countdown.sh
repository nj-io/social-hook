#!/bin/bash
# Run from the worktree root:
#   ./scripts/test-countdown.sh
#
# Step 1: Save snapshot
# Step 2: Run trigger against a real commit
# Step 3: Check rate limit status
# Watch the dashboard between steps.

set -e
WORKTREE="$(cd "$(dirname "$0")/.." && pwd)"
export PYTHONPATH="$WORKTREE/src"

echo "=== Step 1: Save snapshot ==="
python3 -c "
from social_hook.filesystem import get_db_path
import shutil, pathlib
db = get_db_path()
dest = pathlib.Path.home() / '.social-hook/snapshots/pre-countdown-test.db'
shutil.copy2(str(db), str(dest))
print(f'Saved: {dest}')
"

echo ""
echo ">>> Check dashboard now. Should show 0/15, Available now."
echo ">>> Press Enter to run trigger..."
read

echo "=== Step 2: Run trigger against commit 1937cf9 ==="
python3 -c "
from social_hook.trigger import run_trigger
from social_hook.db.connection import init_database
from social_hook.filesystem import get_db_path
conn = init_database(get_db_path())
result = run_trigger(conn, '1937cf9', '$WORKTREE', trigger_source='commit')
print(f'Result: {result}')
conn.close()
"

echo ""
echo ">>> Check dashboard now. Should show 1/15 with a countdown timer."
echo ">>> Press Enter to run trigger again (should be deferred)..."
read

echo "=== Step 3: Run trigger again — should be deferred ==="
python3 -c "
from social_hook.trigger import run_trigger
from social_hook.db.connection import init_database
from social_hook.filesystem import get_db_path
conn = init_database(get_db_path())
result = run_trigger(conn, '095b374', '$WORKTREE', trigger_source='commit')
print(f'Result: {result}')
conn.close()
"

echo ""
echo ">>> Check dashboard. Should show 1/15, countdown still running, '1 queued'."
echo ""

echo "=== Rate limit status ==="
python3 -c "
from social_hook.db.connection import init_database
from social_hook.filesystem import get_db_path
from social_hook.config.yaml import load_config
from social_hook.rate_limits import get_rate_limit_status
conn = init_database(get_db_path())
status = get_rate_limit_status(conn, load_config().rate_limits)
for k, v in status.items():
    print(f'  {k}: {v}')
conn.close()
"
