"""
Unified document processing service with OCR and AI capabilities
"""

import os
import base64
import pdfplumber
import PyPDF2
import re
import pytesseract
import cv2
import numpy as np
from typing import Optional, Tuple, Dict
from datetime import datetime
import logging
from io import BytesIO
from PIL import Image
import json
import re

# LangChain imports (optional - only used if AI is enabled)
try:
    from langchain_openai import ChatOpenAI
    from langchain.schema import HumanMessage
    from langchain.prompts import PromptTemplate
    LANGCHAIN_AVAILABLE = True
except ImportError:
    LANGCHAIN_AVAILABLE = False

logger = logging.getLogger(__name__)

class DocumentProcessor:
    """Unified document processor with OCR and optional AI capabilities"""
    
    def __init__(self, enable_ai: bool = True, openai_api_key: Optional[str] = None):
        """
        Initialize the document processor
        
        Args:
            enable_ai: Whether to enable AI-enhanced processing
            openai_api_key: OpenAI API key for AI processing
        """
        self.enable_ai = enable_ai and LANGCHAIN_AVAILABLE
        self.openai_api_key = openai_api_key or os.getenv("OPENAI_API_KEY")
        
        # Initialize AI components if available
        if self.enable_ai and LANGCHAIN_AVAILABLE and self.openai_api_key:
            try:
                self.llm = ChatOpenAI(
                    model="gpt-4o",  # GPT-4 with vision capabilities
                    api_key=self.openai_api_key,
                    temperature=0.1
                )
                logger.info("AI processing enabled with OpenAI API")
                self.enable_ai = True
            except Exception as e:
                logger.warning(f"Failed to initialize AI: {e}")
                self.enable_ai = False
        else:
            self.enable_ai = False
            if not LANGCHAIN_AVAILABLE:
                logger.info("AI processing disabled - LangChain not available")
            elif not self.openai_api_key:
                logger.info("AI processing disabled - OPENAI_API_KEY not set (set OPENAI_API_KEY environment variable to enable)")
            else:
                logger.info("AI processing disabled - using OCR only")
        
        # OCR patterns for extracting patient information
        self.name_patterns = [
            r'(?:patient\s+name|name|patient):\s*([A-Za-z]+(?:\s+[A-Za-z]+)*)',
            r'([A-Z][a-z]+)\s+([A-Z][a-z]+)(?:\s+(?:DOB|Date\s+of\s+Birth))',
            r'(?:^|\n)([A-Z][a-z]+\s+[A-Z][a-z]+)(?:\s|$)',
            r'(?:Mr\.|Mrs\.|Ms\.|Dr\.)\s+([A-Z][a-z]+\s+[A-Z][a-z]+)',
        ]
        
        self.dob_patterns = [
            r'(?:DOB|Date\s+of\s+Birth|Birth\s+Date):\s*(\d{1,2}[/-]\d{1,2}[/-]\d{4})',
            r'(?:DOB|Date\s+of\s+Birth|Birth\s+Date):\s*(\d{4}[/-]\d{1,2}[/-]\d{1,2})',
            r'(\d{1,2}[/-]\d{1,2}[/-]\d{4})',
            r'(\d{4}[/-]\d{1,2}[/-]\d{1,2})',
            r'(?:born|birth).*?(\d{1,2}[/-]\d{1,2}[/-]\d{4})',
        ]
        
        # AI prompts
        self.text_analysis_prompt = """
        You are a medical document analysis expert. Extract patient information from this document text.
        
        Document text:
        {document_text}
        
        IMPORTANT: Respond with ONLY valid JSON, no additional text or explanation.
        
        Extract the following information in this exact JSON format:
        {{
            "first_name": "patient's first name or null",
            "last_name": "patient's last name or null", 
            "date_of_birth": "date in MM/DD/YYYY format or null",
            "confidence_score": 0.8
        }}
        
        Rules:
        - Only extract information you are confident about
        - Use null (not "null") for missing values
        - Separate patient names from ID numbers, person numbers, or other fields
        - Date format must be MM/DD/YYYY
        - confidence_score must be a number between 0.0 and 1.0
        - Return ONLY the JSON object, no other text
        """
        
        self.validation_prompt = """
        You are a medical data validation expert. Your task is to validate and verify OCR-extracted patient information against the original document text.
        
        Original Document Text:
        {document_text}
        
        OCR-Extracted Information:
        - First Name: {first_name}
        - Last Name: {last_name}
        - Date of Birth: {date_of_birth}
        
        IMPORTANT: Respond with ONLY valid JSON, no additional text or explanation.
        
        Validate this information and provide analysis in this exact JSON format:
        {{
            "validation_results": {{
                "first_name": {{
                    "is_valid": true,
                    "confidence": 0.9,
                    "issues": [],
                    "corrected_value": null
                }},
                "last_name": {{
                    "is_valid": true,
                    "confidence": 0.9,
                    "issues": [],
                    "corrected_value": null
                }},
                "date_of_birth": {{
                    "is_valid": true,
                    "confidence": 0.9,
                    "issues": [],
                    "corrected_value": null
                }}
            }},
            "overall_validation": {{
                "overall_confidence": 0.9,
                "data_quality_score": 0.9,
                "validation_summary": "Brief summary of validation results",
                "recommendations": []
            }}
        }}
        
        Rules:
        - is_valid: true or false (boolean)
        - confidence: number between 0.0 and 1.0
        - issues: array of strings describing problems found
        - corrected_value: corrected value as string or null if no correction needed
        - Use null (not "null") for null values
        - Check if names are realistic human names (not numbers, codes, or artifacts)
        - Verify date format and logical date ranges (birth dates should be reasonable)
        - Look for OCR artifacts like mixed characters, impossible combinations
        - Return ONLY the JSON object, no other text
        """
        
        self.vision_analysis_prompt = """
        You are analyzing a medical document image. Extract patient information with high accuracy.
        
        IMPORTANT: Respond with ONLY valid JSON, no additional text or explanation.
        
        Please identify and extract patient information in this exact JSON format:
        {
            "first_name": "patient's first name or null",
            "last_name": "patient's last name or null",
            "date_of_birth": "date in MM/DD/YYYY format or null",
            "confidence_score": 0.8
        }
        
        Rules:
        - Only extract information you are highly confident about
        - Use null (not "null") for missing values
        - Separate patient names from ID numbers or other document fields
        - Date format must be MM/DD/YYYY
        - confidence_score must be a number between 0.0 and 1.0
        - Return ONLY the JSON object, no other text
        """
    
    async def process_document(self, file_content: bytes, filename: str, use_ai: bool = None) -> Dict:
        """
        Process a document and extract patient information
        
        Args:
            file_content: PDF file content as bytes
            filename: Name of the file
            use_ai: Override AI usage for this specific call
        """
        start_time = datetime.now()
        use_ai_for_this_call = use_ai if use_ai is not None else self.enable_ai
        
        try:
            # Step 1: Extract text using OCR
            logger.info("Starting OCR text extraction")
            text, ocr_method = await self._extract_text_from_pdf(file_content)
            
            # Step 2: Extract information using pattern matching
            first_name, last_name = self._extract_patient_name_ocr(text)
            date_of_birth = self._extract_date_of_birth(text)
            
            ocr_result = {
                "first_name": first_name,
                "last_name": last_name,
                "date_of_birth": date_of_birth
            }
            
            # Step 3: AI validation of OCR results (intelligent quality assessment)
            final_result = ocr_result
            final_method = f"ocr_{ocr_method}"
            final_confidence = self._calculate_confidence(ocr_result)
            validation_summary = None
            
            if use_ai_for_this_call and self.enable_ai:
                logger.info("Validating OCR results with AI")
                validation_result = await self._ai_validate_extracted_data(text, ocr_result)
                
                if validation_result:
                    validation_summary = validation_result["validation_summary"]
                    corrected_info = validation_result["corrected_patient_info"]
                    corrected_confidence = self._calculate_confidence(corrected_info)
                    
                    # Use AI-validated/corrected data
                    final_result = corrected_info
                    final_confidence = max(corrected_confidence, final_confidence)
                    final_method = f"ocr_{ocr_method}_ai_validated"
                    
                    if validation_result["validation_summary"]["corrections_applied"]:
                        logger.info("AI validation applied corrections to improve OCR data quality")
                    else:
                        logger.info("AI validation confirmed OCR results are accurate")
                
                # Step 4: Use AI enhancement if validation indicates low quality
                overall_validation = validation_summary.get("overall_validation", {}) if validation_summary else {}
                data_quality_score = overall_validation.get("data_quality_score", final_confidence)
                
                if data_quality_score < 0.7:
                    logger.info("Data quality low after validation, trying AI enhancement")
                    
                    # Try AI text analysis
                    ai_result = await self._ai_text_analysis(text)
                    if ai_result and self._calculate_confidence(ai_result) > final_confidence:
                        final_result = ai_result
                        final_method = "ai_text_enhanced"
                        final_confidence = self._calculate_confidence(ai_result)
                        logger.info("AI text analysis provided better results")
                        
                        # Validate the AI-enhanced results too
                        enhanced_validation = await self._ai_validate_extracted_data(text, ai_result)
                        if enhanced_validation:
                            validation_summary = enhanced_validation["validation_summary"]
                    
                    # Try AI vision if still not satisfactory
                    elif data_quality_score < 0.6:
                        logger.info("Trying AI vision analysis for better extraction")
                        vision_result = await self._ai_vision_analysis(file_content)
                        if vision_result and self._calculate_confidence(vision_result) > final_confidence:
                            final_result = vision_result
                            final_method = "ai_vision_enhanced"
                            final_confidence = self._calculate_confidence(vision_result)
                            logger.info("AI vision analysis provided better results")
                            
                            # Validate the vision results too
                            vision_validation = await self._ai_validate_extracted_data(text, vision_result)
                            if vision_validation:
                                validation_summary = vision_validation["validation_summary"]
            
            processing_time = (datetime.now() - start_time).total_seconds() * 1000
            
            # Prepare response with validation information
            response = {
                "success": True,
                "message": "Document processed successfully",
                "patient_info": final_result,
                "extracted_text": text[:500] + "..." if len(text) > 500 else text,
                "processing_time_ms": int(processing_time),
                "extraction_method": final_method,
                "confidence_score": final_confidence,
                "timestamp": datetime.utcnow()
            }
            
            # Add validation summary if available
            if validation_summary:
                response["ai_validation"] = validation_summary
            
            return response
            
        except Exception as e:
            logger.error(f"Document processing failed: {e}")
            processing_time = (datetime.now() - start_time).total_seconds() * 1000
            
            return {
                "success": False,
                "message": f"Failed to process document: {str(e)}",
                "patient_info": None,
                "extracted_text": None,
                "processing_time_ms": int(processing_time),
                "extraction_method": "error",
                "confidence_score": 0.0,
                "timestamp": datetime.utcnow()
            }
    
    async def _extract_text_from_pdf(self, file_content: bytes) -> Tuple[str, str]:
        """Extract text from PDF using multiple methods"""
        text = ""
        method = "none"
        
        # Method 1: pdfplumber
        try:
            with pdfplumber.open(BytesIO(file_content)) as pdf:
                for page in pdf.pages:
                    page_text = page.extract_text()
                    if page_text:
                        text += page_text + "\n"
            
            if text.strip():
                logger.info("Successfully extracted text using pdfplumber")
                return text, "pdfplumber"
        except Exception as e:
            logger.warning(f"pdfplumber extraction failed: {e}")
        
        # Method 2: PyPDF2
        try:
            pdf_reader = PyPDF2.PdfReader(BytesIO(file_content))
            for page in pdf_reader.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"
            
            if text.strip():
                logger.info("Successfully extracted text using PyPDF2")
                return text, "pypdf2"
        except Exception as e:
            logger.error(f"PyPDF2 extraction failed: {e}")
        
        # Method 3: OCR for image-based PDFs
        try:
            logger.info("Attempting OCR extraction for image-based PDF")
            text = await self._extract_text_with_ocr(file_content)
            
            if text.strip():
                logger.info("Successfully extracted text using OCR")
                return text, "tesseract"
        except Exception as e:
            logger.error(f"OCR extraction failed: {e}")
            if "tesseract" in str(e).lower():
                raise ValueError("Could not extract text from PDF. This appears to be an image-based PDF that requires OCR. Please install Tesseract OCR: 'sudo apt install tesseract-ocr' on Ubuntu/Debian or 'brew install tesseract' on macOS.")
        
        if not text.strip():
            raise ValueError("Could not extract text from PDF")
        
        return text, method
    
    async def _extract_text_with_ocr(self, file_content: bytes) -> str:
        """Extract text from image-based PDF using OCR"""
        text = ""
        
        with pdfplumber.open(BytesIO(file_content)) as pdf:
            for page_num, page in enumerate(pdf.pages):
                # Convert page to image
                page_image = page.to_image(resolution=200)
                
                # Convert PIL image to numpy array for OpenCV
                img_array = np.array(page_image.original)
                
                # Preprocess image for better OCR results
                processed_img = self._preprocess_image_for_ocr(img_array)
                
                # Perform OCR
                page_text = pytesseract.image_to_string(processed_img, config='--psm 6')
                
                if page_text.strip():
                    text += f"Page {page_num + 1}:\n{page_text}\n\n"
        
        return text
    
    def _preprocess_image_for_ocr(self, img_array: np.ndarray) -> np.ndarray:
        """Preprocess image to improve OCR accuracy"""
        # Convert to grayscale
        if len(img_array.shape) == 3:
            gray = cv2.cvtColor(img_array, cv2.COLOR_RGB2GRAY)
        else:
            gray = img_array
        
        # Apply Gaussian blur to reduce noise
        blurred = cv2.GaussianBlur(gray, (5, 5), 0)
        
        # Apply adaptive thresholding to improve contrast
        thresh = cv2.adaptiveThreshold(
            blurred, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2
        )
        
        # Apply morphological operations to clean up the image
        kernel = np.ones((2, 2), np.uint8)
        cleaned = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel)
        
        return cleaned
    
    def _extract_patient_name_ocr(self, text: str) -> Tuple[Optional[str], Optional[str]]:
        """Extract patient first and last name from text using OCR patterns"""
        first_name = None
        last_name = None
        
        # Clean up the text
        text = re.sub(r'\s+', ' ', text)
        
        for pattern in self.name_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE | re.MULTILINE)
            
            if matches:
                for match in matches:
                    if isinstance(match, tuple):
                        # Pattern captured multiple groups
                        if len(match) >= 2:
                            first_name = match[0].strip().title()
                            last_name = match[1].strip().title()
                            break
                    else:
                        # Single capture group - split the name
                        name_parts = match.strip().split()
                        if len(name_parts) >= 2:
                            first_name = name_parts[0].title()
                            # Clean up last name (remove common OCR artifacts)
                            last_name_parts = name_parts[1:]
                            # Filter out common OCR artifacts
                            cleaned_parts = []
                            for part in last_name_parts:
                                # Skip parts that look like numbers or common artifacts
                                if not re.match(r'.*\d.*', part) and part.lower() not in ['person', 'number', 'id']:
                                    cleaned_parts.append(part)
                                else:
                                    break  # Stop at first artifact
                            
                            if cleaned_parts:
                                last_name = ' '.join(cleaned_parts).title()
                            break
                
                if first_name and last_name:
                    break
        
        # Additional heuristics for common medical document formats
        if not first_name or not last_name:
            # Look for patterns like "SMITH, JOHN" or "Smith, John"
            comma_pattern = r'([A-Z][a-z]+),\s+([A-Z][a-z]+)'
            matches = re.findall(comma_pattern, text)
            if matches:
                last_name = matches[0][0].title()
                first_name = matches[0][1].title()
        
        return first_name, last_name
    
    def _extract_date_of_birth(self, text: str) -> Optional[str]:
        """Extract date of birth from text"""
        # Clean up the text
        text = re.sub(r'\s+', ' ', text)
        
        for pattern in self.dob_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            
            if matches:
                # Take the first valid looking date
                date_str = matches[0].strip()
                
                # Normalize date format
                date_str = re.sub(r'[/-]', '/', date_str)
                
                # Validate date format
                if self._is_valid_date_format(date_str):
                    return date_str
        
        return None
    
    def _is_valid_date_format(self, date_str: str) -> bool:
        """Validate if the date string looks like a valid date"""
        try:
            # Check common date formats
            parts = date_str.split('/')
            if len(parts) != 3:
                return False
            
            # Convert to integers
            nums = [int(part) for part in parts]
            
            # Check if it looks like MM/DD/YYYY or DD/MM/YYYY
            if len(parts[2]) == 4:  # Year is 4 digits
                month, day, year = nums[0], nums[1], nums[2]
                if 1 <= month <= 12 and 1 <= day <= 31 and 1900 <= year <= 2030:
                    return True
            
            # Check if it looks like YYYY/MM/DD
            if len(parts[0]) == 4:  # Year is first
                year, month, day = nums[0], nums[1], nums[2]
                if 1900 <= year <= 2030 and 1 <= month <= 12 and 1 <= day <= 31:
                    return True
            
            return False
            
        except (ValueError, IndexError):
            return False
    
    async def _ai_text_analysis(self, text: str) -> Optional[Dict]:
        """Analyze extracted text using AI"""
        if not self.enable_ai:
            return None
            
        try:
            prompt = self.text_analysis_prompt.format(document_text=text[:4000])
            response = await self.llm.ainvoke([HumanMessage(content=prompt)])
            
            # Parse JSON response with error handling
            import json
            import re
            
            response_content = response.content.strip()
            
            # Try to extract JSON from the response if it contains extra text
            json_match = re.search(r'\{.*\}', response_content, re.DOTALL)
            if json_match:
                json_str = json_match.group(0)
            else:
                json_str = response_content
            
            try:
                result = json.loads(json_str)
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse AI text analysis response: {e}")
                logger.error(f"Response content: {response_content[:500]}...")
                return None
            
            return {
                "first_name": result.get("first_name"),
                "last_name": result.get("last_name"),
                "date_of_birth": result.get("date_of_birth")
            }
        except Exception as e:
            logger.error(f"AI text analysis failed: {e}")
            return None
    
    async def _ai_vision_analysis(self, file_content: bytes) -> Optional[Dict]:
        """Analyze document image directly using AI vision"""
        if not self.enable_ai:
            return None
            
        try:
            # Convert PDF first page to base64 image
            image_base64 = await self._pdf_to_base64_image(file_content)
            
            message = HumanMessage(
                content=[
                    {"type": "text", "text": self.vision_analysis_prompt},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{image_base64}"}
                    }
                ]
            )
            
            response = await self.llm.ainvoke([message])
            
            # Parse JSON response with error handling
     
            
            response_content = response.content.strip()
            
            # Try to extract JSON from the response if it contains extra text
            json_match = re.search(r'\{.*\}', response_content, re.DOTALL)
            if json_match:
                json_str = json_match.group(0)
            else:
                json_str = response_content
            
            try:
                result = json.loads(json_str)
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse AI vision analysis response: {e}")
                logger.error(f"Response content: {response_content[:500]}...")
                return None
            
            return {
                "first_name": result.get("first_name"),
                "last_name": result.get("last_name"),
                "date_of_birth": result.get("date_of_birth")
            }
        except Exception as e:
            logger.error(f"AI vision analysis failed: {e}")
            return None
    
    async def _ai_validate_extracted_data(self, text: str, patient_info: Dict) -> Optional[Dict]:
        """Validate OCR-extracted data using AI analysis"""
        if not self.enable_ai or not patient_info:
            return None
            
        try:
            prompt = self.validation_prompt.format(
                document_text=text[:4000],  # Limit text length
                first_name=patient_info.get("first_name", "None"),
                last_name=patient_info.get("last_name", "None"),
                date_of_birth=patient_info.get("date_of_birth", "None")
            )
            
            response = await self.llm.ainvoke([HumanMessage(content=prompt)])
            
            response_content = response.content.strip()
            
            # Try to extract JSON from the response if it contains extra text
            json_match = re.search(r'\{.*\}', response_content, re.DOTALL)
            if json_match:
                json_str = json_match.group(0)
            else:
                json_str = response_content
            
            try:
                validation_result = json.loads(json_str)
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse AI validation response: {e}")
                logger.error(f"Response content: {response_content[:500]}...")
                # Return a fallback validation result
                validation_result = {
                    "validation_results": {
                        "first_name": {"is_valid": True, "confidence": 0.5, "issues": ["Unable to validate due to parsing error"]},
                        "last_name": {"is_valid": True, "confidence": 0.5, "issues": ["Unable to validate due to parsing error"]},
                        "date_of_birth": {"is_valid": True, "confidence": 0.5, "issues": ["Unable to validate due to parsing error"]}
                    },
                    "overall_validation": {
                        "overall_confidence": 0.5,
                        "data_quality_score": 0.5,
                        "validation_summary": "Validation failed due to response parsing error",
                        "recommendations": ["Manual review recommended due to validation error"]
                    }
                }
            
            # Process validation results and apply corrections if needed
            corrected_info = patient_info.copy()
            validation_summary = {
                "validation_performed": True,
                "validation_results": validation_result.get("validation_results", {}),
                "overall_validation": validation_result.get("overall_validation", {}),
                "corrections_applied": []
            }
            
            # Apply corrections if AI suggests better values
            for field in ["first_name", "last_name", "date_of_birth"]:
                field_validation = validation_result.get("validation_results", {}).get(field, {})
                corrected_value = field_validation.get("corrected_value")
                
                if corrected_value and corrected_value != patient_info.get(field):
                    corrected_info[field] = corrected_value
                    validation_summary["corrections_applied"].append({
                        "field": field,
                        "original": patient_info.get(field),
                        "corrected": corrected_value,
                        "reason": field_validation.get("issues", [])
                    })
            
            return {
                "corrected_patient_info": corrected_info,
                "validation_summary": validation_summary
            }
            
        except Exception as e:
            logger.error(f"AI validation failed: {e}")
            return None
    
    async def _pdf_to_base64_image(self, file_content: bytes) -> str:
        """Convert first page of PDF to base64 image"""
        with pdfplumber.open(BytesIO(file_content)) as pdf:
            first_page = pdf.pages[0]
            page_image = first_page.to_image(resolution=150)
            
            # Convert to base64
            img_buffer = BytesIO()
            page_image.original.save(img_buffer, format='JPEG', quality=85)
            img_base64 = base64.b64encode(img_buffer.getvalue()).decode()
            
            return img_base64
    
    def _calculate_confidence(self, patient_info: Dict) -> float:
        """Calculate confidence score based on extracted information"""
        if not patient_info:
            return 0.0
        
        score = 0.0
        
        # First name
        if patient_info.get("first_name"):
            score += 0.4
        
        # Last name
        if patient_info.get("last_name"):
            score += 0.4
            # Bonus for clean last name (no numbers or artifacts)
            last_name = patient_info["last_name"]
            if not re.search(r'\d|person|number|id', last_name.lower()):
                score += 0.1
        
        # Date of birth
        if patient_info.get("date_of_birth"):
            score += 0.2
        
        return min(score, 1.0)
