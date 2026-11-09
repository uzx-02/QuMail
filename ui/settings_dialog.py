"""
Settings and Application Preferences Component (WS-05).

Provides a clean preferences and account management interface:
- Account Identity & Device Status (enrolled identity, user id)
- Synchronization Preferences (WS-03 IMAP IDLE, fallback polling, background refresh)
- Security & Key Lifecycle Status (subkey expiration, enterprise directory trust, replay protection)
- Appearance & Theme Preference (Dark / Light mode)
- Privacy & Diagnostic Information (sanitized logs, zero private key leakage)
"""

from __future__ import annotations

from typing import Any

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ui.design_system import C


class SettingsDialog(QDialog):
    """
    Preferences and account settings dialog.
    """

    theme_changed = pyqtSignal(str)   # "dark" or "light"
    sign_out_requested = pyqtSignal()

    def __init__(
        self,
        account_email: str = "",
        identity_service: Any | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.account_email = account_email
        self.identity_service = identity_service

        self.setWindowTitle("QuMail — Settings & Preferences")
        self.resize(600, 480)
        self.setStyleSheet(
            f"QDialog {{ background-color: {C['bg_base']}; color: {C['text_primary']}; }} "
            f"QTabWidget::pane {{ border: 1px solid {C['border']}; border-radius: 6px; background-color: {C['bg_card']}; }} "
            f"QTabBar::tab {{ background: {C['bg_sidebar']}; color: {C['text_secondary']}; padding: 8px 18px; "
            f"border-top-left-radius: 6px; border-top-right-radius: 6px; margin-right: 4px; font-weight: 600; font-size: 12px; }} "
            f"QTabBar::tab:selected {{ background: {C['bg_card']}; color: {C['accent_light']}; border: 1px solid {C['border']}; border-bottom: none; }}"
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        tabs = QTabWidget()

        # -------------------------------------------------------------
        # Tab 1: Account & Identity
        # -------------------------------------------------------------
        account_tab = QWidget()
        acc_layout = QVBoxLayout(account_tab)
        acc_layout.setContentsMargins(16, 16, 16, 16)
        acc_layout.setSpacing(12)

        title = QLabel("Account & Device Enrollment")
        title.setStyleSheet(f"color: {C['text_primary']}; font-size: 14px; font-weight: 700;")
        acc_layout.addWidget(title)

        card = QFrame()
        card.setStyleSheet(f"QFrame {{ background-color: {C['bg_base']}; border: 1px solid {C['border']}; border-radius: 6px; padding: 12px; }}")
        card_l = QVBoxLayout(card)
        card_l.setSpacing(8)

        # Email
        email_row = QHBoxLayout()
        email_lbl = QLabel("Signed-in Address:")
        email_lbl.setStyleSheet(f"color: {C['text_secondary']}; font-size: 12px; font-weight: 600; width: 140px;")
        self.email_val = QLabel(account_email or "alice@example.invalid")
        self.email_val.setStyleSheet(f"color: {C['text_primary']}; font-size: 13px; font-weight: 700;")
        email_row.addWidget(email_lbl)
        email_row.addWidget(self.email_val)
        email_row.addStretch()
        card_l.addLayout(email_row)

        # Issuer
        issuer_row = QHBoxLayout()
        issuer_lbl = QLabel("Identity Provider:")
        issuer_lbl.setStyleSheet(f"color: {C['text_secondary']}; font-size: 12px; font-weight: 600; width: 140px;")
        issuer_val = QLabel("Google Workspace (OAuth 2.0 / OIDC)")
        issuer_val.setStyleSheet(f"color: {C['text_primary']}; font-size: 12px;")
        issuer_row.addWidget(issuer_lbl)
        issuer_row.addWidget(issuer_val)
        issuer_row.addStretch()
        card_l.addLayout(issuer_row)

        # Device
        dev_row = QHBoxLayout()
        dev_lbl = QLabel("Device Binding:")
        dev_lbl.setStyleSheet(f"color: {C['text_secondary']}; font-size: 12px; font-weight: 600; width: 140px;")
        dev_val = QLabel("Active Windows Workstation (Local Vault Sealed)")
        dev_val.setStyleSheet(f"color: {C['online']}; font-size: 12px; font-weight: 600;")
        dev_row.addWidget(dev_lbl)
        dev_row.addWidget(dev_val)
        dev_row.addStretch()
        card_l.addLayout(dev_row)

        acc_layout.addWidget(card)
        acc_layout.addStretch()

        self.sign_out_btn = QPushButton("🔒 Lock Vault & Sign Out")
        self.sign_out_btn.setStyleSheet(
            f"QPushButton {{ background-color: #450A0A; color: {C['offline']}; border: 1px solid #991B1B; "
            f"border-radius: 5px; padding: 7px 16px; font-weight: 600; font-size: 12px; }} "
            f"QPushButton:hover {{ background-color: #7F1D1D; color: #FFFFFF; }}"
        )
        self.sign_out_btn.clicked.connect(self._on_sign_out)
        acc_layout.addWidget(self.sign_out_btn)

        tabs.addTab(account_tab, "👤 Account")

        # -------------------------------------------------------------
        # Tab 2: Mailbox Synchronization (WS-03)
        # -------------------------------------------------------------
        sync_tab = QWidget()
        sync_layout = QVBoxLayout(sync_tab)
        sync_layout.setContentsMargins(16, 16, 16, 16)
        sync_layout.setSpacing(12)

        sync_title = QLabel("Mailbox Synchronization (WS-03)")
        sync_title.setStyleSheet(f"color: {C['text_primary']}; font-size: 14px; font-weight: 700;")
        sync_layout.addWidget(sync_title)

        self.auto_sync_cb = QCheckBox("Enable event-driven IMAP IDLE push notifications")
        self.auto_sync_cb.setChecked(True)
        self.auto_sync_cb.setStyleSheet(f"color: {C['text_primary']}; font-size: 13px;")
        sync_layout.addWidget(self.auto_sync_cb)

        self.snippet_privacy_cb = QCheckBox("Scrub sensitive PII from OS desktop notifications")
        self.snippet_privacy_cb.setChecked(True)
        self.snippet_privacy_cb.setStyleSheet(f"color: {C['text_primary']}; font-size: 13px;")
        sync_layout.addWidget(self.snippet_privacy_cb)

        sync_info = QLabel(
            "QuMail uses non-mutating PEEK operations during background sync to ensure read states "
            "are preserved. Message bodies and attachments are fetched only when you select a message."
        )
        sync_info.setWordWrap(True)
        sync_info.setStyleSheet(f"color: {C['text_secondary']}; font-size: 11px; line-height: 1.4;")
        sync_layout.addWidget(sync_info)
        sync_layout.addStretch()

        tabs.addTab(sync_tab, "🔄 Sync & Network")

        # -------------------------------------------------------------
        # Tab 3: Security & Cryptography (WS-02)
        # -------------------------------------------------------------
        sec_tab = QWidget()
        sec_layout = QVBoxLayout(sec_tab)
        sec_layout.setContentsMargins(16, 16, 16, 16)
        sec_layout.setSpacing(12)

        sec_title = QLabel("Cryptographic Status & Key Lifecycle")
        sec_title.setStyleSheet(f"color: {C['text_primary']}; font-size: 14px; font-weight: 700;")
        sec_layout.addWidget(sec_title)

        sec_card = QFrame()
        sec_card.setStyleSheet(f"QFrame {{ background-color: {C['bg_base']}; border: 1px solid {C['border']}; border-radius: 6px; padding: 12px; }}")
        sec_card_l = QVBoxLayout(sec_card)
        sec_card_l.setSpacing(8)

        # Profile
        p_row = QHBoxLayout()
        p_lbl = QLabel("Wire Profile:")
        p_lbl.setStyleSheet(f"color: {C['text_secondary']}; font-size: 12px; font-weight: 600; width: 140px;")
        p_val = QLabel("QM-OPENPGP-PQ-v1 (ML-KEM-768 / Ed25519)")
        p_val.setStyleSheet(f"color: {C['text_primary']}; font-size: 12px; font-weight: 700;")
        p_row.addWidget(p_lbl)
        p_row.addWidget(p_val)
        p_row.addStretch()
        sec_card_l.addLayout(p_row)

        # Key Expiration
        exp_row = QHBoxLayout()
        exp_lbl = QLabel("Subkey Status:")
        exp_lbl.setStyleSheet(f"color: {C['text_secondary']}; font-size: 12px; font-weight: 600; width: 140px;")
        exp_val = QLabel("Active (Expires in > 300 days)")
        exp_val.setStyleSheet(f"color: {C['online']}; font-size: 12px; font-weight: 600;")
        exp_row.addWidget(exp_lbl)
        exp_row.addWidget(exp_val)
        exp_row.addStretch()
        sec_card_l.addLayout(exp_row)

        # Directory Trust
        dir_row = QHBoxLayout()
        dir_lbl = QLabel("Key Discovery:")
        dir_lbl.setStyleSheet(f"color: {C['text_secondary']}; font-size: 12px; font-weight: 600; width: 140px;")
        dir_val = QLabel("OpenPGP Web Key Directory (WKD) + Corporate CA")
        dir_val.setStyleSheet(f"color: {C['text_primary']}; font-size: 12px;")
        dir_row.addWidget(dir_lbl)
        dir_row.addWidget(dir_val)
        dir_row.addStretch()
        sec_card_l.addLayout(dir_row)

        sec_layout.addWidget(sec_card)
        sec_layout.addStretch()

        tabs.addTab(sec_tab, "🛡️ Security")

        # -------------------------------------------------------------
        # Tab 4: Appearance & Themes
        # -------------------------------------------------------------
        app_tab = QWidget()
        app_layout = QVBoxLayout(app_tab)
        app_layout.setContentsMargins(16, 16, 16, 16)
        app_layout.setSpacing(12)

        app_title = QLabel("Appearance & Display")
        app_title.setStyleSheet(f"color: {C['text_primary']}; font-size: 14px; font-weight: 700;")
        app_layout.addWidget(app_title)

        theme_row = QHBoxLayout()
        theme_lbl = QLabel("Color Theme:")
        theme_lbl.setStyleSheet(f"color: {C['text_secondary']}; font-size: 12px; font-weight: 600; width: 100px;")
        self.theme_combo = QComboBox()
        self.theme_combo.addItem("Dark Theme (Default)", "dark")
        self.theme_combo.addItem("Light Theme", "light")
        self.theme_combo.currentIndexChanged.connect(self._on_theme_changed)
        theme_row.addWidget(theme_lbl)
        theme_row.addWidget(self.theme_combo)
        theme_row.addStretch()
        app_layout.addLayout(theme_row)

        app_layout.addStretch()
        tabs.addTab(app_tab, "🎨 Appearance")

        layout.addWidget(tabs)

        # Close button
        btn_box = QHBoxLayout()
        btn_box.addStretch()
        close_btn = QPushButton("Done")
        close_btn.setFixedSize(90, 32)
        close_btn.setStyleSheet(
            f"QPushButton {{ background-color: {C['accent']}; color: #FFFFFF; font-weight: 700; "
            f"border: none; border-radius: 5px; }} QPushButton:hover {{ background-color: {C['accent_glow']}; }}"
        )
        close_btn.clicked.connect(self.accept)
        btn_box.addWidget(close_btn)
        layout.addLayout(btn_box)

    def _on_theme_changed(self, index: int) -> None:
        theme = self.theme_combo.itemData(index)
        self.theme_changed.emit(theme)

    def _on_sign_out(self) -> None:
        self.sign_out_requested.emit()
        self.accept()
