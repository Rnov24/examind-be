import os
import re
import base64
import secrets
import string
import logging
import httpx
from app.core.config import settings

# Strip bracketed IPv6 literals in NO_PROXY to prevent httpx InvalidURL parsing error
for _var in ("NO_PROXY", "no_proxy"):
    _val = os.environ.get(_var)
    if _val and "[" in _val:
        os.environ[_var] = re.sub(r"\[([0-9a-fA-F:]+)\]", r"\1", _val)

logger = logging.getLogger("examind.resend")
RESEND_API_ENDPOINT = "https://api.resend.com/emails"


def generate_otp(length: int = 6) -> str:
    """Generate a cryptographically secure numeric OTP."""
    digits = string.digits
    return "".join(secrets.choice(digits) for _ in range(length))


def _email_shell(title: str, body_html: str) -> str:
    """Shared single-column, table-based responsive email shell adhering to EXAMIND precision palette."""
    return f"""<!DOCTYPE html>
<html lang="id">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{title}</title>
</head>
<body style="margin: 0; padding: 0; background-color: #f4f4f5; font-family: -apple-system, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; -webkit-font-smoothing: antialiased; color: #18181b;">
  <table role="presentation" border="0" cellpadding="0" cellspacing="0" width="100%" style="background-color: #f4f4f5; padding: 32px 12px;">
    <tr>
      <td align="center">
        <table role="presentation" border="0" cellpadding="0" cellspacing="0" width="100%" style="max-width: 600px; background-color: #ffffff; border-radius: 8px; border: 1px solid #e4e4e7; overflow: hidden;">
          <!-- Midnight-Violet Header Band with Lime Accent Rule -->
          <tr>
            <td style="background-color: #150f23; padding: 24px 32px; text-align: left;">
              <table role="presentation" border="0" cellpadding="0" cellspacing="0">
                <tr>
                  <td>
                    <span style="font-size: 20px; font-weight: 800; letter-spacing: 0.05em; color: #ffffff; text-transform: uppercase;">EXAMIND</span>
                  </td>
                </tr>
                <tr>
                  <td style="padding-top: 6px;">
                    <div style="height: 3px; width: 36px; background-color: #c2ef4e; line-height: 3px; font-size: 0;">&nbsp;</div>
                  </td>
                </tr>
              </table>
            </td>
          </tr>
          <!-- Body -->
          <tr>
            <td style="padding: 32px; background-color: #ffffff; color: #18181b; font-size: 14px; line-height: 1.6;">
              {body_html}
            </td>
          </tr>
          <!-- Footer -->
          <tr>
            <td style="padding: 24px 32px; background-color: #fafafa; border-top: 1px solid #f4f4f5; text-align: center;">
              <p style="margin: 0; font-size: 12px; color: #71717a; line-height: 1.5;">&copy; 2026 EXAMIND. Sistem Ujian &amp; Evaluasi Akademik Berbasis AI.</p>
              <p style="margin: 4px 0 0 0; font-size: 11px; color: #a1a1aa; line-height: 1.4;">Email transaksional otomatis. Harap tidak membalas email ini.</p>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""


def render_otp_html(otp_code: str, purpose: str = "email_verification", expires_in_minutes: int = 10) -> str:
    """Render a branded, responsive HTML template for EXAMIND OTP emails."""
    purpose_title = "Verifikasi Alamat Email" if purpose == "email_verification" else "Kode Keamanan Akun"
    purpose_desc = (
        "Gunakan kode verifikasi berikut untuk mengonfirmasi alamat email akun EXAMIND Anda:"
        if purpose == "email_verification"
        else "Gunakan kode otorisasi berikut untuk verifikasi keamanan akun EXAMIND Anda:"
    )

    body_html = f"""<h1 style="margin: 0 0 12px 0; font-size: 20px; font-weight: 700; color: #150f23;">{purpose_title}</h1>
<p style="margin: 0 0 20px 0; font-size: 14px; line-height: 1.6; color: #3f3f46;">{purpose_desc}</p>

<table role="presentation" border="0" cellpadding="0" cellspacing="0" width="100%" style="margin: 24px 0;">
  <tr>
    <td align="center" style="background-color: #ede9fe; border-radius: 6px; padding: 20px; border: 1px solid #ddd6fe;">
      <div style="font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.08em; color: #6a5fc1; margin-bottom: 8px;">Kode Verifikasi OTP</div>
      <div style="font-family: ui-monospace, 'SFMono-Regular', Menlo, Monaco, Consolas, 'Liberation Mono', 'Courier New', monospace; font-size: 36px; font-weight: 700; letter-spacing: 8px; color: #6a5fc1; line-height: 1;">{otp_code}</div>
      <div style="font-size: 12px; color: #52525b; margin-top: 8px;">Berlaku selama {expires_in_minutes} menit</div>
    </td>
  </tr>
</table>

<p style="margin: 0 0 12px 0; font-size: 13px; line-height: 1.5; color: #71717a;">
  Jangan bagikan kode ini kepada siapa pun. Tim EXAMIND tidak akan pernah meminta kode verifikasi Anda.
</p>
<p style="margin: 16px 0 0 0; font-size: 12px; line-height: 1.5; color: #a1a1aa; border-top: 1px solid #f4f4f5; padding-top: 16px;">
  Jika Anda tidak merasa melakukan permintaan ini, abaikan pesan ini.
</p>"""

    return _email_shell(title=f"{purpose_title} - EXAMIND", body_html=body_html)


def render_password_reset_html(
    user_name: str,
    reset_url: str,
    token_code: str,
    expires_in_minutes: int = 15,
) -> str:
    """Render high-aesthetic, branded HTML template for EXAMIND Password Reset."""
    display_name = user_name.strip() if user_name else "Pengguna EXAMIND"

    body_html = f"""<h1 style="margin: 0 0 12px 0; font-size: 20px; font-weight: 700; color: #150f23;">Atur Ulang Kata Sandi</h1>
<p style="margin: 0 0 16px 0; font-size: 14px; line-height: 1.6; color: #3f3f46;">
  Halo <strong>{display_name}</strong>, kami menerima permintaan untuk mengatur ulang kata sandi akun EXAMIND Anda.
</p>
<p style="margin: 0 0 20px 0; font-size: 14px; line-height: 1.6; color: #3f3f46;">
  Klik tautan di bawah ini untuk membuat kata sandi baru:
</p>

<table role="presentation" border="0" cellpadding="0" cellspacing="0" style="margin: 24px 0;">
  <tr>
    <td align="center" style="background-color: #150f23; border-radius: 6px;">
      <a href="{reset_url}" target="_blank" style="display: inline-block; padding: 12px 24px; font-size: 14px; font-weight: 600; color: #ffffff; text-decoration: none;">Atur Ulang Kata Sandi</a>
    </td>
  </tr>
</table>

<table role="presentation" border="0" cellpadding="0" cellspacing="0" width="100%" style="margin: 24px 0;">
  <tr>
    <td align="center" style="background-color: #ede9fe; border-radius: 6px; padding: 16px; border: 1px solid #ddd6fe;">
      <div style="font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.08em; color: #6a5fc1; margin-bottom: 6px;">Atau Masukkan Kode Secara Manual:</div>
      <div style="font-family: ui-monospace, 'SFMono-Regular', Menlo, Monaco, Consolas, 'Liberation Mono', 'Courier New', monospace; font-size: 28px; font-weight: 700; letter-spacing: 6px; color: #6a5fc1; line-height: 1;">{token_code}</div>
      <div style="font-size: 12px; color: #52525b; margin-top: 6px;">Berlaku selama {expires_in_minutes} menit</div>
    </td>
  </tr>
</table>

<p style="margin: 16px 0 6px 0; font-size: 12px; color: #71717a;">
  Tautan alternatif jika tombol di atas tidak dapat diklik:
</p>
<div style="background-color: #f4f4f5; padding: 10px 12px; border-radius: 6px; font-family: ui-monospace, 'SFMono-Regular', Menlo, Monaco, Consolas, monospace; font-size: 11px; color: #52525b; word-break: break-all; border: 1px solid #e4e4e7;">
  {reset_url}
</div>

<p style="margin: 20px 0 0 0; font-size: 12px; line-height: 1.5; color: #a1a1aa; border-top: 1px solid #f4f4f5; padding-top: 16px;">
  Jika Anda tidak merasa melakukan permintaan ini, abaikan email ini. Kata sandi lama Anda tetap aman dan tidak akan berubah.
</p>"""

    return _email_shell(title="Atur Ulang Kata Sandi - EXAMIND", body_html=body_html)


def render_password_reset_success_html(user_name: str) -> str:
    """Render notification confirming password has been successfully reset."""
    display_name = user_name.strip() if user_name else "Pengguna EXAMIND"

    body_html = f"""<h1 style="margin: 0 0 12px 0; font-size: 20px; font-weight: 700; color: #150f23;">Kata Sandi Berhasil Diperbarui</h1>
<p style="margin: 0 0 16px 0; font-size: 14px; line-height: 1.6; color: #3f3f46;">
  Halo <strong>{display_name}</strong>,
</p>
<p style="margin: 0 0 16px 0; font-size: 14px; line-height: 1.6; color: #3f3f46;">
  Kata sandi akun EXAMIND Anda telah berhasil diperbarui. Anda kini dapat masuk kembali ke sistem menggunakan kata sandi baru Anda.
</p>
<p style="margin: 20px 0 0 0; font-size: 12px; line-height: 1.5; color: #a1a1aa; border-top: 1px solid #f4f4f5; padding-top: 16px;">
  Jika Anda tidak merasa melakukan pembaruan ini, segera hubungi administrator sekolah untuk mengamankan akun Anda.
</p>"""

    return _email_shell(title="Kata Sandi Berhasil Diperbarui - EXAMIND", body_html=body_html)


def render_exam_result_html(
    student_name: str,
    exam_title: str,
    score: float | int | str,
    grade_predicate: str | None = None,
    correct_count: int = 0,
    wrong_count: int = 0,
    unanswered_count: int = 0,
    summary_counts: dict | None = None,
    platform_url: str | None = None,
) -> str:
    """Render branded email reporting exam result with attached PDF notification."""
    display_name = student_name.strip() if student_name else "Siswa"
    clean_exam_title = exam_title.strip() if exam_title else "Ujian"

    if summary_counts:
        correct_count = summary_counts.get("correct", summary_counts.get("correct_count", correct_count))
        wrong_count = summary_counts.get("wrong", summary_counts.get("wrong_count", wrong_count))
        unanswered_count = summary_counts.get("unanswered", summary_counts.get("unanswered_count", unanswered_count))

    try:
        score_num = float(score)
        formatted_score = f"{score_num:.1f}" if score_num % 1 != 0 else f"{int(score_num)}"
    except (ValueError, TypeError):
        formatted_score = str(score)

    portal_url = platform_url or getattr(settings, "FRONTEND_URL", "http://localhost:3000")

    predicate_badge = ""
    if grade_predicate and str(grade_predicate).strip():
        predicate_badge = f"""<div style="margin-top: 12px;">
  <span style="display: inline-block; padding: 4px 12px; border-radius: 4px; background-color: #c2ef4e; color: #150f23; font-size: 12px; font-weight: 700; letter-spacing: 0.04em; text-transform: uppercase;">
    {str(grade_predicate).strip()}
  </span>
</div>"""

    body_html = f"""<h1 style="margin: 0 0 8px 0; font-size: 20px; font-weight: 700; color: #150f23;">Hasil Evaluasi Ujian</h1>
<p style="margin: 0 0 16px 0; font-size: 14px; line-height: 1.6; color: #3f3f46;">
  Halo <strong>{display_name}</strong>, proses penilaian untuk ujian <strong>{clean_exam_title}</strong> telah selesai. Berikut adalah ringkasan hasil yang Anda peroleh:
</p>

<!-- Score Card -->
<table role="presentation" border="0" cellpadding="0" cellspacing="0" width="100%" style="margin: 20px 0;">
  <tr>
    <td align="center" style="background-color: #150f23; border-radius: 8px; padding: 24px; text-align: center;">
      <div style="font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.08em; color: #a1a1aa; margin-bottom: 6px;">Nilai Akhir</div>
      <div style="font-size: 48px; font-weight: 800; color: #c2ef4e; line-height: 1; letter-spacing: -0.02em;">{formatted_score}</div>
      {predicate_badge}
    </td>
  </tr>
</table>

<!-- Section Summary Table -->
<div style="font-size: 12px; font-weight: 600; color: #52525b; text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 8px;">Ringkasan Soal Pilihan Ganda</div>
<table role="presentation" border="0" cellpadding="0" cellspacing="0" width="100%" style="margin-bottom: 24px; border: 1px solid #e4e4e7; border-radius: 6px; overflow: hidden;">
  <tr>
    <td align="center" style="padding: 12px; background-color: #fafafa; border-right: 1px solid #e4e4e7; width: 33%;">
      <div style="font-size: 11px; font-weight: 600; text-transform: uppercase; color: #71717a; letter-spacing: 0.05em;">Benar</div>
      <div style="font-size: 18px; font-weight: 700; color: #15803d; margin-top: 4px;">{correct_count}</div>
    </td>
    <td align="center" style="padding: 12px; background-color: #fafafa; border-right: 1px solid #e4e4e7; width: 33%;">
      <div style="font-size: 11px; font-weight: 600; text-transform: uppercase; color: #71717a; letter-spacing: 0.05em;">Salah</div>
      <div style="font-size: 18px; font-weight: 700; color: #b91c1c; margin-top: 4px;">{wrong_count}</div>
    </td>
    <td align="center" style="padding: 12px; background-color: #fafafa; width: 34%;">
      <div style="font-size: 11px; font-weight: 600; text-transform: uppercase; color: #71717a; letter-spacing: 0.05em;">Kosong</div>
      <div style="font-size: 18px; font-weight: 700; color: #71717a; margin-top: 4px;">{unanswered_count}</div>
    </td>
  </tr>
</table>

<p style="margin: 0 0 12px 0; font-size: 13px; line-height: 1.5; color: #3f3f46;">
  Laporan evaluasi lengkap beserta rincian lembar jawaban siswa telah dilampirkan dalam berkas PDF pada email ini.
</p>
<p style="margin: 0; font-size: 12px; line-height: 1.5; color: #71717a; border-top: 1px solid #f4f4f5; padding-top: 16px;">
  Anda juga dapat meninjau rincian hasil ujian melalui portal EXAMIND di <a href="{portal_url}" target="_blank" style="color: #6a5fc1; text-decoration: underline;">{portal_url}</a>.
</p>"""

    return _email_shell(title=f"Hasil Ujian: {clean_exam_title} - EXAMIND", body_html=body_html)


async def send_email_via_resend(
    to_email: str,
    subject: str,
    html_content: str,
    attachments: list[dict] | None = None,
) -> dict:
    """Send transactional email using Resend API with local mock fallback."""
    from app.core.secret_manager import get_secret

    api_key = get_secret("RESEND_API_KEY") or (settings.RESEND_API_KEY.strip() if settings.RESEND_API_KEY else "")
    from_email = get_secret("RESEND_FROM_EMAIL") or settings.RESEND_FROM_EMAIL

    # Mock fallback for development or test environments without API keys
    if not api_key:
        logger.info(f"[RESEND MOCK] No RESEND_API_KEY configured. Mock sending to: {to_email} | Subject: '{subject}'")
        return {
            "id": f"mock_resend_{secrets.token_hex(8)}",
            "from": from_email,
            "to": [to_email],
            "status": "mock_sent",
            "mock": True
        }

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "from": from_email,
        "to": [to_email],
        "subject": subject,
        "html": html_content,
    }
    if attachments:
        payload["attachments"] = attachments

    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            response = await client.post(RESEND_API_ENDPOINT, json=payload, headers=headers)
            if response.is_success:
                return response.json()
            else:
                logger.error(f"[RESEND ERROR] Status {response.status_code}: {response.text}")
                return {
                    "error": True,
                    "status_code": response.status_code,
                    "details": response.text
                }
        except Exception as e:
            logger.error(f"[RESEND EXCEPTION] Failed to connect to Resend API: {e}")
            return {
                "error": True,
                "message": str(e)
            }


async def send_otp_email(to_email: str, otp_code: str, purpose: str = "email_verification", expires_in_minutes: int = 10) -> dict:
    """Helper to render template and dispatch OTP email via Resend."""
    subject = f"[{otp_code}] Kode Verifikasi EXAMIND"
    html_content = render_otp_html(otp_code=otp_code, purpose=purpose, expires_in_minutes=expires_in_minutes)
    return await send_email_via_resend(to_email=to_email, subject=subject, html_content=html_content)


async def send_password_reset_email(
    to_email: str,
    user_name: str,
    reset_url: str,
    token_code: str,
    expires_in_minutes: int = 15,
) -> dict:
    """Helper to dispatch branded password reset email via Resend API."""
    subject = f"[{token_code}] Atur Ulang Kata Sandi Akun EXAMIND"
    html_content = render_password_reset_html(
        user_name=user_name,
        reset_url=reset_url,
        token_code=token_code,
        expires_in_minutes=expires_in_minutes,
    )
    return await send_email_via_resend(to_email=to_email, subject=subject, html_content=html_content)


async def send_password_reset_success_email(to_email: str, user_name: str) -> dict:
    """Helper to dispatch password changed confirmation via Resend API."""
    subject = "Keamanan Akun: Kata Sandi EXAMIND Berhasil Diperbarui"
    html_content = render_password_reset_success_html(user_name=user_name)
    return await send_email_via_resend(to_email=to_email, subject=subject, html_content=html_content)


async def send_exam_result_email(
    to_email: str,
    student_name: str,
    exam_title: str,
    score: float | int | str,
    pdf_bytes: bytes,
    pdf_filename: str,
    grade_predicate: str | None = None,
    summary_counts: dict | None = None,
    platform_url: str | None = None,
) -> dict:
    """Helper to render exam result email with attached PDF and dispatch via Resend."""
    subject = f"Hasil Ujian: {exam_title}"
    html_content = render_exam_result_html(
        student_name=student_name,
        exam_title=exam_title,
        score=score,
        grade_predicate=grade_predicate,
        summary_counts=summary_counts,
        platform_url=platform_url,
    )
    pdf_base64 = base64.b64encode(pdf_bytes).decode("utf-8")
    attachments = [
        {
            "content": pdf_base64,
            "filename": pdf_filename,
        }
    ]
    return await send_email_via_resend(
        to_email=to_email,
        subject=subject,
        html_content=html_content,
        attachments=attachments,
    )

