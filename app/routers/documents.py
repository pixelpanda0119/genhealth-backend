"""
Document processing endpoints
"""

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Request, Form
from sqlalchemy.orm import Session
from slowapi import Limiter
from slowapi.util import get_remote_address
from typing import Optional
import logging
from datetime import datetime

from app.database import get_db
from app.models.order import Order
from app.schemas.document import DocumentUploadResponse, DocumentProcessResponse, PatientInfo
from app.services.unified_document_processor import DocumentProcessor
from app.services.activity_logger import ActivityLogger
from app.auth.auth_handler import get_current_user, admin_required, user_required

logger = logging.getLogger(__name__)
limiter = Limiter(key_func=get_remote_address)

router = APIRouter()

@router.post("/upload", response_model=DocumentUploadResponse)
@limiter.limit("5/minute")
async def upload_document(
    request: Request,
    file: UploadFile = File(..., description="PDF document to process"),
    create_order: bool = Form(False, description="Whether to create an order from extracted data"),
    order_type: Optional[str] = Form(None, description="Order type if creating an order"),
    use_ai: bool = Form(True, description="Enable AI-enhanced processing"),
    current_user: dict = Depends(user_required),
    db: Session = Depends(get_db)
):
    """Upload and process a PDF document to extract patient information"""
    try:
        # Validate file type
        if not file.filename.lower().endswith('.pdf'):
            raise HTTPException(
                status_code=400,
                detail="Only PDF files are supported"
            )
        
        # Check file size (limit to 10MB)
        file_content = await file.read()
        file_size = len(file_content)
        
        if file_size > 10 * 1024 * 1024:  # 10MB
            raise HTTPException(
                status_code=400,
                detail="File size must be less than 10MB"
            )
        
        if file_size == 0:
            raise HTTPException(
                status_code=400,
                detail="File is empty"
            )
        
        # Process the document with unified processor
        processor = DocumentProcessor(enable_ai=True)  # AI available but controlled by use_ai parameter
        result = await processor.process_document(file_content, file.filename, use_ai=use_ai)
        
        patient_info = None
        if result["success"] and result["patient_info"]:
            patient_info = PatientInfo(**result["patient_info"])
        
        # Optionally create an order from the extracted data
        if create_order and result["success"] and patient_info:
            if not order_type:
                order_type = "Document Processing"
            
            try:
                # Generate a unique order number
                import uuid
                order_number = f"DOC-{uuid.uuid4().hex[:8].upper()}"
                
                # Create order with extracted patient information
                order_data = {
                    "order_number": order_number,
                    "patient_first_name": patient_info.first_name,
                    "patient_last_name": patient_info.last_name,
                    "patient_date_of_birth": patient_info.date_of_birth,
                    "order_type": order_type,
                    "status": "pending",
                    "notes": f"Created from document: {file.filename}"
                }
                
                db_order = Order(**order_data)
                db.add(db_order)
                db.commit()
                db.refresh(db_order)
                
                logger.info(f"Created order {order_number} from document {file.filename}")
                
            except Exception as e:
                logger.error(f"Failed to create order from document: {e}")
                # Don't fail the whole request if order creation fails
        
        return DocumentUploadResponse(
            success=result["success"],
            message=result["message"],
            filename=file.filename,
            file_size=file_size,
            patient_info=patient_info,
            timestamp=result["timestamp"]
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Document upload failed: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to process document: {str(e)}"
        )

@router.post("/process", response_model=DocumentProcessResponse)
@limiter.limit("5/minute")
async def process_document_only(
    request: Request,
    file: UploadFile = File(..., description="PDF document to process"),
    use_ai_validation: bool = Form(True, description="Enable AI validation of extracted data"),
    current_user: dict = Depends(user_required),
    db: Session = Depends(get_db)
):
    """Process a PDF document and return extracted information with AI validation"""
    try:
        # Validate file type
        if not file.filename.lower().endswith('.pdf'):
            raise HTTPException(
                status_code=400,
                detail="Only PDF files are supported"
            )
        
        # Check file size (limit to 10MB)
        file_content = await file.read()
        file_size = len(file_content)
        
        if file_size > 10 * 1024 * 1024:  # 10MB
            raise HTTPException(
                status_code=400,
                detail="File size must be less than 10MB"
            )
        
        if file_size == 0:
            raise HTTPException(
                status_code=400,
                detail="File is empty"
            )
        
        # Process the document with AI validation enabled
        processor = DocumentProcessor(enable_ai=True)
        result = await processor.process_document(file_content, file.filename, use_ai=use_ai_validation)
        
        return DocumentProcessResponse(**result)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Document processing failed: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to process document: {str(e)}"
        )

@router.post("/validate")
@limiter.limit("10/minute")
async def validate_extracted_data(
    request: Request,
    file: UploadFile = File(..., description="PDF document to validate against"),
    first_name: Optional[str] = Form(None, description="First name to validate"),
    last_name: Optional[str] = Form(None, description="Last name to validate"),
    date_of_birth: Optional[str] = Form(None, description="Date of birth to validate"),
    current_user: dict = Depends(user_required),
    db: Session = Depends(get_db)
):
    """Validate already extracted patient data against the original document using AI"""
    try:
        # Validate file type
        if not file.filename.lower().endswith('.pdf'):
            raise HTTPException(
                status_code=400,
                detail="Only PDF files are supported"
            )
        
        # Check file size (limit to 10MB)
        file_content = await file.read()
        file_size = len(file_content)
        
        if file_size > 10 * 1024 * 1024:  # 10MB
            raise HTTPException(
                status_code=400,
                detail="File size must be less than 10MB"
            )
        
        if file_size == 0:
            raise HTTPException(
                status_code=400,
                detail="File is empty"
            )
        
        # Prepare patient info for validation
        patient_info = {
            "first_name": first_name,
            "last_name": last_name,
            "date_of_birth": date_of_birth
        }
        
        # Extract text from document for validation
        processor = DocumentProcessor(enable_ai=True)
        text, _ = await processor._extract_text_from_pdf(file_content)
        
        # Perform AI validation
        validation_result = await processor._ai_validate_extracted_data(text, patient_info)
        
        if not validation_result:
            raise HTTPException(
                status_code=503,
                detail="AI validation service is not available"
            )
        
        return {
            "success": True,
            "message": "Validation completed successfully",
            "filename": file.filename,
            "original_data": patient_info,
            "validation_result": validation_result,
            "timestamp": datetime.utcnow()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Data validation failed: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to validate data: {str(e)}"
        )

@router.get("/supported-formats")
@limiter.limit("30/minute")
async def get_supported_formats(
    request: Request,
    current_user: dict = Depends(get_current_user)
):
    """Get list of supported document formats"""
    return {
        "supported_formats": [
            {
                "format": "PDF",
                "extensions": [".pdf"],
                "max_size_mb": 10,
                "description": "Portable Document Format files"
            }
        ],
        "extraction_capabilities": [
            "Patient first name",
            "Patient last name", 
            "Date of birth",
            "Full text extraction",
            "AI-powered validation and correction"
        ],
        "validation_features": [
            "OCR accuracy verification",
            "Data consistency checking",
            "Automatic error correction",
            "Confidence scoring",
            "Quality assessment"
        ]
    }
