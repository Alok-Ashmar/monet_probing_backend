from datetime import datetime
from typing import List, Optional, Union
from pydantic import BaseModel, Field

from .types import PyObjectId
from .enums import StatusEnum, LLMEnum, StrategyEnum


# -- Configuration Schemas
class SurveyConfig(BaseModel):
    """
    Configuration settings for a Survey.
    Includes settings for the language model, metrics tracking, and context addition.
    """

    language: str = "English"
    add_context: bool = False
    repetition: bool = True

class SurveyMedia(BaseModel):
    """
    Media information associated with a Survey, such as external video links or metadata.
    """

    media_url: str = ""
    media_filename: str = ""
    media_content_type: str = "video/mp4"
    media_description: str = ""
    media_name: str = ""
    media_movie_name: str = ""
    media_upload_timestamp: datetime = Field(default_factory=datetime.now)


class TargetConfig(BaseModel):
    """
    Configuration for probing targets to apply to questions.
    """

    target: str
    priority: int = 1
    strategy: StrategyEnum


class MediaConfig(BaseModel):
    """
    Configuration indicating if specific media types are available for a question.
    """

    available: bool = False
    audio: bool = False
    video: bool = False


class QuestionConfig(BaseModel):
    """
    Configuration specific to a single survey question.
    Controls probing behavior, contextual settings, and acceptable quality thresholds.
    """

    min_probes: int = 0
    max_probes: int = 0
    add_context: bool = False
    quality_threshold: int = 4
    gibberish_score: int = 4
    repetition: bool = True


# -- Base Survey Schemas
class Survey(BaseModel):
    """
    Base Pydantic schema for creating or representing a Survey metadata object.
    """

    title: str
    description: str
    media: SurveyMedia = Field(default_factory=SurveyMedia)
    config: SurveyConfig = Field(default_factory=SurveyConfig)
    createdAt: Optional[datetime] = None
    status: StatusEnum
    tags: List[str] = []
    display: bool


class SurveyQuestion(BaseModel):
    """
    Base Pydantic schema for creating or representing a specific Question within a Survey.
    """

    su_id: Optional[str] = None
    question: str
    description: str = ""
    seq_num: int = Field(..., description="Sequence position of the question")
    config: QuestionConfig = Field(default_factory=QuestionConfig)


class SurveyResponse(BaseModel):
    """
    Base Pydantic schema for processing or submitting user responses.
    """

    su_id: str
    mo_id: str
    qs_id: str
    cnt_id: Optional[int] = None
    question: str
    response: str
    comment: Optional[str] = None
    relevant: bool = True


# -- MongoDB (PyObjectId) Wrapper Schemas
class PySurveyQuestion(SurveyQuestion):
    """
    SurveyQuestion schema bound to MongoDB IDs.
    """

    su_id: PyObjectId = Field(default_factory=PyObjectId, alias="su_id")
    id: PyObjectId = Field(default_factory=PyObjectId, alias="_id")


class PySurveyResponse(SurveyResponse):
    """
    SurveyResponse schema bound to a MongoDB ID.
    """

    id: PyObjectId = Field(default_factory=PyObjectId, alias="_id")


class PySurvey(Survey):
    """
    Full Survey schema bound to MongoDB IDs, complete with its list of questions.
    """

    id: PyObjectId = Field(default_factory=PyObjectId, alias="_id")
    questions: List[PySurveyQuestion] = []


class CreateSurvey(Survey):
    """
    Schema for handling Survey creation payloads.
    """

    id: Optional[PyObjectId] = None
    questions: List[SurveyQuestion]


# -- Controller / DB Switcher Wrapper Schemas (Pd represents Database layer structures)
class PdSurvey(BaseModel):
    """
    Database-agnostic representation of a Survey used when interacting with the database service layer.
    """

    study_id: Optional[Union[str, int]] = 0
    cnt_id: Optional[Union[str, int]] = 0
    survey_description: str
    survey_title: Optional[str] = ""
    add_context: bool = False
    config: SurveyConfig = Field(default_factory=SurveyConfig)


class PdSurveyQuestion(BaseModel):
    """
    Database-agnostic representation of a Survey Question used with the database service layer.
    """

    qs_id: Optional[Union[str, int]] = 0
    su_id: Optional[Union[str, int]] = 0
    cnt_id: Optional[Union[str, int]] = 0
    question: str = "<question>"
    description: str = "<description>"
    config: QuestionConfig = Field(default_factory=QuestionConfig)


# -- API Response / Auth Schemas
class GetSurveyResponse(BaseModel):
    """
    Schema representing a standardized API response when fetching Surveys.
    """

    code: int
    error: bool
    message: str
    response: List[PySurvey]


class AccessRequest(BaseModel):
    """
    Schema representing a user request for platform access.
    """

    firstName: str
    lastName: str
    email: str
    organization: str
    department: str
    jobTitle: str
    requestType: str
    message: str


class get_token(BaseModel):
    """
    Schema representing the payload to request an authentication token.
    """

    client_id: str
    client_secret: str
    code: str
    redirect_uri: str
    grant_type: str


class NSIGHT(BaseModel):
    """
    Pydantic schema capturing LLM-evaluated quality metrics for a survey response.
    """

    quality: int
    relevance: int
    detail: int
    confusion: int
    negativity: int
    consistency: int
    confidence: int
    keywords: List[str]
    reason: str
    gibberish_score: int


class NSIGHT_v2(NSIGHT):
    """
    Extended NSIGHT schema that also stores the original question and response text.
    """

    question: str
    response: str
