# GenHealthAI Document Processing API

A production-ready REST API for processing medical documents and extracting patient information. Built with FastAPI, SQLAlchemy, AI-enhanced document processing, and advanced PDF processing capabilities.

## Features

### Core Functionality
- **CRUD Operations**: Complete order management with validation
- **AI-Enhanced Document Processing**: Extract patient information (name, DOB) from PDF documents using advanced AI
- **Multi-Engine OCR**: Fallback processing with pdfplumber, PyPDF2, and Tesseract OCR
- **Activity Logging**: Comprehensive logging of all user activities
- **Database Persistence**: SQLite database with SQLAlchemy ORM

### AI Document Processing
- **GPT-4o Vision**: Direct analysis of document images for maximum accuracy
- **Text Analysis**: AI-powered text extraction and pattern recognition
- **Confidence Scoring**: Intelligent confidence assessment for extracted data
- **Fallback Processing**: Automatic fallback from AI → OCR → manual patterns
- **Image Preprocessing**: Advanced image enhancement for better OCR results

### Production-Ready Features
- **Rate Limiting**: Protect against abuse with configurable limits
- **Error Handling**: Robust error handling with detailed logging
- **Request Validation**: Pydantic schemas for request/response validation
- **CORS Support**: Configurable cross-origin resource sharing
- **API Documentation**: Automatic OpenAPI/Swagger documentation
- **Health Checks**: Built-in health monitoring endpoints
- **Docker Support**: Containerized deployment ready

### Security & Performance
- **Input Validation**: Comprehensive validation for all endpoints
- **File Size Limits**: Configurable upload size restrictions
- **Response Time Tracking**: Performance monitoring built-in
- **Structured Logging**: Comprehensive activity and error logging
- **Configurable AI**: Toggle AI processing on/off per request

## Quick Start

### Prerequisites
- Python 3.11+
- pip
- Tesseract OCR (for image-based PDF processing)
- OpenAI API Key (optional, for AI-enhanced processing)

### Installation

1. **Install Tesseract OCR** (required for image-based PDFs):
```bash
# Ubuntu/Debian
sudo apt update && sudo apt install tesseract-ocr

# macOS
brew install tesseract

# Windows
# Download and install from: https://github.com/UB-Mannheim/tesseract/wiki
```

2. **Clone and setup**:
```bash
git clone <repository>
cd GenHealthAI
pip install -r requirements.txt
```

3. **Configure AI (Optional)**:
```bash
# Copy environment template
cp env.example .env

# Edit .env and add your OpenAI API key
OPENAI_API_KEY=your-openai-api-key-here
```

4. **Run the application**:
```bash
python main.py
```

5. **Access the API**:
- API: http://localhost:8000
- Documentation: http://localhost:8000/docs
- Alternative docs: http://localhost:8000/redoc

### Docker Deployment

1. **Build and run with Docker**:
```bash
docker-compose up --build
```

2. **Access the containerized API**:
- API: http://localhost:8000

## API Endpoints

### Orders Management

#### Create Order
```http
POST /api/v1/orders/
Content-Type: application/json

{
  "order_number": "ORD-001",
  "patient_first_name": "John",
  "patient_last_name": "Doe",
  "patient_date_of_birth": "1980-01-15",
  "order_type": "CPAP Equipment",
  "status": "pending",
  "total_amount": 299.99,
  "notes": "Initial CPAP setup"
}
```

#### Get Orders (Paginated)
```http
GET /api/v1/orders/?page=1&page_size=10&status=pending
```

#### Get Single Order
```http
GET /api/v1/orders/{order_id}
```

#### Update Order
```http
PUT /api/v1/orders/{order_id}
Content-Type: application/json

{
  "status": "confirmed",
  "notes": "Order confirmed and ready for processing"
}
```

#### Delete Order
```http
DELETE /api/v1/orders/{order_id}
```

#### Search Orders by Patient
```http
GET /api/v1/orders/search/by-patient?first_name=John&last_name=Doe
```

### Document Processing

#### Upload and Process Document
```http
POST /api/v1/documents/upload
Content-Type: multipart/form-data

file: [PDF file]
create_order: true
order_type: "Document Processing"
use_ai: true
```

**Parameters:**
- `file`: PDF document to process (required)
- `create_order`: Whether to create an order from extracted data (default: false)
- `order_type`: Order type if creating an order (default: "Document Processing")
- `use_ai`: Enable AI-enhanced processing (default: true)

#### Process Document Only
```http
POST /api/v1/documents/process
Content-Type: multipart/form-data

file: [PDF file]
```

#### Get Supported Formats
```http
GET /api/v1/documents/supported-formats
```

### System Endpoints

#### Health Check
```http
GET /health
```

#### API Information
```http
GET /
```

## Document Processing Capabilities

### AI-Enhanced Processing
The API uses a sophisticated multi-tier approach for maximum accuracy:

1. **AI Vision Analysis**: Direct image analysis using GPT-4o Vision for complex documents
2. **AI Text Analysis**: Context-aware text processing for pattern recognition
3. **OCR Fallback**: Traditional OCR with image preprocessing when AI is unavailable
4. **Pattern Matching**: Regex-based extraction as final fallback

### Extracted Information
- **Patient First Name**: AI understands context and separates names from IDs
- **Patient Last Name**: Advanced disambiguation from document artifacts
- **Date of Birth**: Support for various date formats with validation
- **Confidence Scoring**: Each extraction includes confidence assessment
- **Full Text**: Complete text extraction for further processing

### Processing Methods
- **GPT-4o Vision**: Direct document image analysis (highest accuracy)
- **GPT-4o Text**: Context-aware text analysis
- **Tesseract OCR**: Image-based PDF text extraction with preprocessing
- **pdfplumber**: Native PDF text extraction
- **PyPDF2**: Alternative PDF text extraction

### Supported Formats
- PDF files up to 10MB
- Text-based PDFs (native extraction)
- Image-based/scanned PDFs (OCR + AI processing)
- Image preprocessing for improved OCR accuracy (noise reduction, contrast enhancement)
- Automatic format detection and optimal processing method selection

## Database Schema

### Orders Table
- `id`: Primary key
- `order_number`: Unique order identifier
- `patient_first_name`: Patient's first name
- `patient_last_name`: Patient's last name
- `patient_date_of_birth`: Patient's date of birth
- `order_type`: Type of order
- `status`: Order status (pending, confirmed, processing, shipped, delivered, cancelled)
- `total_amount`: Order total amount
- `notes`: Additional notes
- `created_at`: Creation timestamp
- `updated_at`: Last update timestamp

### Activity Logs Table
- `id`: Primary key
- `endpoint`: API endpoint accessed
- `method`: HTTP method
- `status_code`: Response status code
- `ip_address`: Client IP address
- `user_agent`: Client user agent
- `request_body`: Request payload (for small requests)
- `response_time_ms`: Response time in milliseconds
- `error_message`: Error details if applicable
- `created_at`: Activity timestamp

## Configuration

Copy `env.example` to `.env` and configure:

```bash
DATABASE_URL=sqlite:///./genhealth.db
DEBUG=False
LOG_LEVEL=INFO
SECRET_KEY=your-secret-key-here
RATE_LIMIT_PER_MINUTE=60
MAX_FILE_SIZE_MB=10
ALLOWED_ORIGINS=*
```

## Rate Limiting

Default rate limits:
- General endpoints: 30/minute
- Order creation/updates: 10/minute
- Document processing: 5/minute
- Health checks: 30/minute

## Error Handling

The API provides consistent error responses:

```json
{
  "error": "Error type",
  "message": "Detailed error message",
  "timestamp": "2024-01-01T12:00:00.000Z"
}
```

## Logging

All activities are logged with:
- Request/response details
- Performance metrics
- Error tracking
- User activity monitoring

## Testing

### Test PDF Processing
```bash
python test_pdf_extraction.py
```

### Run Unit Tests
```bash
pytest
```

## Production Deployment

### Environment Setup
1. Set production environment variables
2. Configure database (PostgreSQL recommended for production)
3. Set up reverse proxy (nginx)
4. Configure SSL certificates
5. Set up monitoring and logging

### Security Considerations
- Change default secret keys
- Configure CORS properly
- Set up authentication if needed
- Use HTTPS in production
- Configure rate limiting appropriately
- Set up database backups
- **Secure OpenAI API Key**: Store in environment variables, never in code
- **AI Rate Limiting**: Monitor AI API usage and costs

## Architecture

```
GenHealthAI/
├── app/
│   ├── models/          # SQLAlchemy models
│   ├── schemas/         # Pydantic schemas
│   ├── routers/         # API endpoints
│   ├── services/        # Business logic
│   │   └── unified_document_processor.py  # AI + OCR processing
│   ├── middleware/      # Custom middleware
│   └── database.py      # Database configuration
├── data/               # Database and test files
├── demo_ai_improvement.py  # AI vs OCR comparison demo
├── main.py            # Application entry point
├── requirements.txt   # Python dependencies (includes AI libraries)
├── env.example       # Environment configuration template
├── Dockerfile        # Container configuration
└── docker-compose.yml # Docker Compose setup
```

## Contributing

1. Follow PEP 8 style guidelines
2. Add tests for new features
3. Update documentation
4. Use type hints
5. Add logging for important operations

## License

This project is licensed under the MIT License.

## Support

For support and questions, please contact the development team.
