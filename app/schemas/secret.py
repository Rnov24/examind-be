from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field, ConfigDict


class SecretResponse(BaseModel):
    id: int
    key_name: str
    service_name: str
    masked_value: str
    description: Optional[str] = None
    is_active: bool
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class SecretCreateOrUpdate(BaseModel):
    key_name: str = Field(..., min_length=2, max_length=100, description="Identifier name of the API key")
    service_name: str = Field(..., min_length=2, max_length=50, description="Service provider name (gemini, resend, openai, custom)")
    value: Optional[str] = Field(None, description="Raw API key value to encrypt and store. Required for new secrets, optional when updating.")
    description: Optional[str] = Field(None, max_length=255, description="Brief note about the key's usage")
    is_active: bool = Field(default=True, description="Whether the secret is actively used by the system")


class TestSecretRequest(BaseModel):
    service_name: str = Field(..., description="Service provider: gemini, resend, openai, custom")
    key_name: str = Field(..., description="Secret key name to test")
    test_value: Optional[str] = Field(None, description="Optional raw key value to test before saving")


class TestSecretResponse(BaseModel):
    success: bool
    service: str
    latency_ms: int
    message: str
