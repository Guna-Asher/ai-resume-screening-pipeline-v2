"""Structured errors for the ingestion / screening pipeline."""

from enum import StrEnum


class ProcessingStage(StrEnum):
    DISCOVER = "discover"
    READ = "read"
    PARSE = "parse"
    EXTRACT = "extract"
    SCREEN = "screen"


class ResumeProcessingError(Exception):
    """A single resume could not be processed. Carries the stage that failed."""

    stage: ProcessingStage = ProcessingStage.READ

    def __init__(self, message: str, *, stage: ProcessingStage | None = None) -> None:
        super().__init__(message)
        if stage is not None:
            self.stage = stage


class UnsupportedFormatError(ResumeProcessingError):
    stage = ProcessingStage.READ


class FileTooLargeError(ResumeProcessingError):
    stage = ProcessingStage.READ


class ResumeParseError(ResumeProcessingError):
    """The file was readable but no usable text could be extracted from it."""

    stage = ProcessingStage.PARSE
