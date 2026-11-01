"""Start/reuse MeiMei services for the desktop pet without opening the main UI."""
from pathlib import Path
import sys
root=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root/'app'))
import desktop
desktop.use_log_file()
desktop.ensure_services(7788,str(Path.home()/'Documents/rm-workspace'),with_voice=True)
if not desktop.wait_port(7788,120):raise SystemExit('MeiMei backend did not become ready')
print('MeiMei services ready',flush=True)
