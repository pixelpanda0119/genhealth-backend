"""
Pydantic schemas for document processing operations
"""

from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from datetime import datetime

class PatientInfo(BaseModel):
    """Schema for extracted patient information"""
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    date_of_birth: Optional[str] = None

class ValidationFieldResult(BaseModel):
    """Schema for individual field validation result"""
    is_valid: bool
    confidence: float
    issues: List[str] = []
    corrected_value: Optional[str] = None

class ValidationResults(BaseModel):
    """Schema for field-specific validation results"""
    first_name: Optional[ValidationFieldResult] = None
    last_name: Optional[ValidationFieldResult] = None
    date_of_birth: Optional[ValidationFieldResult] = None

class OverallValidation(BaseModel):
    """Schema for overall validation summary"""
    overall_confidence: float
    data_quality_score: float
    validation_summary: str
    recommendations: List[str] = []

class CorrectionApplied(BaseModel):
    """Schema for corrections applied during validation"""
    field: str
    original: Optional[str]
    corrected: str
    reason: List[str] = []

class AIValidationSummary(BaseModel):
    """Schema for AI validation summary"""
    validation_performed: bool
    validation_results: Optional[ValidationResults] = None
    overall_validation: Optional[OverallValidation] = None
    corrections_applied: List[CorrectionApplied] = []

class DocumentProcessResponse(BaseModel):
    """Schema for document processing response"""
    success: bool
    message: str
    patient_info: Optional[PatientInfo] = None
    extracted_text: Optional[str] = None
    processing_time_ms: Optional[int] = None
    extraction_method: Optional[str] = None
    confidence_score: Optional[float] = None
    ai_validation: Optional[AIValidationSummary] = None
    timestamp: datetime

class DocumentUploadResponse(BaseModel):
    """Schema for document upload response"""
    success: bool
    message: str
    filename: str
    file_size: int
    patient_info: Optional[PatientInfo] = None
    timestamp: datetime
