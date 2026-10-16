import time
import httpx
from typing import List, Optional
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import func
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.exceptions import AppException
from app.core.dependencies import require_superadmin, require_admin
from app.core.security import get_password_hash
from app.core.secret_manager import encrypt_secret, decrypt_secret, mask_secret, get_secret
from app.models.tenant import Tenant
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
from app.schemas.common import ApiResponse

router = APIRouter(prefix="/superadmin", tags=["SaaS & Platform Super Admin"])


@router.get("/stats", response_model=ApiResponse[SuperAdminStatsResponse])
def get_superadmin_global_stats(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_superadmin),
):
    tenants = db.query(Tenant).all()
    total_tenants = len(tenants)
    active_tenants = sum(1 for t in tenants if t.is_active)

    plan_counts = {"starter": 0, "pro": 0, "enterprise": 0}
    total_ai_credits = 0
    for t in tenants:
        plan_counts[t.subscription_plan] = plan_counts.get(t.subscription_plan, 0) + 1
        total_ai_credits += int(t.ai_credits_used or 0)

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
    return ApiResponse.ok(data=stats, message="Statistik global SaaS berhasil dimuat")


@router.get("/tenants", response_model=ApiResponse[List[TenantResponse]])
def get_all_tenants(
    search: Optional[str] = Query(None, description="Cari nama atau kode sekolah"),
    plan: Optional[str] = Query(None, description="Filter paket: starter, pro, enterprise"),
    subscription_status: Optional[str] = Query(None, description="Filter status langganan"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_superadmin),
):
    query = db.query(Tenant)
    if search:
        kw = f"%{search}%"
        query = query.filter((Tenant.name.ilike(kw)) | (Tenant.code.ilike(kw)))
    if plan:
        query = query.filter(Tenant.subscription_plan == plan)
    if subscription_status:
        query = query.filter(Tenant.subscription_status == subscription_status)

    tenants = query.order_by(Tenant.created_at.desc()).all()

    # Pre-aggregate user counts per tenant in single SQL query (O(1) roundtrip)
    user_counts = (
        db.query(User.tenant_id, User.role, func.count(User.id))
        .filter(User.tenant_id.isnot(None))
        .group_by(User.tenant_id, User.role)
        .all()
    )
    user_stats = {}
    for tid, role, cnt in user_counts:
        if tid not in user_stats:
            user_stats[tid] = {"student": 0, "teacher": 0, "total": 0}
        user_stats[tid][role] = cnt
        user_stats[tid]["total"] += cnt

    # Pre-aggregate exam counts per tenant in single SQL query
    exam_counts = (
        db.query(User.tenant_id, func.count(Exam.id))
        .join(User, Exam.teacher_id == User.id)
        .filter(User.tenant_id.isnot(None))
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
            created_at=t.created_at,
            total_users=t_user_stat["total"],
            total_students=t_user_stat["student"],
            total_teachers=t_user_stat["teacher"],
            total_exams=t_exams,
        )
        result.append(res_item)

    return ApiResponse.ok(data=result, message="Daftar tenant sekolah berhasil dimuat")


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

