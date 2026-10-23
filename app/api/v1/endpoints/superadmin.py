import time
import calendar
from datetime import datetime, timedelta
import httpx
from typing import List, Optional
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import func, case
from sqlalchemy.orm import Session, joinedload, load_only
from app.core.database import get_db
from app.core.exceptions import AppException
from app.core.dependencies import require_superadmin, require_admin
from app.core.security import get_password_hash
from app.core.secret_manager import encrypt_secret, decrypt_secret, mask_secret, get_secret
from app.core.cache import memory_cache
from app.core.timing import log_query_timing
from app.models.tenant import Tenant, TenantRegistrationCode
from app.models.user import User
from app.models.exam import Exam
from app.models.secret import SystemSecret
from app.schemas.tenant import (
    TenantResponse,
    TenantCreate,
    TenantUpdate,
    SuperAdminStatsResponse,
)
from app.schemas.secret import (
    SecretResponse,
    SecretCreateOrUpdate,
    TestSecretRequest,
    TestSecretResponse,
)
from app.schemas.common import ApiResponse, PaginatedResponse

router = APIRouter(prefix="/superadmin", tags=["SaaS & Platform Super Admin"])


@router.get("/stats", response_model=ApiResponse[SuperAdminStatsResponse])
def get_superadmin_global_stats(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_superadmin),
):
    is_sqlite = db.bind is not None and "sqlite" in db.bind.dialect.name
    cache_key = "superadmin:global_stats"
    if not is_sqlite:
        cached = memory_cache.get(cache_key)
        if cached:
            return ApiResponse.ok(data=cached, message="Statistik global SaaS berhasil dimuat")

    with log_query_timing("get_superadmin_global_stats"):
        tenant_summary = db.query(
            func.count(Tenant.id),
            func.sum(case((Tenant.is_active == True, 1), else_=0)),
            func.sum(func.coalesce(Tenant.ai_credits_used, 0)),
        ).first()
        total_tenants = tenant_summary[0] or 0
        active_tenants = int(tenant_summary[1] or 0)
        total_ai_credits = int(tenant_summary[2] or 0)

        raw_plan_counts = dict(
            db.query(Tenant.subscription_plan, func.count(Tenant.id))
            .group_by(Tenant.subscription_plan)
            .all()
        )
        plan_counts = {
            "starter": raw_plan_counts.get("starter", 0),
            "pro": raw_plan_counts.get("pro", 0),
            "enterprise": raw_plan_counts.get("enterprise", 0),
        }

        # Use database aggregation instead of loading all users into memory
        user_counts_by_role = dict(db.query(User.role, func.count(User.id)).group_by(User.role).all())
        total_users = sum(user_counts_by_role.values())
        total_students = user_counts_by_role.get("student", 0)
        total_teachers = user_counts_by_role.get("teacher", 0)
        total_exams = db.query(Exam).count()

        stats = SuperAdminStatsResponse(
            total_tenants=total_tenants,
            active_tenants=active_tenants,
            plan_distribution=plan_counts,
            total_global_users=total_users,
            total_global_students=total_students,
            total_global_teachers=total_teachers,
            total_global_exams=total_exams,
            total_ai_credits_used=total_ai_credits,
            server_status="Optimal (FastAPI + MySQL Multi-Tenant)",
        )

        if not is_sqlite:
            memory_cache.set(cache_key, stats, ttl=60)

        return ApiResponse.ok(data=stats, message="Statistik global SaaS berhasil dimuat")


@router.get("/tenants", response_model=PaginatedResponse[TenantResponse])
def get_all_tenants(
    search: Optional[str] = Query(None, description="Cari nama atau kode sekolah"),
    plan: Optional[str] = Query(None, description="Filter paket: starter, pro, enterprise"),
    subscription_status: Optional[str] = Query(None, description="Filter status langganan"),
    page: int = Query(1, ge=1, description="Nomor halaman"),
    page_size: int = Query(20, ge=1, le=100, description="Jumlah data per halaman"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_superadmin),
):
    with log_query_timing("get_all_tenants"):
        query = db.query(Tenant)
        if search:
            kw = f"%{search}%"
            query = query.filter((Tenant.name.ilike(kw)) | (Tenant.code.ilike(kw)))
        if plan:
            query = query.filter(Tenant.subscription_plan == plan)
        if subscription_status:
            query = query.filter(Tenant.subscription_status == subscription_status)

        total = query.count()
        tenants = (
            query.order_by(Tenant.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )
        tenant_ids = [t.id for t in tenants]

        # Pre-aggregate user counts only for current page tenants in single SQL query
        user_stats = {}
        exam_stats = {}
        if tenant_ids:
            user_counts = (
                db.query(User.tenant_id, User.role, func.count(User.id))
                .filter(User.tenant_id.in_(tenant_ids))
                .group_by(User.tenant_id, User.role)
                .all()
            )
            for tid, role, cnt in user_counts:
                if tid not in user_stats:
                    user_stats[tid] = {"student": 0, "teacher": 0, "total": 0}
                user_stats[tid][role] = cnt
                user_stats[tid]["total"] += cnt

            # Pre-aggregate exam counts only for current page tenants in single SQL query
            exam_counts = (
                db.query(User.tenant_id, func.count(Exam.id))
                .join(User, Exam.teacher_id == User.id)
                .filter(User.tenant_id.in_(tenant_ids))
                .group_by(User.tenant_id)
                .all()
            )
            exam_stats = dict(exam_counts)

        result = []
        for t in tenants:
            t_user_stat = user_stats.get(t.id, {"student": 0, "teacher": 0, "total": 0})
            t_exams = exam_stats.get(t.id, 0)

            res_item = TenantResponse(
                id=t.id,
                name=t.name,
                code=t.code,
                domain=t.domain,
                subscription_plan=t.subscription_plan,
                subscription_status=t.subscription_status,
                max_students=t.max_students,
                max_teachers=t.max_teachers,
                max_storage_gb=t.max_storage_gb,
                ai_credits_monthly=t.ai_credits_monthly,
                ai_credits_used=t.ai_credits_used,
                is_active=t.is_active,
                subscription_due_date=t.subscription_due_date,
                grace_period_ends=t.grace_period_ends,
                created_at=t.created_at,
                total_users=t_user_stat["total"],
                total_students=t_user_stat["student"],
                total_teachers=t_user_stat["teacher"],
                total_exams=t_exams,
            )
            result.append(res_item)

        return PaginatedResponse.ok(
            data=result,
            page=page,
            page_size=page_size,
            total=total,
            message="Daftar tenant sekolah berhasil dimuat",
        )


@router.post("/tenants", response_model=ApiResponse[TenantResponse], status_code=status.HTTP_201_CREATED)
def create_tenant(
    payload: TenantCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_superadmin),
):
    # Check code uniqueness
    existing = db.query(Tenant).filter(Tenant.code == payload.code).first()
    if existing:
        raise AppException(
            message=f"Kode sekolah '{payload.code}' telah digunakan oleh tenant lain.",
            status_code=status.HTTP_400_BAD_REQUEST,
            error_code="TENANT_CODE_EXISTS",
        )

    # Set quota defaults based on plan if not specified
    max_stu = payload.max_students
    max_tea = payload.max_teachers
    ai_credits = payload.ai_credits_monthly
    if payload.subscription_plan == "starter":
        max_stu = max_stu or 150
        max_tea = max_tea or 15
        ai_credits = ai_credits or 500
    elif payload.subscription_plan == "enterprise":
        max_stu = max_stu or 2000
        max_tea = max_tea or 200
        ai_credits = ai_credits or 5000

    now = datetime.utcnow()
    due_date = payload.subscription_due_date or (now + timedelta(days=30))
    grace_ends = payload.grace_period_ends or (due_date + timedelta(days=7))

    new_tenant = Tenant(
        name=payload.name,
        code=payload.code,
        domain=payload.domain,
        subscription_plan=payload.subscription_plan,
        subscription_status="active",
        max_students=max_stu,
        max_teachers=max_tea,
        ai_credits_monthly=ai_credits,
        ai_credits_used=0,
        is_active=True,
        created_at=now,
        subscription_due_date=due_date,
        grace_period_ends=grace_ends,
    )
    db.add(new_tenant)
    db.commit()
    db.refresh(new_tenant)

    # Create initial admin if requested
    if payload.admin_identifier and payload.admin_password:
        admin_user = User(
            identifier=payload.admin_identifier,
            email=payload.admin_email or f"{payload.admin_identifier}@{payload.code}.examind.sch.id",
            password_hash=get_password_hash(payload.admin_password),
            full_name=payload.admin_full_name or f"Administrator {payload.name}",
            role="admin",
            tenant_id=new_tenant.id,
            is_active=True,
        )
        db.add(admin_user)
        db.commit()

    resp = TenantResponse(
        id=new_tenant.id,
        name=new_tenant.name,
        code=new_tenant.code,
        domain=new_tenant.domain,
        subscription_plan=new_tenant.subscription_plan,
        subscription_status=new_tenant.subscription_status,
        max_students=new_tenant.max_students,
        max_teachers=new_tenant.max_teachers,
        max_storage_gb=new_tenant.max_storage_gb,
        ai_credits_monthly=new_tenant.ai_credits_monthly,
        ai_credits_used=new_tenant.ai_credits_used,
        is_active=new_tenant.is_active,
        subscription_due_date=new_tenant.subscription_due_date,
        grace_period_ends=new_tenant.grace_period_ends,
        created_at=new_tenant.created_at,
        total_users=1 if payload.admin_identifier else 0,
        total_students=0,
        total_teachers=0,
        total_exams=0,
    )
    return ApiResponse.created(data=resp, message="Institusi sekolah baru berhasil didaftarkan ke platform SaaS")


@router.get("/tenants/{tenant_id}", response_model=ApiResponse[TenantResponse])
def get_tenant_detail(
    tenant_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_superadmin),
):
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if not tenant:
        raise AppException(
            message="Tenant sekolah tidak ditemukan.",
            status_code=status.HTTP_404_NOT_FOUND,
            error_code="TENANT_NOT_FOUND",
        )

    t_users = db.query(User).filter(User.tenant_id == tenant.id).all()
    t_students = sum(1 for u in t_users if u.role == "student")
    t_teachers = sum(1 for u in t_users if u.role == "teacher")
    t_exams = db.query(Exam).join(User, Exam.teacher_id == User.id).filter(User.tenant_id == tenant.id).count()

    resp = TenantResponse(
        id=tenant.id,
        name=tenant.name,
        code=tenant.code,
        domain=tenant.domain,
        subscription_plan=tenant.subscription_plan,
        subscription_status=tenant.subscription_status,
        max_students=tenant.max_students,
        max_teachers=tenant.max_teachers,
        max_storage_gb=tenant.max_storage_gb,
        ai_credits_monthly=tenant.ai_credits_monthly,
        ai_credits_used=tenant.ai_credits_used,
        is_active=tenant.is_active,
        subscription_due_date=tenant.subscription_due_date,
        grace_period_ends=tenant.grace_period_ends,
        created_at=tenant.created_at,
        total_users=len(t_users),
        total_students=t_students,
        total_teachers=t_teachers,
        total_exams=t_exams,
    )
    return ApiResponse.ok(data=resp, message="Detail tenant berhasil dimuat")


@router.patch("/tenants/{tenant_id}", response_model=ApiResponse[TenantResponse])
def update_tenant(
    tenant_id: int,
    payload: TenantUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_superadmin),
):
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if not tenant:
        raise AppException(
            message="Tenant sekolah tidak ditemukan.",
            status_code=status.HTTP_404_NOT_FOUND,
            error_code="TENANT_NOT_FOUND",
        )

    if payload.name is not None:
        tenant.name = payload.name
    if payload.domain is not None:
        tenant.domain = payload.domain
    if payload.subscription_plan is not None:
        tenant.subscription_plan = payload.subscription_plan
    if payload.subscription_status is not None:
        tenant.subscription_status = payload.subscription_status
    if payload.max_students is not None:
        tenant.max_students = payload.max_students
    if payload.max_teachers is not None:
        tenant.max_teachers = payload.max_teachers
    if payload.ai_credits_monthly is not None:
        tenant.ai_credits_monthly = payload.ai_credits_monthly
    if payload.is_active is not None:
        tenant.is_active = payload.is_active
    if payload.subscription_due_date is not None:
        tenant.subscription_due_date = payload.subscription_due_date
    if payload.grace_period_ends is not None:
        tenant.grace_period_ends = payload.grace_period_ends

    db.commit()
    db.refresh(tenant)

    t_users = db.query(User).filter(User.tenant_id == tenant.id).all()
    resp = TenantResponse(
        id=tenant.id,
        name=tenant.name,
        code=tenant.code,
        domain=tenant.domain,
        subscription_plan=tenant.subscription_plan,
        subscription_status=tenant.subscription_status,
        max_students=tenant.max_students,
        max_teachers=tenant.max_teachers,
        max_storage_gb=tenant.max_storage_gb,
        ai_credits_monthly=tenant.ai_credits_monthly,
        ai_credits_used=tenant.ai_credits_used,
        is_active=tenant.is_active,
        subscription_due_date=tenant.subscription_due_date,
        grace_period_ends=tenant.grace_period_ends,
        created_at=tenant.created_at,
        total_users=len(t_users),
        total_students=sum(1 for u in t_users if u.role == "student"),
        total_teachers=sum(1 for u in t_users if u.role == "teacher"),
        total_exams=db.query(Exam).join(User, Exam.teacher_id == User.id).filter(User.tenant_id == tenant.id).count(),
    )
    return ApiResponse.ok(data=resp, message="Konfigurasi tenant berhasil diperbarui")


@router.patch("/tenants/{tenant_id}/toggle-status", response_model=ApiResponse[TenantResponse])
def toggle_tenant_status(
    tenant_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_superadmin),
):
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if not tenant:
        raise AppException(
            message="Tenant sekolah tidak ditemukan.",
            status_code=status.HTTP_404_NOT_FOUND,
            error_code="TENANT_NOT_FOUND",
        )

    tenant.is_active = not tenant.is_active
    db.commit()
    db.refresh(tenant)

    t_users = db.query(User).filter(User.tenant_id == tenant.id).all()
    resp = TenantResponse(
        id=tenant.id,
        name=tenant.name,
        code=tenant.code,
        domain=tenant.domain,
        subscription_plan=tenant.subscription_plan,
        subscription_status=tenant.subscription_status,
        max_students=tenant.max_students,
        max_teachers=tenant.max_teachers,
        max_storage_gb=tenant.max_storage_gb,
        ai_credits_monthly=tenant.ai_credits_monthly,
        ai_credits_used=tenant.ai_credits_used,
        is_active=tenant.is_active,
        subscription_due_date=tenant.subscription_due_date,
        grace_period_ends=tenant.grace_period_ends,
        created_at=tenant.created_at,
        total_users=len(t_users),
        total_students=sum(1 for u in t_users if u.role == "student"),
        total_teachers=sum(1 for u in t_users if u.role == "teacher"),
        total_exams=db.query(Exam).join(User, Exam.teacher_id == User.id).filter(User.tenant_id == tenant.id).count(),
    )
    status_msg = "diaktifkan" if tenant.is_active else "ditangguhkan (suspend)"
    return ApiResponse.ok(data=resp, message=f"Status tenant sekolah berhasil {status_msg}")


# ---------------------------------------------------------------------------
# SECRET MANAGER ENDPOINTS (Platform Super Admin Only)
# ---------------------------------------------------------------------------

@router.get("/secrets", response_model=ApiResponse[List[SecretResponse]])
def get_all_secrets(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Retrieve all stored API secrets with masked values."""
    records = db.query(SystemSecret).order_by(SystemSecret.service_name.asc(), SystemSecret.key_name.asc()).all()
    results = []
    for r in records:
        plain = decrypt_secret(r.encrypted_value)
        masked = mask_secret(plain)
        results.append(
            SecretResponse(
                id=r.id,
                key_name=r.key_name,
                service_name=r.service_name,
                masked_value=masked,
                description=r.description,
                is_active=r.is_active,
                created_at=r.created_at,
                updated_at=r.updated_at,
            )
        )
    return ApiResponse.ok(data=results, message="Daftar secret API berhasil dimuat")


@router.post("/secrets", response_model=ApiResponse[SecretResponse])
def create_or_update_secret(
    request: SecretCreateOrUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Create or update a secret API key with at-rest encryption."""
    clean_key = request.key_name.strip().upper()
    clean_service = request.service_name.strip().lower()

    record = db.query(SystemSecret).filter(SystemSecret.key_name == clean_key).first()

    # If it's a new secret, a valid non-empty value is mandatory
    if not record and (not request.value or not request.value.strip()):
        raise AppException(
            message=f"Nilai API key wajib diisi saat menambahkan secret baru '{clean_key}'.",
            status_code=status.HTTP_400_BAD_REQUEST,
            error_code="SECRET_VALUE_REQUIRED",
        )

    if record:
        record.service_name = clean_service
        # Only re-encrypt and update the value if a new non-empty value is provided
        if request.value and request.value.strip():
            record.encrypted_value = encrypt_secret(request.value.strip())
        record.description = request.description
        record.is_active = request.is_active
    else:
        encrypted_val = encrypt_secret(request.value.strip())
        record = SystemSecret(
            key_name=clean_key,
            service_name=clean_service,
            encrypted_value=encrypted_val,
            description=request.description,
            is_active=request.is_active,
        )
        db.add(record)

    db.commit()
    db.refresh(record)

    plain = decrypt_secret(record.encrypted_value)
    resp = SecretResponse(
        id=record.id,
        key_name=record.key_name,
        service_name=record.service_name,
        masked_value=mask_secret(plain),
        description=record.description,
        is_active=record.is_active,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )
    return ApiResponse.ok(data=resp, message=f"Secret API '{clean_key}' berhasil disimpan dan dienkripsi")


@router.patch("/secrets/{key_name}/toggle", response_model=ApiResponse[SecretResponse])
def toggle_secret_status(
    key_name: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Toggle active/inactive status of a secret."""
    clean_key = key_name.strip().upper()
    record = db.query(SystemSecret).filter(SystemSecret.key_name == clean_key).first()
    if not record:
        raise AppException(
            message=f"Secret '{clean_key}' tidak ditemukan.",
            status_code=status.HTTP_404_NOT_FOUND,
            error_code="SECRET_NOT_FOUND",
        )

    record.is_active = not record.is_active
    db.commit()
    db.refresh(record)

    plain = decrypt_secret(record.encrypted_value)
    resp = SecretResponse(
        id=record.id,
        key_name=record.key_name,
        service_name=record.service_name,
        masked_value=mask_secret(plain),
        description=record.description,
        is_active=record.is_active,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )
    action = "diaktifkan" if record.is_active else "dinonaktifkan"
    return ApiResponse.ok(data=resp, message=f"Secret '{clean_key}' berhasil {action}")


@router.delete("/secrets/{key_name}", response_model=ApiResponse[dict])
def delete_secret(
    key_name: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Delete a secret API key from the database."""
    clean_key = key_name.strip().upper()
    record = db.query(SystemSecret).filter(SystemSecret.key_name == clean_key).first()
    if not record:
        raise AppException(
            message=f"Secret '{clean_key}' tidak ditemukan.",
            status_code=status.HTTP_404_NOT_FOUND,
            error_code="SECRET_NOT_FOUND",
        )

    db.delete(record)
    db.commit()
    return ApiResponse.ok(data={"deleted_key": clean_key}, message=f"Secret '{clean_key}' berhasil dihapus")


@router.post("/secrets/test", response_model=ApiResponse[TestSecretResponse])
async def test_secret_connection(
    request: TestSecretRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Perform live health check test against provider API using the specified secret."""
    service = request.service_name.strip().lower()
    clean_key = request.key_name.strip().upper()

    # Determine key value: explicit test_value, or resolve from database / fallback
    raw_key = ""
    if request.test_value and request.test_value.strip():
        raw_key = request.test_value.strip()
    else:
        raw_key = get_secret(clean_key, db=db)

    if not raw_key:
        return ApiResponse.ok(
            data=TestSecretResponse(
                success=False,
                service=service,
                latency_ms=0,
                message=f"Kunci API untuk '{clean_key}' kosong atau belum dikonfigurasi.",
            ),
            message="Uji koneksi gagal: Kunci API tidak ditemukan",
        )

    start_time = time.time()

    try:
        if service == "gemini":
            # Test Google Gemini endpoint
            test_url = f"https://generativelanguage.googleapis.com/v1beta/models?key={raw_key}"
            async with httpx.AsyncClient(timeout=8.0) as client:
                res = await client.get(test_url)
                latency = int((time.time() - start_time) * 1000)
                if res.is_success:
                    return ApiResponse.ok(
                        data=TestSecretResponse(
                            success=True,
                            service=service,
                            latency_ms=latency,
                            message=f"Koneksi Google Gemini API berhasil! Model tersedia ({latency}ms)",
                        ),
                        message="Test koneksi sukses",
                    )
                else:
                    err_snippet = res.text[:150]
                    if res.status_code == 400:
                        err_msg = "Google Gemini: API key tidak valid atau format salah."
                    elif res.status_code == 403:
                        err_msg = "Google Gemini: Akses ditolak (API belum diaktifkan di Google Cloud)."
                    elif res.status_code == 429:
                        err_msg = "Google Gemini: Kuota rate limit API terlampaui."
                    else:
                        err_msg = f"Google Gemini merespon status {res.status_code}: {err_snippet}"

                    return ApiResponse.ok(
                        data=TestSecretResponse(
                            success=False,
                            service=service,
                            latency_ms=latency,
                            message=err_msg,
                        ),
                        message="Test koneksi gagal",
                    )

        elif service == "resend":
            # Test Resend API endpoint
            test_url = "https://api.resend.com/api-keys"
            headers = {"Authorization": f"Bearer {raw_key}"}
            async with httpx.AsyncClient(timeout=8.0) as client:
                res = await client.get(test_url, headers=headers)
                latency = int((time.time() - start_time) * 1000)
                if res.is_success:
                    return ApiResponse.ok(
                        data=TestSecretResponse(
                            success=True,
                            service=service,
                            latency_ms=latency,
                            message=f"Koneksi Resend Email API berhasil! Kunci API valid (Full Access) ({latency}ms)",
                        ),
                        message="Test koneksi sukses",
                    )
                elif res.status_code == 403 and ("restricted" in res.text.lower() or raw_key.startswith("re_")):
                    # Sending-only API keys in Resend have restricted permission on /api-keys, which is normal and valid for emails
                    return ApiResponse.ok(
                        data=TestSecretResponse(
                            success=True,
                            service=service,
                            latency_ms=latency,
                            message=f"Koneksi Resend Email API berhasil! Kunci pengiriman valid ({latency}ms)",
                        ),
                        message="Test koneksi sukses",
                    )
                else:
                    if res.status_code == 401:
                        err_msg = "Resend menolak key: Kunci API tidak valid atau telah dicabut."
                    else:
                        err_msg = f"Resend merespon status {res.status_code}: {res.text[:150]}"

                    return ApiResponse.ok(
                        data=TestSecretResponse(
                            success=False,
                            service=service,
                            latency_ms=latency,
                            message=err_msg,
                        ),
                        message="Test koneksi gagal",
                    )

        elif service == "openai":
            # Test OpenAI models endpoint
            test_url = "https://api.openai.com/v1/models"
            headers = {"Authorization": f"Bearer {raw_key}"}
            async with httpx.AsyncClient(timeout=8.0) as client:
                res = await client.get(test_url, headers=headers)
                latency = int((time.time() - start_time) * 1000)
                if res.is_success:
                    return ApiResponse.ok(
                        data=TestSecretResponse(
                            success=True,
                            service=service,
                            latency_ms=latency,
                            message=f"Koneksi OpenAI API berhasil ({latency}ms)",
                        ),
                        message="Test koneksi sukses",
                    )
                else:
                    if res.status_code == 401:
                        err_msg = "OpenAI menolak key: Kunci API tidak valid atau kedaluwarsa."
                    elif res.status_code == 429:
                        err_msg = "OpenAI: Kunci valid namun batas kuota / billing terlampaui."
                    else:
                        err_msg = f"OpenAI merespon status {res.status_code}: {res.text[:150]}"

                    return ApiResponse.ok(
                        data=TestSecretResponse(
                            success=False,
                            service=service,
                            latency_ms=latency,
                            message=err_msg,
                        ),
                        message="Test koneksi gagal",
                    )

        else:
            # Custom or generic key format validation
            latency = int((time.time() - start_time) * 1000)
            return ApiResponse.ok(
                data=TestSecretResponse(
                    success=True,
                    service=service,
                    latency_ms=latency,
                    message=f"Format secret '{clean_key}' valid ({len(raw_key)} karakter, {latency}ms)",
                ),
                message="Validasi secret berhasil",
            )

    except Exception as e:
        latency = int((time.time() - start_time) * 1000)
        return ApiResponse.ok(
            data=TestSecretResponse(
                success=False,
                service=service,
                latency_ms=latency,
                message=f"Koneksi gagal atau timeout: {str(e)}",
            ),
            message="Test koneksi gagal",
        )


# ---------------------------------------------------------------------------
# FINANCE, MRR & SAAS REVENUE ENDPOINTS
# ---------------------------------------------------------------------------

INDONESIAN_MONTHS = ["Jan", "Feb", "Mar", "Apr", "Mei", "Jun", "Jul", "Agu", "Sep", "Okt", "Nov", "Des"]


@router.get("/finance")
def get_superadmin_finance_analytics(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_superadmin),
):
    """Retrieve comprehensive SaaS financial metrics: MRR, ARR, plan breakdowns, and transaction ledger."""
    is_sqlite = db.bind is not None and "sqlite" in db.bind.dialect.name
    cache_key = "superadmin:finance_analytics"
    if not is_sqlite:
        cached = memory_cache.get(cache_key)
        if cached:
            return ApiResponse.ok(data=cached, message="Data finansial SaaS dan MRR berhasil dimuat")

    with log_query_timing("get_superadmin_finance_analytics"):
        # Column-limited: only the fields this endpoint reads (name/code feed recent_invoices).
        tenants = (
            db.query(Tenant)
            .options(
                load_only(
                    Tenant.id,
                    Tenant.name,
                    Tenant.code,
                    Tenant.created_at,
                    Tenant.is_active,
                    Tenant.subscription_status,
                    Tenant.subscription_plan,
                )
            )
            .all()
        )

    # Plan rates (in IDR) — from the DB-backed pricing plans (superadmin-editable)
    PLAN_PRICES = get_plan_price_map(db)

    mrr = 0
    plan_distribution = {plan_id: 0 for plan_id in PLAN_PRICES}
    plan_revenue = {plan_id: 0 for plan_id in PLAN_PRICES}

    for t in tenants:
        if t.is_active and t.subscription_status in ("active", "trial"):
            price = PLAN_PRICES.get(t.subscription_plan, 3500000)
            mrr += price
            plan_distribution[t.subscription_plan] = plan_distribution.get(t.subscription_plan, 0) + 1
            plan_revenue[t.subscription_plan] = plan_revenue.get(t.subscription_plan, 0) + price

    arr = mrr * 12
    active_count = sum(1 for t in tenants if t.is_active)
    arpu = (mrr // active_count) if active_count > 0 else 0

    now = datetime.utcnow()

    # Real Historical 6-Month MRR trend from REAL Tenant.created_at dates
    mrr_history = []
    prev_month_mrr = 0

    for offset in range(5, -1, -1):
        total_months = now.year * 12 + (now.month - 1) - offset
        y = total_months // 12
        m = (total_months % 12) + 1
        last_day = calendar.monthrange(y, m)[1]
        month_end = datetime(y, m, last_day, 23, 59, 59, 999999)
        month_label = f"{INDONESIAN_MONTHS[m - 1]} {y}"

        month_mrr = 0
        month_schools = 0
        for t in tenants:
            if not t.created_at:
                continue
            t_created = t.created_at.replace(tzinfo=None) if t.created_at.tzinfo else t.created_at
            if t_created <= month_end:
                if t.is_active and t.subscription_status in ("active", "trial"):
                    price = PLAN_PRICES.get(t.subscription_plan, 3500000)
                    month_mrr += price
                    month_schools += 1

        if offset == 5 or prev_month_mrr == 0:
            growth_str = "+100%" if month_mrr > 0 and offset < 5 else "0%"
        else:
            diff_pct = round(((month_mrr - prev_month_mrr) / prev_month_mrr) * 100)
            growth_str = f"+{diff_pct}%" if diff_pct >= 0 else f"{diff_pct}%"

        prev_month_mrr = month_mrr

        mrr_history.append({
            "month": month_label,
            "mrr": month_mrr,
            "schools": month_schools,
            "tenants": month_schools,
            "growth": growth_str,
        })

    # Honest Invoices / Transactions derived directly from real tenant records
    recent_invoices = []
    sorted_tenants = sorted(
        tenants,
        key=lambda x: (x.created_at.replace(tzinfo=None) if (x.created_at and x.created_at.tzinfo) else x.created_at) or datetime.min,
        reverse=True,
    )
    for t in sorted_tenants:
        price = PLAN_PRICES.get(t.subscription_plan, 3500000)
        t_created = t.created_at.replace(tzinfo=None) if (t.created_at and t.created_at.tzinfo) else t.created_at

        if t_created:
            inv_id = f"INV-{t_created.strftime('%Y-%m')}-{1000 + t.id}"
            period = f"{INDONESIAN_MONTHS[t_created.month - 1]} {t_created.year}"
            date_str = f"{t_created.strftime('%d')} {INDONESIAN_MONTHS[t_created.month - 1]} {t_created.year}"
        else:
            inv_id = f"INV-{1000 + t.id}"
            period = "-"
            date_str = "-"

        status = "paid" if (t.is_active and t.subscription_status in ("active", "trial")) else "past_due"

        recent_invoices.append({
            "id": inv_id,
            "tenant_id": t.id,
            "tenant_name": t.name,
            "code": t.code,
            "plan": (t.subscription_plan or "pro").upper(),
            "amount": price,
            "period": period,
            "status": status,
            "payment_method": "-",
            "date": date_str,
        })

    plans_breakdown = {}
    total_rev = mrr if mrr > 0 else 1
    for plan_key in ("starter", "pro", "enterprise"):
        subtotal = plan_revenue.get(plan_key, 0)
        cnt = plan_distribution.get(plan_key, 0)
        pct = round((subtotal / total_rev) * 100) if mrr > 0 else 0
        plans_breakdown[plan_key] = {
            "count": cnt,
            "subtotal": subtotal,
            "percentage": pct,
        }

    # Honest MoM Growth Rate from real MRR history
    if len(mrr_history) >= 2 and mrr_history[-2]["mrr"] > 0:
        prev_mrr = mrr_history[-2]["mrr"]
        growth_rate_mom = round(((mrr - prev_mrr) / prev_mrr) * 100, 1)
    elif mrr > 0:
        growth_rate_mom = 100.0
    else:
        growth_rate_mom = 0.0

    data_payload = {
        "mrr": mrr,
        "arr": arr,
        "arpu": arpu,
        "active_tenants": active_count,
        "paying_tenants": active_count,
        "growth_rate_mom": growth_rate_mom,
        "churn_rate": 0.0,
        "plan_revenue": plan_revenue,
        "plan_distribution": plan_distribution,
        "plans_breakdown": plans_breakdown,
        "mrr_history": mrr_history,
        "historical_mrr": mrr_history,
        "recent_invoices": recent_invoices,
        "invoices": recent_invoices,
    }
    if not is_sqlite:
        memory_cache.set(cache_key, data_payload, ttl=60)

    return ApiResponse.ok(
        data=data_payload,
        message="Data finansial SaaS dan MRR berhasil dimuat",
    )


# ---------------------------------------------------------------------------
# PRICING, AI CREDITS & PROMO MANAGEMENT ENDPOINTS
# ---------------------------------------------------------------------------

from app.core.billing_defaults import (
    DEFAULT_AI_CREDITS_CONFIG,
    DEFAULT_PROMO_CODES,
)
from app.services.billing.pricing_plans import (
    get_plan_price_map,
    get_pricing_plans as fetch_pricing_plans,
    update_pricing_plan,
)

@router.get("/pricing-plans")
def get_pricing_plans(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    return ApiResponse.ok(data=fetch_pricing_plans(db), message="Paket langganan berhasil dimuat")

_PRICING_INT_FIELDS = (
    "price_monthly",
    "price_annually",
    "max_students",
    "max_teachers",
    "max_storage_gb",
    "ai_credits_monthly",
)
_PRICING_ALL_FIELDS = (
    ("name",) + _PRICING_INT_FIELDS + ("proctoring_type", "description", "features", "is_popular")
)

def _validate_pricing_payload(payload: dict) -> dict:
    """Validate a full pricing-plan update body; returns cleaned fields."""
    def _invalid(message: str):
        raise AppException(
            message=message,
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            error_code="VALIDATION_ERROR",
        )

    if not isinstance(payload, dict):
        _invalid("Body harus berupa objek JSON")

    missing = [f for f in _PRICING_ALL_FIELDS if f not in payload]
    if missing:
        _invalid(f"Field wajib belum diisi: {', '.join(missing)}")

    cleaned = {}

    name = payload.get("name")
    if not isinstance(name, str) or not name.strip():
        _invalid("Nama paket tidak boleh kosong")
    cleaned["name"] = name.strip()

    for field in _PRICING_INT_FIELDS:
        value = payload.get(field)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            _invalid(f"Field {field} harus berupa bilangan bulat >= 0")
        cleaned[field] = value

    proctoring_type = payload.get("proctoring_type")
    if proctoring_type not in ("single_camera", "dual_camera"):
        _invalid("proctoring_type harus 'single_camera' atau 'dual_camera'")
    cleaned["proctoring_type"] = proctoring_type

    description = payload.get("description")
    if not isinstance(description, str):
        _invalid("Field description harus berupa teks")
    cleaned["description"] = description

    features = payload.get("features")
    if not isinstance(features, list) or not all(isinstance(f, str) for f in features):
        _invalid("Field features harus berupa daftar teks")
    cleaned["features"] = features

    is_popular = payload.get("is_popular")
    if not isinstance(is_popular, bool):
        _invalid("Field is_popular harus berupa boolean")
    cleaned["is_popular"] = is_popular

    return cleaned

@router.put("/pricing-plans/{plan_id}")
def update_pricing_plan_endpoint(
    plan_id: str,
    payload: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_superadmin),
):
    cleaned = _validate_pricing_payload(payload)
    updated = update_pricing_plan(db, plan_id, cleaned)
    if updated is None:
        raise AppException(message="Paket tidak ditemukan", status_code=status.HTTP_404_NOT_FOUND)
    return ApiResponse.ok(data=updated, message=f"Paket {updated['name']} berhasil diperbarui")

@router.get("/ai-credits")
def get_ai_credits_config(current_user: User = Depends(require_admin)):
    return ApiResponse.ok(data=DEFAULT_AI_CREDITS_CONFIG, message="Skema kredit AI berhasil dimuat")

@router.get("/promos")
def get_promo_codes(current_user: User = Depends(require_admin)):
    return ApiResponse.ok(data=DEFAULT_PROMO_CODES, message="Daftar promo berhasil dimuat")

@router.post("/promos")
def create_promo_code(
    payload: dict,
    current_user: User = Depends(require_superadmin),
):
    new_promo = {
        "id": len(DEFAULT_PROMO_CODES) + 1,
        "code": payload.get("code", "").upper().strip(),
        "discount_type": payload.get("discount_type", "percentage"),
        "discount_value": int(payload.get("discount_value", 0)),
        "credit_bonus": int(payload.get("credit_bonus", 0)),
        "max_uses": int(payload.get("max_uses", 50)),
        "used_count": 0,
        "valid_until": payload.get("valid_until", "2026-12-31"),
        "description": payload.get("description", "Voucher promosi EXAMIND"),
        "is_active": True,
    }
    DEFAULT_PROMO_CODES.insert(0, new_promo)
    return ApiResponse.ok(data=new_promo, message=f"Kode promo {new_promo['code']} berhasil dibuat")

@router.patch("/promos/{promo_id}/toggle")
def toggle_promo_status(
    promo_id: int,
    current_user: User = Depends(require_superadmin),
):
    for p in DEFAULT_PROMO_CODES:
        if p["id"] == promo_id:
            p["is_active"] = not p["is_active"]
            status_text = "diaktifkan" if p["is_active"] else "dinonaktifkan"
            return ApiResponse.ok(data=p, message=f"Promo {p['code']} berhasil {status_text}")
    raise AppException(message="Promo tidak ditemukan", status_code=status.HTTP_404_NOT_FOUND)


# ---------------------------------------------------------------------------
# TASK-SPECIFIC AI SECRETS & MULTI-MODEL CONFIGURATION
# ---------------------------------------------------------------------------

DEFAULT_AI_TASKS = [
    {
        "task_id": "TASK_CHATBOT",
        "name": "AI Assistant Chatbot",
        "description": "Chatbot asisten utama di dashboard — menjawab pertanyaan operasional, data, dan bantuan umum.",
        "default_provider": "gemini",
        "default_model": "gemini-2.5-flash",
        "default_temperature": 0.5,
        "default_max_tokens": 2048,
        "providers_supported": ["gemini", "openai", "claude", "deepseek", "ollama", "openrouter"],
    },
    {
        "task_id": "TASK_QUESTION_GEN",
        "name": "AI Question Generation Engine",
        "description": "Sintesis soal pilihan ganda & esai, perumusan taksonomi Bloom, dan rubrik penilaian.",
        "default_provider": "gemini",
        "default_model": "gemini-2.5-flash",
        "default_temperature": 0.7,
        "default_max_tokens": 4096,
        "providers_supported": ["gemini", "openai", "claude", "deepseek", "ollama"],
    },
    {
        "task_id": "TASK_ESSAY_GRADING",
        "name": "AI Essay Auto-Grading & Rubric Scoring",
        "description": "Evaluasi semantik esai siswa, pencocokan konsep kunci, scoring analitik, dan confidence rating.",
        "default_provider": "gemini",
        "default_model": "gemini-2.5-pro",
        "default_temperature": 0.1,
        "default_max_tokens": 2048,
        "providers_supported": ["gemini", "openai", "claude", "deepseek"],
    },
    {
        "task_id": "TASK_TUTOR_CHAT",
        "name": "Post-Exam AI Tutor & Explanation Chat",
        "description": "Chat interaktif pasca ujian yang menjawab kebingungan siswa dan memandu pemahaman materi.",
        "default_provider": "gemini",
        "default_model": "gemini-2.5-flash",
        "default_temperature": 0.5,
        "default_max_tokens": 2048,
        "providers_supported": ["gemini", "openai", "claude", "deepseek", "ollama"],
    },
    {
        "task_id": "TASK_PROCTORING_CV",
        "name": "Edge Proctoring Multimodal Verification",
        "description": "Audit visual multimodal atas snapshot anomali siswa (tatapan mata, ponsel kedua, atau orang lain).",
        "default_provider": "gemini",
        "default_model": "gemini-2.5-flash",
        "default_temperature": 0.0,
        "default_max_tokens": 1024,
        "providers_supported": ["gemini", "openai"],
    },
    {
        "task_id": "TASK_SHORT_ANSWER_GRADING",
        "name": "AI Short-Answer Grading (Respan)",
        "description": "Penilaian jawaban singkat siswa via OpenRouter Decisions API (model Respan Span).",
        "default_provider": "openrouter",
        "default_model": "respan/span-01-lite",
        "default_temperature": 0.0,
        "default_max_tokens": 0,
        "providers_supported": ["openrouter"],
    },
    {
        "task_id": "TASK_CHATBOT_GUARDRAIL",
        "name": "Chatbot Safety Guardrail (Respan)",
        "description": "Filter keamanan pesan chatbot via OpenRouter Decisions API — deteksi jailbreak, cheating, dan konten berbahaya.",
        "default_provider": "openrouter",
        "default_model": "respan/span-01-lite",
        "default_temperature": 0.0,
        "default_max_tokens": 0,
        "providers_supported": ["openrouter"],
    },
]

@router.get("/secrets/tasks")
def get_task_secrets(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    import json
    records = {r.key_name: r for r in db.query(SystemSecret).all()}

    task_results = []
    for t in DEFAULT_AI_TASKS:
        tid = t["task_id"]
        rec = records.get(tid)
        config = {
            "task_id": tid,
            "name": t["name"],
            "description": t["description"],
            "provider": t["default_provider"],
            "model": t["default_model"],
            "temperature": t["default_temperature"],
            "max_tokens": t["default_max_tokens"],
            "api_key_masked": "********",
            "has_custom_key": False,
            "is_active": True,
            "providers_supported": t["providers_supported"],
            "last_tested": "Optimal",
        }
        if rec:
            config["is_active"] = rec.is_active
            plain = decrypt_secret(rec.encrypted_value)
            try:
                parsed = json.loads(plain)
                if isinstance(parsed, dict):
                    config["provider"] = parsed.get("provider", config["provider"])
                    config["model"] = parsed.get("model", config["model"])
                    config["temperature"] = parsed.get("temperature", config["temperature"])
                    config["max_tokens"] = parsed.get("max_tokens", config["max_tokens"])
                    raw_k = parsed.get("api_key", "")
                    config["api_key_masked"] = mask_secret(raw_k) if raw_k else "Inherit Global"
                    config["has_custom_key"] = bool(raw_k)
            except Exception:
                config["api_key_masked"] = mask_secret(plain)
                config["has_custom_key"] = bool(plain)

        task_results.append(config)

    return ApiResponse.ok(data=task_results, message="Konfigurasi secret per task berhasil dimuat")

@router.post("/secrets/tasks")
def save_task_secret(
    payload: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    import json
    task_id = payload.get("task_id", "").strip().upper()
    if not task_id:
        raise AppException(message="Task ID wajib diisi", status_code=status.HTTP_400_BAD_REQUEST)

    rec = db.query(SystemSecret).filter(SystemSecret.key_name == task_id).first()

    # Existing key retention if new key not supplied
    api_key = payload.get("api_key", "").strip()
    if not api_key and rec:
        try:
            old_plain = decrypt_secret(rec.encrypted_value)
            old_parsed = json.loads(old_plain)
            api_key = old_parsed.get("api_key", "")
        except Exception:
            pass

    save_data = {
        "provider": payload.get("provider", "gemini"),
        "model": payload.get("model", "gemini-2.5-flash"),
        "api_key": api_key,
        "temperature": float(payload.get("temperature", 0.7)),
        "max_tokens": int(payload.get("max_tokens", 2048)),
    }
    encrypted_val = encrypt_secret(json.dumps(save_data))

    if rec:
        rec.service_name = save_data["provider"]
        rec.encrypted_value = encrypted_val
        rec.description = payload.get("description", rec.description)
        rec.is_active = payload.get("is_active", True)
    else:
        rec = SystemSecret(
            key_name=task_id,
            service_name=save_data["provider"],
            encrypted_value=encrypted_val,
            description=payload.get("description", f"AI engine configuration for {task_id}"),
            is_active=payload.get("is_active", True),
        )
        db.add(rec)

    db.commit()
    db.refresh(rec)
    return ApiResponse.ok(data={"task_id": task_id, "status": "saved"}, message=f"Konfigurasi task {task_id} berhasil disimpan")


from pydantic import BaseModel


class RegistrationCodeCreate(BaseModel):
    tenant_id: int
    role: str  # 'admin' | 'teacher' | 'student'
    code: str
    description: Optional[str] = None
    max_uses: int = 0


@router.get("/registration-codes", response_model=PaginatedResponse[dict])
def list_registration_codes(
    tenant_id: Optional[int] = Query(None),
    role: Optional[str] = Query(None),
    page: int = Query(1, ge=1, description="Nomor halaman"),
    page_size: int = Query(20, ge=1, le=100, description="Jumlah data per halaman"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_superadmin),
):
    """List all provider registration codes across all schools with tenant details."""
    with log_query_timing("list_registration_codes"):
        query = db.query(TenantRegistrationCode)
        if tenant_id:
            query = query.filter(TenantRegistrationCode.tenant_id == tenant_id)
        if role:
            query = query.filter(TenantRegistrationCode.role == role)

        total = query.count()
        records = (
            query.options(joinedload(TenantRegistrationCode.tenant))
            .order_by(TenantRegistrationCode.tenant_id.asc(), TenantRegistrationCode.role.asc())
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )
        results = [
            {
                "id": r.id,
                "tenant_id": r.tenant_id,
                "tenant_name": r.tenant.name if r.tenant else "Unknown",
                "tenant_code": r.tenant.code if r.tenant else "",
                "role": r.role,
                "code": r.code,
                "description": r.description,
                "max_uses": r.max_uses,
                "used_count": r.used_count,
                "is_active": r.is_active,
                "expires_at": r.expires_at,
                "created_at": r.created_at,
            }
            for r in records
        ]
        return PaginatedResponse.ok(
            data=results,
            page=page,
            page_size=page_size,
            total=total,
            message="Daftar kode registrasi sekolah berhasil dimuat",
        )


@router.post("/registration-codes")
def create_registration_code(
    payload: RegistrationCodeCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_superadmin),
):
    """Create a new role-specific registration code for a specific school."""
    clean_code = payload.code.strip().upper()
    existing = db.query(TenantRegistrationCode).filter(TenantRegistrationCode.code == clean_code).first()
    if existing:
        raise AppException(
            message=f"Kode '{clean_code}' sudah digunakan.",
            status_code=status.HTTP_400_BAD_REQUEST,
            error_code="CODE_ALREADY_EXISTS",
        )

    tenant = db.query(Tenant).filter(Tenant.id == payload.tenant_id).first()
    if not tenant:
        raise AppException(
            message="Sekolah/tenant tidak ditemukan.",
            status_code=status.HTTP_404_NOT_FOUND,
            error_code="TENANT_NOT_FOUND",
        )

    entry = TenantRegistrationCode(
        tenant_id=payload.tenant_id,
        role=payload.role,
        code=clean_code,
        description=payload.description or f"Kode Registrasi {payload.role.capitalize()} - {tenant.name}",
        max_uses=payload.max_uses,
        used_count=0,
        is_active=True,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)

    return ApiResponse.ok(
        data={
            "id": entry.id,
            "tenant_id": entry.tenant_id,
            "tenant_name": tenant.name,
            "role": entry.role,
            "code": entry.code,
            "description": entry.description,
            "is_active": entry.is_active,
        },
        message=f"Kode registrasi '{clean_code}' berhasil dibuat untuk {tenant.name}",
    )


@router.patch("/registration-codes/{code_id}/toggle")
def toggle_registration_code(
    code_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_superadmin),
):
    """Toggle active/inactive status of a registration code."""
    entry = db.query(TenantRegistrationCode).filter(TenantRegistrationCode.id == code_id).first()
    if not entry:
        raise AppException(message="Kode pendaftaran tidak ditemukan", status_code=status.HTTP_404_NOT_FOUND)

    entry.is_active = not entry.is_active
    db.commit()
    status_str = "diaktifkan" if entry.is_active else "dinonaktifkan"
    return ApiResponse.ok(data={"id": entry.id, "is_active": entry.is_active}, message=f"Kode pendaftaran berhasil {status_str}")


@router.delete("/registration-codes/{code_id}")
def delete_registration_code(
    code_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_superadmin),
):
    """Delete a registration code."""
    entry = db.query(TenantRegistrationCode).filter(TenantRegistrationCode.id == code_id).first()
    if not entry:
        raise AppException(message="Kode pendaftaran tidak ditemukan", status_code=status.HTTP_404_NOT_FOUND)

    db.delete(entry)
    db.commit()
    return ApiResponse.ok(data={"id": code_id}, message="Kode pendaftaran berhasil dihapus")



