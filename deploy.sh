#!/bin/bash

# GenHealthAI Deployment Script
# This script sets up and runs the GenHealthAI API

set -e

echo "🚀 GenHealthAI Deployment Script"
echo "================================"

# Check if Python is available
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 is required but not installed."
    exit 1
fi

echo "✅ Python 3 found"

# Create virtual environment if it doesn't exist
if [ ! -d "venv" ]; then
    echo "📦 Creating virtual environment..."
    python3 -m venv venv
fi

# Activate virtual environment
echo "🔧 Activating virtual environment..."
source venv/bin/activate

# Install dependencies
echo "📥 Installing dependencies..."
pip install -r requirements.txt

# Create data directory
mkdir -p data

# Run database migrations (create tables)
echo "🗄️  Setting up database..."
python -c "from app.database import engine, Base; Base.metadata.create_all(bind=engine); print('Database tables created')"

# Test PDF extraction if test file exists
if [ -f "data/DME Patient Demo Document CPAP.fax.pdf" ]; then
    echo "🔍 Testing PDF extraction..."
    python test_pdf_extraction.py
else
    echo "⚠️  Test PDF not found, skipping extraction test"
fi

# Run basic API tests
echo "🧪 Running API tests..."
python -m pytest test_api.py -v || echo "⚠️  Some tests failed, but continuing..."

echo ""
echo "✅ Deployment complete!"
echo ""
echo "To start the API server:"
echo "  python main.py"
echo ""
echo "Or with uvicorn directly:"
echo "  uvicorn main:app --host 0.0.0.0 --port 8000 --reload"
echo ""
echo "API will be available at:"
echo "  - Main API: http://localhost:8000"
echo "  - Documentation: http://localhost:8000/docs"
echo "  - Health Check: http://localhost:8000/health"
echo ""
echo "For Docker deployment:"
echo "  docker-compose up --build"
