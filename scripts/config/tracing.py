"""LangSmith tracing configuration module."""

import os
import logging
from typing import Optional
from langsmith import Client
from langsmith.utils import LangSmithError

logger = logging.getLogger(__name__)


class TracingConfig:
    """Configuration and client management for LangSmith tracing."""
    
    def __init__(self):
        """Initialise tracing configuration."""
        self.enabled = os.getenv("LANGSMITH_TRACING_V2", "").lower() == "true"
        self.api_key = os.getenv("LANGSMITH_API_KEY")
        self.project_name = os.getenv("LANGSMITH_PROJECT", "microlearning-extraction")
        self.endpoint = os.getenv("LANGSMITH_ENDPOINT", "https://api.smith.langchain.com")
        
        self._client: Optional[Client] = None
        
        if self.enabled and not self.api_key:
            logger.warning("LANGSMITH_TRACING_V2 is enabled but LANGSMITH_API_KEY is not set")
            self.enabled = False
    
    @property
    def client(self) -> Optional[Client]:
        """Get or create LangSmith client."""
        if not self.enabled:
            return None
            
        if self._client is None and self.api_key:
            try:
                self._client = Client(
                    api_url=self.endpoint,
                    api_key=self.api_key
                )
                logger.info(f"LangSmith client initialised for project: {self.project_name}")
            except Exception as e:
                logger.error(f"Failed to initialise LangSmith client: {e}")
                self.enabled = False
                
        return self._client
    
    def is_configured(self) -> bool:
        """Check if tracing is properly configured and enabled."""
        return self.enabled and self.api_key is not None
    
    def get_project_url(self) -> Optional[str]:
        """Get the URL for the current project in LangSmith UI."""
        if not self.is_configured():
            return None
            
        # Construct the project URL
        base_url = self.endpoint.replace("/api", "")
        return f"{base_url}/o/-/projects/p/{self.project_name}"


# Global instance
tracing_config = TracingConfig()