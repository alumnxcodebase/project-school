from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional, Any, Dict
from datetime import datetime
from bson import ObjectId

class AssessmentConfig(BaseModel):
    taskId: str
    title: str
    description: str
    endpoint_requirements: Dict[str, Any]
    test_cases: List[Dict[str, Any]]

class TestResultDetails(BaseModel):
    test_case_id: str
    description: str
    status: str # "passed", "failed", "error"
    input: Any
    expected_output: Any
    actual_output: Optional[Any] = None
    error_message: Optional[str] = None
    execution_time_ms: float

class AssessmentSubmission(BaseModel):
    model_config = ConfigDict(populate_by_name=True, json_encoders={ObjectId: str})
    id: Optional[str] = None
    userId: str
    taskId: str
    endpoint_url: str
    status: str # "passed", "failed"
    score: int # percentage or count
    total_tests: int
    passed_tests: int
    results: List[TestResultDetails]
    timestamp: datetime = Field(default_factory=datetime.now)

class RunAssessmentRequest(BaseModel):
    taskId: str
    studentUrl: str
