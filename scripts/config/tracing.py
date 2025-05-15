"""LangSmith tracing configuration for the extraction pipeline."""

import os
import logging
from langsmith import Client, trace
from langsmith.evaluation import evaluate
from langchain_core.tracers import LangChainTracer
from . import settings

logger = logging.getLogger(__name__)


class TracingConfig:
    """Configuration and management for LangSmith tracing."""
    
    def __init__(self):
        """Initialise tracing configuration."""
        self.enabled = settings.LANGSMITH_TRACING_ENABLED
        self.client = None
        self.tracer = None
        
    def initialise(self):
        """Initialise LangSmith client and tracer."""
        if not self.enabled:
            logger.info("LangSmith tracing is disabled")
            return
            
        if not settings.LANGSMITH_API_KEY:
            logger.warning("LANGSMITH_API_KEY not set - tracing disabled")
            self.enabled = False
            return
            
        try:
            self.client = Client(
                api_key=settings.LANGSMITH_API_KEY,
                api_url=settings.LANGSMITH_ENDPOINT
            )
            
            self.tracer = LangChainTracer(
                project_name=settings.LANGSMITH_PROJECT,
                client=self.client
            )
            
            logger.info(f"LangSmith tracing initialised for project: {settings.LANGSMITH_PROJECT}")
            
        except Exception as e:
            logger.error(f"Failed to initialise LangSmith tracing: {e}")
            self.enabled = False
    
    def get_run_metadata(self, operation_type, file_path=None):
        """Generate metadata for a traced run."""
        metadata = {
            "operation": operation_type,
            "environment": os.getenv("ENVIRONMENT", "development"),
            "extraction_model": settings.GEMINI_MODEL
        }
        
        if file_path:
            metadata["file_path"] = file_path
            metadata["file_size"] = os.path.getsize(file_path) if os.path.exists(file_path) else None
            
        return metadata


# Global tracing instance
_tracing_config = TracingConfig()


def initialise_tracing():
    """Initialise global tracing configuration."""
    _tracing_config.initialise()


def get_tracer():
    """Get the LangChain tracer instance."""
    return _tracing_config.tracer


def is_tracing_enabled():
    """Check if tracing is enabled."""
    return _tracing_config.enabled


def create_run_metadata(operation_type, **kwargs):
    """Create metadata for a traced run."""
    return _tracing_config.get_run_metadata(operation_type, **kwargs)