import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import difficulty
assert not difficulty.needs_escalation('write a short story')
assert difficulty.needs_escalation('Please architect and implement a multi-step workflow with testing.')
print('difficulty tests: 2/2 passed')
