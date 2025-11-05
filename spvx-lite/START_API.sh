#!/bin/bash

# SPVX API Server Startup Script
# Starts the FastAPI server with all endpoints including ship registry

cd "$(dirname "$0")"

echo "🚀 STARTING SPVX API SERVER"
echo "============================"
echo ""
echo "📍 API Endpoints:"
echo "   - Main API:        http://localhost:8000"
echo "   - Ship Registry:   http://localhost:8000/api/registry/status"
echo "   - Health:          http://localhost:8000/health"
echo "   - Docs:            http://localhost:8000/docs"
echo ""
echo "Press Ctrl+C to stop"
echo ""

source .venv/bin/activate
uvicorn spvx.api_app:app --host 0.0.0.0 --port 8000 --reload
