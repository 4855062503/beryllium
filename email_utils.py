from logging import Logger
from typing import Optional

from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail, From, Attachment, FileContent, FileName, FileType, Disposition, ContentId
from flask import url_for, render_template

from app_core import app
import utils
from models import ApiKeyRequest, PayoutRequest, Referral, UserCreateRequest, UserUpdateEmailRequest

def _attachment(b64data, mime_type, filename, content_id, disposition='attachment'):
    attachment = Attachment()
    attachment.file_content = FileContent(b64data)
    attachment.file_type = FileType(mime_type)
    attachment.file_name = FileName(filename)
    attachment.disposition = Disposition(disposition)
    attachment.content_id = ContentId(content_id)
    return attachment

def _attachment_inline(b64data, mime_type, filename, content_id):
    return _attachment(b64data, mime_type, filename, content_id, 'inline')

def send_email(logger: Logger, subject: str, msg: str, recipient: Optional[str] = None, attachment: Optional[str] = None) -> bool:
    if not recipient:
        recipient = app.config["ADMIN_EMAIL"]
    from_email = From(app.config["FROM_EMAIL"], app.config["FROM_NAME"])
    html = render_template('email.html', content=msg)
    message = Mail(from_email=from_email, to_emails=recipient, subject=subject, html_content=html)
    if attachment:
        message.attachment = attachment
    try:
        sg = SendGridAPIClient(app.config["MAIL_SENDGRID_API_KEY"])
        sg.send(message)
        return True
    except Exception as ex: # pylint: disable=broad-except
        logger.error(f"email '{subject}': {ex}")
    return False

def email_exception(logger: Logger, msg: str):
    send_email(logger, "beryllium exception", msg)

def email_user_create_request(logger: Logger, req: UserCreateRequest, minutes_expiry: int):
    url = url_for("api.user_registration_confirm", token=req.token, _external=True)
    msg = f"You have a pending user registration waiting!<br/><br/>Confirm your registration <a href='{url}'>here</a><br/><br/>Confirm within {minutes_expiry} minutes"
    send_email(logger, "Confirm your registration", msg, req.email)

def email_user_update_email_request(logger: Logger, req: UserUpdateEmailRequest, minutes_expiry: int):
    url = url_for("api.user_update_email_confirm", token=req.token, _external=True)
    msg = f"You have a pending update email request waiting!<br/><br/>Confirm your new email <a href='{url}'>here</a><br/><br/>Confirm within {minutes_expiry} minutes"
    send_email(logger, "Confirm your update email request", msg, req.email)

def email_api_key_request(logger: Logger, req: ApiKeyRequest, minutes_expiry: int):
    url = url_for("api.api_key_confirm", token=req.token, secret=req.secret, _external=True)
    msg = f"You have a pending email login request waiting!<br/><br/>Confirm your email login <a href='{url}'>here</a><br/><br/>Confirm within {minutes_expiry} minutes"
    send_email(logger, "Confirm your email login request", msg, req.user.email)

def email_referral(logger: Logger, referral: Referral):
    shop_name = app.config["REFERRAL_STORE_NAME"]
    qrcode_b64 = utils.qrcode_pngb64_create(referral.token, box_size=4)
    ecom_link = app.config["REFERRAL_ECOMMERCE_URL"]
    if ecom_link:
        ecom_link += f"?beryllium_referral={referral.token}"
    sender_name = referral.user.first_name
    if not sender_name:
        sender_name = referral.user.email
    asset_name = app.config["ASSET_NAME"]
    spend = referral.recipient_min_spend
    spend_asset = app.config["REFERRAL_SPEND_ASSET"]
    gift = f"Spend {spend} {spend_asset} and recieve {referral.reward_recipient} {asset_name}"
    if referral.reward_recipient_type == referral.REWARD_TYPE_PERCENT:
        gift = f"Spend {spend} {spend_asset} or more and recieve {referral.reward_recipient}% off your purchase price"
    msg = f"You have been recieved a referral from {sender_name}<br/><br/>{gift}<br/<br/><img src=\"cid:qrcode\"><br/><br/>"
    if ecom_link:
        msg += ecom_link
    attachment = _attachment_inline(qrcode_b64, 'image/png', 'qrcode.png', 'qrcode')
    send_email(logger, f"{shop_name} Referral", msg, referral.recipient, attachment)

def email_notification_alert(logger: Logger, subject: str, msg: str, recipient: str):
    send_email(logger, subject, msg, recipient=recipient)

def email_payouts_notification(logger: Logger, payout_requests: list[PayoutRequest]):
    recipient = app.config['PAYOUT_GROUP_EMAIL']
    server_name = app.config['SERVER_NAME']
    subject = f'{server_name} payouts'
    url = url_for('payments.payouts', _external=True)
    html_content = f'{len(payout_requests)} payout requests<br/><br/><a href="{url}">payouts</a>'
    send_email(logger, subject, html_content, recipient=recipient)

def email_tripwire_notification(logger: Logger):
    server_name = app.config['SERVER_NAME']
    subject = f'{server_name} tripwire'
    html_content = f'the tripwire at <a href="{server_name}">{server_name}</a> has triggered'
    send_email(logger, subject, html_content)
