from datetime import datetime
from typing import Optional, Dict, Any
from pydantic import BaseModel, ConfigDict


class TenantResponse(BaseModel):
    id: int
    name: str
    code: str
    domain: Optional[str] = None
    subscription_plan: str
    subscription_status: str
    max_students: int
    max_teachers: int
    max_storage_gb: int
    ai_credits_monthly: int
    ai_credits_used: int
    is_active: bool
    created_at: Optional[datetime] = None
    total_users: int = 0
    total_students: int = 0
    total_teachers: int = 0
    total_exams: int = 0

    model_config = ConfigDict(from_attributes=True)


class TenantCreate(BaseModel):
    name: str
    code: str
    domain: Optional[str] = None
    subscription_plan: str = "pro"
    max_students: int = 500
    max_teachers: int = 50
    ai_credits_monthly: int = 1000
    # Optional initial school administrator
    admin_identifier: Optional[str] = None
    admin_email: Optional[str] = None
    admin_full_name: Optional[str] = None
    admin_password: Optional[str] = None


class TenantUpdate(BaseModel):
    name: Optional[str] = None
    domain: Optional[str] = None
    subscription_plan: Optional[str] = None
    subscription_status: Optional[str] = None
    max_students: Optional[int] = None
    max_teachers: Optional[int] = None
    ai_credits_monthly: Optional[int] = None
    is_active: Optional[bool] = None


class SuperAdminStatsResponse(BaseModel):
    total_tenants: int
    active_tenants: int
    plan_distribution: Dict[str, int]
    total_global_users: int
    total_global_students: int
    total_global_teachers: int
    total_global_exams: int
    total_ai_credits_used: int
    server_status: str
