import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from loguru import logger
from app.core.config import settings


def send_email(to_email: str, subject: str, body: str):
    # LOCAL mode — just print to terminal, don't send real email
    if settings.is_local:
        logger.info(f"[EMAIL LOCAL] ━━━━━━━━━━━━━━━━━━━━━━━━━━")
        logger.info(f"[EMAIL LOCAL] To      : {to_email}")
        logger.info(f"[EMAIL LOCAL] Subject : {subject}")
        logger.info(f"[EMAIL LOCAL] Body    : {body}")
        logger.info(f"[EMAIL LOCAL] ━━━━━━━━━━━━━━━━━━━━━━━━━━")
        return True

    # PRODUCTION — send real email via Office 365 SMTP
    try:
        msg = MIMEMultipart("alternative")   # ← changed from MIMEText
        msg["Subject"] = subject
        msg["From"]    = settings.MAIL_FROM
        msg["To"]      = to_email

        msg.attach(MIMEText(body, "html"))   # ← attach html body

        with smtplib.SMTP(settings.MAIL_SERVER, settings.MAIL_PORT) as server:
            server.ehlo()                    # ← required for Office 365
            server.starttls()                # ← TLS on port 587
            server.ehlo()                    # ← ehlo again after starttls
            server.login(
                settings.MAIL_USERNAME,
                settings.MAIL_PASSWORD
            )
            server.send_message(msg)

        logger.info(f"[EMAIL] Sent to {to_email}")
        return True

    except smtplib.SMTPAuthenticationError as e:
        logger.error(f"[EMAIL] Auth failed — check MAIL_USERNAME/MAIL_PASSWORD: {e}")
        return False

    except smtplib.SMTPConnectError as e:
        logger.error(f"[EMAIL] Cannot connect to {settings.MAIL_SERVER}:{settings.MAIL_PORT}: {e}")
        return False

    except Exception as e:
        logger.error(f"[EMAIL] Failed to send to {to_email}: {e}")
        return False


def send_rfq_expiry_reminder(
    to_email:    str,
    vendor_name: str,
    rfq_list:    list
) -> bool:
    count = len(rfq_list)
    subject = (
        f"⚠️ {count} RFQ{'s' if count > 1 else ''} Expiring Tomorrow!"
    )

    rfq_rows = ""
    for i, rfq in enumerate(rfq_list, 1):
        rfq_rows += f"""
        <tr style="background:{'#ffffff' if i % 2 == 0 else '#fdf9f9'}">
            <td style="padding:10px;border-bottom:1px solid #f0e0e0">
                <b>{rfq['rfqcaseid']}</b>
            </td>
            <td style="padding:10px;border-bottom:1px solid #f0e0e0">
                {rfq.get('title', '')}
            </td>
            <td style="padding:10px;border-bottom:1px solid #f0e0e0">
                <b style="color:#c0392b">{str(rfq['expirydate'])[:10]}</b>
            </td>
        </tr>
        """

    return send_email(
        to_email,
        subject,
        f"""
        <div style="font-family:Arial;max-width:650px;margin:auto">

          <div style="background:#1F3864;padding:24px;text-align:center">
            <h2 style="color:white;margin:0">Vendor Portal — RFQ Reminder</h2>
          </div>

          <div style="padding:32px">
            <p>Dear <b>{vendor_name}</b>,</p>

            <p>You have <b style="color:#c0392b">{count} RFQ{'s' if count > 1 else ''}</b>
               expiring <b>tomorrow</b>. Please submit your bids before they expire.</p>

            <div style="background:#fde8e8;border-radius:6px;
                        overflow:hidden;margin:20px 0">
              <table style="width:100%;border-collapse:collapse">
                <thead>
                  <tr style="background:#c0392b">
                    <th style="padding:12px;color:white;text-align:left">RFQ Case ID</th>
                    <th style="padding:12px;color:white;text-align:left">Title</th>
                    <th style="padding:12px;color:white;text-align:left">Expiry Date</th>
                  </tr>
                </thead>
                <tbody>
                  {rfq_rows}
                </tbody>
              </table>
            </div>

            <div style="text-align:center;margin:28px 0">
              <a href="{settings.FRONTEND_BASE_URL}"
                 style="background:#1F3864;color:white;padding:14px 32px;
                        text-decoration:none;border-radius:6px;font-size:16px">
                Submit Bids Now
              </a>
            </div>

            <p style="color:#aaa;font-size:12px">
              This is an automated reminder. Do not reply to this email.
            </p>
          </div>

        </div>
        """
    )


# import smtplib
# from email.mime.text import MIMEText
# from loguru import logger
# from app.core.config import settings


# def send_email(to_email: str, subject: str, body: str):
#     # LOCAL mode — just print to terminal, don't send real email
#     if settings.is_local:
#         logger.info(f"[EMAIL LOCAL] ━━━━━━━━━━━━━━━━━━━━━━━━━━")
#         logger.info(f"[EMAIL LOCAL] To      : {to_email}")
#         logger.info(f"[EMAIL LOCAL] Subject : {subject}")
#         logger.info(f"[EMAIL LOCAL] Body    : {body}")
#         logger.info(f"[EMAIL LOCAL] ━━━━━━━━━━━━━━━━━━━━━━━━━━")
#         return True

#     # PRODUCTION — send real email via SMTP
#     try:
#         msg = MIMEText(body, "html")
#         msg["Subject"] = subject
#         msg["From"]    = settings.MAIL_FROM
#         msg["To"]      = to_email

#         with smtplib.SMTP(settings.MAIL_SERVER, settings.MAIL_PORT) as server:
#             server.starttls()
#             server.login(settings.MAIL_USERNAME, settings.MAIL_PASSWORD)
#             server.send_message(msg)

#         logger.info(f"[EMAIL] Sent to {to_email}")
#         return True

#     except Exception as e:
#         logger.error(f"[EMAIL] Failed to send to {to_email}: {e}")
#         return False

# def send_rfq_expiry_reminder(
#     to_email:    str,
#     vendor_name: str,
#     rfq_list:    list      # list of rfq dicts
# ) -> bool:
#     count = len(rfq_list)
#     subject = (
#         f"⚠️ {count} RFQ{'s' if count > 1 else ''} Expiring Tomorrow!"
#     )

#     # Build RFQ rows for email table
#     rfq_rows = ""
#     for i, rfq in enumerate(rfq_list, 1):
#         rfq_rows += f"""
#         <tr style="background:{'#ffffff' if i % 2 == 0 else '#fdf9f9'}">
#             <td style="padding:10px;border-bottom:1px solid #f0e0e0">
#                 <b>{rfq['rfqcaseid']}</b>
#             </td>
#             <td style="padding:10px;border-bottom:1px solid #f0e0e0">
#                 {rfq.get('title', '')}
#             </td>
#             <td style="padding:10px;border-bottom:1px solid #f0e0e0">
#                 <b style="color:#c0392b">{str(rfq['expirydate'])[:10]}</b>
#             </td>
#         </tr>
#         """

#     return send_email(
#         to_email,
#         subject,
#         f"""
#         <div style="font-family:Arial;max-width:650px;margin:auto">

#           <div style="background:#1F3864;padding:24px;text-align:center">
#             <h2 style="color:white;margin:0">Vendor Portal — RFQ Reminder</h2>
#           </div>

#           <div style="padding:32px">
#             <p>Dear <b>{vendor_name}</b>,</p>

#             <p>You have <b style="color:#c0392b">{count} RFQ{'s' if count > 1 else ''}</b>
#                expiring <b>tomorrow</b>. Please submit your bids before they expire.</p>

#             <div style="background:#fde8e8;border-radius:6px;
#                         overflow:hidden;margin:20px 0">
#               <table style="width:100%;border-collapse:collapse">
#                 <thead>
#                   <tr style="background:#c0392b">
#                     <th style="padding:12px;color:white;text-align:left">RFQ Case ID</th>
#                     <th style="padding:12px;color:white;text-align:left">Title</th>
#                     <th style="padding:12px;color:white;text-align:left">Expiry Date</th>
#                   </tr>
#                 </thead>
#                 <tbody>
#                   {rfq_rows}
#                 </tbody>
#               </table>
#             </div>

#             <div style="text-align:center;margin:28px 0">
#               <a href="{settings.FRONTEND_BASE_URL}"
#                  style="background:#1F3864;color:white;padding:14px 32px;
#                         text-decoration:none;border-radius:6px;font-size:16px">
#                 Submit Bids Now
#               </a>
#             </div>

#             <p style="color:#aaa;font-size:12px">
#               This is an automated reminder. Do not reply to this email.
#             </p>
#           </div>

#         </div>
#         """
#     )
