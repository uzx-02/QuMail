"""Small accessibility/error conventions shared by the development mail controls."""
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QPushButton,QWidget


def configure(root,names,order):
    for widget,name in names:
        widget.setAccessibleName(name)
    for button in root.findChildren(QPushButton):
        button.setAccessibleName(button.text().replace('&',''))
        button.setAutoDefault(False)  # Enter in an editor never implicitly submits/discards.
        button.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
    for first,second in zip(order,order[1:]): QWidget.setTabOrder(first,second)


def error_message(error):
    code=getattr(getattr(error,'code',None),'value','')
    google_steps={
        'google_browser_start_failed':'Could not start Google authorization. Check the Desktop client and default browser.',
        'google_callback_failed_or_expired':'Google browser authorization was cancelled or expired. Start Connect Google again and complete consent promptly.',
        'google_token_exchange_failed':'Google token exchange failed. Check connectivity, Desktop-client configuration and granted scopes; no account was installed.',
        'google_verified_identity_failed':'Google identity verification failed. Check the system clock and client configuration; no account was installed.',
        'google_token_time_invalid':'Google token time is invalid. Synchronize Windows date/time, then retry authorization; no token was accepted.',
        'google_verification_keys_unavailable':'Google verification keys could not be fetched. Check connectivity and retry; signature verification remains required.',
        'google_token_signature_or_format_invalid':'Google token signature or format verification failed. No account was installed; inspect the maintained verifier configuration.',
        'google_token_audience_mismatch':'Google token audience does not match the configured Desktop client. Check that client configuration before retrying.',
        'google_token_nonce_mismatch':'Google token nonce does not match this authorization. Start a fresh flow; no account was installed.',
        'google_token_authority_or_claims_invalid':'Google token issuer, subject, email authority or required claims were rejected. No account was installed.',
        'google_expected_address_mismatch':'Google returned a different account. Select the exact expected address and authorize again.',
        'google_required_consent_missing':'Required Google mail/identity consent is missing. Authorize again and grant the requested test permissions.',
    }
    if code in google_steps: return google_steps[code]
    if code in ('authorize_selected_google_account_with_mail_scope','credential_unavailable_or_expired','identity_binding_failed'):
        return 'Google authorization failed or expired. Check the configured Desktop client; reauthorize the selected account with mail consent in Settings.'
    if code in ('cancelled_or_account_changed','cancelled_or_stale','cancelled_before_submission','account_locked_or_changed'):
        return 'Operation stopped or account changed. Refresh the outbox/flags before retrying; a dispatched action may already have reached the server.'
    if code in ('invalid_mailbox_response','mailbox_connection_failed','transport_failure'):
        return 'Connection failed. Check connectivity and the configured Google client. Inspect outbox state before any explicit retry.'
    if code=='select_imported_signer_certificate_in_settings':
        return 'Signer key unavailable. Import the expected public certificate in Settings, verify its fingerprint independently, then select it and open again.'
    if code in ('profile_or_recipient_rejected','unverified_or_changed_recipient','key_not_active'):
        return 'Recipient/key unavailable, unverified, changed, expired or revoked. Resolve the contact in Settings and independently verify the current fingerprint. No bypass.'
    if code in ('resource_limit','mailbox_resource_limit','invalid_request','invalid_input'):
        return 'Input exceeds a qualified limit or is invalid. Check recipients, filename, body and attachment sizes in the guide; no plaintext fallback.'
    if code in ('storage_failure','authenticated_storage_failure','authenticated_record_invalid','secure_store_unavailable'):
        return 'Vault/storage unavailable. Check the selected vault and Windows account; unlock again. Inspect saved state before retrying; do not overwrite recovery data.'
    if code=='explicit_duplicate_risk_acknowledgment_required':
        return 'Unknown may already be accepted. An explicit retry requires acknowledging duplicate risk; inspect the outbox first.'
    return 'Operation failed; no unverified content released. Check the selected account, operation state and qualified limits in the guide. No automatic retry or plaintext fallback.'
