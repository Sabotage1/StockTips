#!/bin/bash

# StockTips AI — Launcher Script

cd "$(dirname "$0")"

# Check Python
if ! command -v python3 &> /dev/null; then
    echo "Error: python3 is required but not found."
    exit 1
fi

# Create virtual environment if needed
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

# Activate venv
source venv/bin/activate

# Install dependencies
echo "Installing dependencies..."
pip install -r requirements.txt --quiet

# Check .env
if [ ! -f ".env" ]; then
    echo "Error: .env file not found. Copy .env.example to .env and fill in your API keys."
    exit 1
fi

echo ""
echo "========================================="
echo "  StockTips AI"
echo "========================================="
echo "  Web Dashboard: http://localhost:8000"
echo "  Telegram Bot:  Active (if token set)"
echo "========================================="
echo ""

# Run the app
python3 -m uvicorn app:app --host 0.0.0.0 --port 8000 --reload
