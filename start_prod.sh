#!/bin/bash
set -e
export OLLAMA_KEEP_ALIVE=5m

echo "🚀 Starting IOCL RAG System (Production Mode)..."

# Ensure Environment
if [ -d ".venv" ]; then
    echo "Using .venv environment..."
    source .venv/bin/activate
elif [ -d "venv" ]; then
    echo "Using venv environment..."
    source venv/bin/activate
else
    echo "Warning: .venv not found, assuming system python or externally activated env."
fi

# Frontend Check
if [ ! -d "frontend/dist" ]; then
    echo "Frontend build not found at frontend/dist"
    echo "   Running build now..."
    cd frontend && npm install && npm run build && cd ..
fi

# Ensure Ollama is running
# Ensure Ollama is running (Check Port 11434)
if ! nc -z localhost 11434; then
    echo "Ollama is not reachable on port 11434. Starting Ollama..."
    # Attempt to start
    ollama serve > ollama.log 2>&1 &
    OLLAMA_PID=$!
    echo "   Started Ollama (PID: $OLLAMA_PID). Waiting for it to be ready..."
    
    # Wait for port 11434
    for i in {1..30}; do
        if nc -z localhost 11434; then
            echo "Ollama is ready!"
            break
        fi
        echo "   Waiting for Ollama..."
        sleep 1
    done
    
    # Final Check
    if ! nc -z localhost 11434; then
        echo "CRUD: Ollama failed to start after 30 seconds. Check ollama.log."
        # Don't exit, maybe it's just slow, but warn heavily
        echo "   Attempting to continue, but RAG may fail..."
    fi
else
    echo "Ollama is already running on port 11434."
fi

# Run Backend with Uvicorn (Workers=4 for concurrency)
echo "Launching Server on http://0.0.0.0:8000"
# echo "   - Docs: http://0.0.0.0:8000/api/v1/docs"
echo "   - UI:   http://0.0.0.0:8000/"

# Use exec to replace shell process
exec uvicorn app.main:app \
    --host 0.0.0.0 \
    --port 8000 \
    --workers 1 \
    --log-level info
