#!/bin/bash

# Start XLM-RoBERTa Intent Classification Server
cd /home/siamai/openmem0ai_feat/MonkeyResearcher/services/local/local-deep-researcher/

echo "Starting Intent Classification Server on port 8762..."
python intent_server.py