import secrets
import string
import logging
import httpx
from app.core.config import settings

logger = logging.getLogger("examind.resend")
RESEND_API_ENDPOINT = "https://api.resend.com/emails"


def generate_otp(length: int = 6) -> str:
    """Generate a cryptographically secure numeric OTP."""
    digits = string.digits
    return "".join(secrets.choice(digits) for _ in range(length))


def render_otp_html(otp_code: str, purpose: str = "email_verification", expires_in_minutes: int = 10) -> str:
    """Render a branded, responsive HTML template for EXAMIND OTP emails."""
    purpose_title = "Verifikasi Alamat Email" if purpose == "email_verification" else "Permintaan Kode Keamanan"
    purpose_desc = (
        "Terima kasih telah bergabung dengan platform ujian online EXAMIND. Masukkan kode verifikasi berikut untuk mengonfirmasi email akun Anda:"
        if purpose == "email_verification"
        else "Gunakan kode otorisasi berikut untuk memproses verifikasi keamanan akun EXAMIND Anda:"
    )

    return f"""<!DOCTYPE html>
<html lang="id">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{purpose_title}</title>
</head>
<body style="margin: 0; padding: 0; background-color: #0f172a; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; color: #f8fafc;">
  <table role="presentation" border="0" cellpadding="0" cellspacing="0" width="100%" style="background-color: #0f172a; padding: 40px 10px;">
    <tr>
      <td align="center">
        <table role="presentation" border="0" cellpadding="0" cellspacing="0" width="100%" style="max-width: 520px; background-color: #1e293b; border-radius: 16px; border: 1px solid #334155; overflow: hidden; box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.4);">
          <!-- Header -->
          <tr>
            <td style="padding: 32px 32px 20px 32px; text-align: center; border-bottom: 1px solid #334155;">
              <h1 style="margin: 0; font-size: 26px; font-weight: 800; letter-spacing: -0.03em; color: #38bdf8;">EXAMIND</h1>
              <p style="margin: 4px 0 0 0; font-size: 13px; color: #94a3b8; font-weight: 500;">AI-Powered Academic Examination System</p>
            </td>
          </tr>
          <!-- Body -->
          <tr>
            <td style="padding: 32px;">
              <h2 style="margin: 0 0 12px 0; font-size: 20px; font-weight: 700; color: #f1f5f9;">{purpose_title}</h2>
              <p style="margin: 0 0 24px 0; font-size: 14px; line-height: 1.6; color: #cbd5e1;">{purpose_desc}</p>
              
              <!-- OTP Box -->
              <div style="background-color: #090d16; border: 1px dashed #38bdf8; border-radius: 12px; padding: 20px; text-align: center; margin: 24px 0;">
                <div style="font-size: 12px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.1em; color: #94a3b8; margin-bottom: 8px;">Kode Verifikasi OTP</div>
                <div style="font-size: 36px; font-weight: 800; letter-spacing: 8px; color: #38bdf8; font-family: monospace;">{otp_code}</div>
                <div style="font-size: 12px; color: #e2e8f0; margin-top: 8px; opacity: 0.85;">Berlaku selama {expires_in_minutes} menit</div>
              </div>

              <p style="margin: 24px 0 0 0; font-size: 13px; line-height: 1.5; color: #94a3b8;">
                ⚠️ <em>Jangan bagikan kode ini kepada siapapun. Tim EXAMIND tidak akan pernah meminta kode verifikasi Anda.</em>
              </p>
            </td>
          </tr>
          <!-- Footer -->
          <tr>
            <td style="padding: 20px 32px 28px 32px; background-color: #172033; border-top: 1px solid #334155; text-align: center;">
              <p style="margin: 0; font-size: 12px; color: #64748b;">&copy; 2026 EXAMIND Inc. Hak Cipta Dilindungi.</p>
              <p style="margin: 4px 0 0 0; font-size: 11px; color: #475569;">Pesan otomatis ini dikirim sehubungan dengan aktivitas akun Anda.</p>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""


async def send_email_via_resend(to_email: str, subject: str, html_content: str) -> dict:
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
