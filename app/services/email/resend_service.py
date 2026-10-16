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


def render_password_reset_html(
    user_name: str,
    reset_url: str,
    token_code: str,
    expires_in_minutes: int = 15,
) -> str:
    """Render high-aesthetic, branded HTML template for EXAMIND Password Reset."""
    display_name = user_name.strip() if user_name else "Pengguna EXAMIND"

    return f"""<!DOCTYPE html>
<html lang="id">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Permintaan Atur Ulang Kata Sandi - EXAMIND</title>
</head>
<body style="margin: 0; padding: 0; background-color: #0f172a; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; color: #f8fafc;">
  <table role="presentation" border="0" cellpadding="0" cellspacing="0" width="100%" style="background-color: #0f172a; padding: 40px 12px;">
    <tr>
      <td align="center">
        <table role="presentation" border="0" cellpadding="0" cellspacing="0" width="100%" style="max-width: 540px; background-color: #1e293b; border-radius: 16px; border: 1px solid #334155; overflow: hidden; box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.5);">
          <!-- Header Branding -->
          <tr>
            <td style="padding: 32px 32px 24px 32px; text-align: center; border-bottom: 1px solid #334155; background: linear-gradient(180deg, #1e293b 0%, #172033 100%);">
              <div style="display: inline-block; width: 44px; height: 44px; line-height: 44px; border-radius: 12px; background-color: #0f172a; border: 1px solid #38bdf8; color: #38bdf8; font-weight: 900; font-size: 18px; margin-bottom: 12px;">EX</div>
              <h1 style="margin: 0; font-size: 24px; font-weight: 800; letter-spacing: -0.02em; color: #f8fafc;">EXAMIND</h1>
              <p style="margin: 4px 0 0 0; font-size: 12px; color: #94a3b8; font-weight: 500; text-transform: uppercase; letter-spacing: 0.05em;">Pusat Keamanan Akun & CBT</p>
            </td>
          </tr>

          <!-- Content Body -->
          <tr>
            <td style="padding: 32px 32px 24px 32px;">
              <h2 style="margin: 0 0 14px 0; font-size: 20px; font-weight: 700; color: #f1f5f9;">Permintaan Atur Ulang Kata Sandi</h2>
              <p style="margin: 0 0 16px 0; font-size: 14px; line-height: 1.6; color: #cbd5e1;">
                Halo <strong>{display_name}</strong>,
              </p>
              <p style="margin: 0 0 24px 0; font-size: 14px; line-height: 1.6; color: #94a3b8;">
                Kami menerima permintaan untuk mengatur ulang kata sandi akun EXAMIND Anda. Klik tombol di bawah ini untuk segera membuat kata sandi baru yang aman:
              </p>

              <!-- Primary Action Button -->
              <div style="text-align: center; margin: 28px 0;">
                <a href="{reset_url}" target="_blank" style="display: inline-block; background-color: #38bdf8; color: #0f172a; font-size: 14px; font-weight: 700; text-decoration: none; padding: 14px 32px; border-radius: 10px; box-shadow: 0 4px 14px 0 rgba(56, 189, 248, 0.4); letter-spacing: -0.01em;">
                  Atur Ulang Kata Sandi Saya &rarr;
                </a>
              </div>

              <!-- Secondary Verification Code Box -->
              <div style="background-color: #090d16; border: 1px dashed #334155; border-radius: 12px; padding: 18px; text-align: center; margin: 24px 0;">
                <div style="font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.08em; color: #94a3b8; margin-bottom: 6px;">
                  Atau Masukkan Kode Verifikasi Ini Secara Manual:
                </div>
                <div style="font-size: 28px; font-weight: 800; letter-spacing: 6px; color: #38bdf8; font-family: 'Courier New', Courier, monospace;">
                  {token_code}
                </div>
                <div style="font-size: 12px; color: #64748b; margin-top: 6px;">
                  Berlaku selama <strong>{expires_in_minutes} menit</strong>
                </div>
              </div>

              <!-- Fallback Direct Link -->
              <p style="margin: 20px 0 8px 0; font-size: 12px; color: #64748b; line-height: 1.5;">
                Jika tombol di atas tidak dapat diklik, salin dan tempel tautan berikut ke peramban (browser) Anda:
              </p>
              <div style="background-color: #0f172a; padding: 10px 14px; border-radius: 8px; border: 1px solid #1e293b; font-size: 11px; color: #38bdf8; word-break: break-all; font-family: monospace;">
                {reset_url}
              </div>

              <!-- Security Warning -->
              <div style="margin-top: 28px; padding-top: 20px; border-top: 1px solid #334155;">
                <p style="margin: 0; font-size: 12px; line-height: 1.5; color: #ef4444;">
                  <strong>Pemberitahuan Keamanan:</strong> Jika Anda tidak merasa melakukan permintaan ini, abaikan email ini. Kata sandi lama Anda tetap aman dan tidak akan berubah tanpa tautan/kode ini.
                </p>
              </div>
            </td>
          </tr>

          <!-- Footer -->
          <tr>
            <td style="padding: 20px 32px; background-color: #172033; border-top: 1px solid #334155; text-align: center;">
              <p style="margin: 0; font-size: 12px; color: #64748b;">
                &copy; 2026 EXAMIND Academic Assessment System.
              </p>
              <p style="margin: 4px 0 0 0; font-size: 11px; color: #475569;">
                Email transaksional otomatis ini dikirim melalui Resend API Infrastructure.
              </p>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""


def render_password_reset_success_html(user_name: str) -> str:
    """Render notification confirming password has been successfully reset."""
    display_name = user_name.strip() if user_name else "Pengguna EXAMIND"

    return f"""<!DOCTYPE html>
<html lang="id">
<head>
  <meta charset="utf-8">
  <title>Kata Sandi Berhasil Diperbarui - EXAMIND</title>
</head>
<body style="margin: 0; padding: 0; background-color: #0f172a; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; color: #f8fafc;">
  <table role="presentation" border="0" cellpadding="0" cellspacing="0" width="100%" style="background-color: #0f172a; padding: 40px 12px;">
    <tr>
      <td align="center">
        <table role="presentation" border="0" cellpadding="0" cellspacing="0" width="100%" style="max-width: 520px; background-color: #1e293b; border-radius: 16px; border: 1px solid #334155; padding: 32px; text-align: center;">
          <tr>
            <td>
              <div style="width: 48px; height: 48px; line-height: 48px; border-radius: 50%; background-color: #10b981; color: white; font-size: 24px; margin: 0 auto 16px auto;">&#10003;</div>
              <h1 style="margin: 0 0 12px 0; font-size: 22px; font-weight: 800; color: #f1f5f9;">Kata Sandi Berhasil Diperbarui</h1>
              <p style="font-size: 14px; line-height: 1.6; color: #cbd5e1; margin-bottom: 20px;">
                Halo <strong>{display_name}</strong>, kata sandi akun EXAMIND Anda baru saja berhasil diatur ulang. Anda kini dapat masuk kembali menggunakan kata sandi baru Anda.
              </p>
              <p style="font-size: 12px; color: #ef4444; margin-top: 16px;">
                Jika bukan Anda yang melakukan perubahan ini, segera hubungi tim admin sekolah Anda untuk mengamankan akun.
              </p>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""


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

