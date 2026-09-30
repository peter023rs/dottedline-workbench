#!/bin/zsh
cd -- "${0:A:h}"
if [[ ! -x .venv/bin/python ]]; then
  echo 'Install the runtime first: uv venv .venv --python 3.12 && uv pip install --python .venv/bin/python -r requirements.txt'
  read '?Press Return to close.'
  exit 1
fi
if curl -fsS http://127.0.0.1:8767/health 2>/dev/null | /usr/bin/grep -q dottedline-workbench; then
  open http://127.0.0.1:8767
else
  .venv/bin/python server.py --open
fi
