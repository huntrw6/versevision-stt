#!/bin/sh
# Build the current code and install/update it on a hermes-remote Mac, then set up its helpers. Settings and logs are kept.
#   sh scripts/deploy-to-node.sh jpl-graphics-imac
# Touches only the "versevision-stt" tool and ~/VerseVision-STT. The VerseVision importer is left exactly as it is.
set -eu
node="${1:?usage: deploy-to-node.sh NODE}"
cd "$(dirname "$0")/.."
rm -rf dist && uv build --wheel -q
wheel=$(ls dist/*.whl)
hermes-remote push "$node" "$wheel" "/tmp/$(basename "$wheel")" >/dev/null
hermes-remote push "$node" scripts/install-macos.sh /tmp/install-stt-macos.sh >/dev/null
hermes-remote run "$node" -- /bin/sh -c "sh /tmp/install-stt-macos.sh install /tmp/$(basename "$wheel"); rm -f /tmp/install-stt-macos.sh /tmp/$(basename "$wheel")"
# helper apps compile with the logged-in user's tools, so run the second step in the GUI session
hermes-remote gui --timeout 1500 --sh "$node" 'export PATH="$HOME/.local/bin:$PATH"; versevision-stt install' 
