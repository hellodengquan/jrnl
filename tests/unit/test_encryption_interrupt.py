# Copyright © 2012-2023 jrnl contributors
# License: https://www.gnu.org/licenses/gpl-3.0.html

from unittest import mock

import pytest

from jrnl.encryption.Jrnlv2Encryption import Jrnlv2Encryption
from jrnl.exception import JrnlException
from jrnl.messages import MsgText


@pytest.fixture
def enc():
    config = {"journal": "test_journal.txt"}
    return Jrnlv2Encryption("test", config)


class TestPasswordInterruptHandling:
    """Test KeyboardInterrupt and EOFError handling in password entry flow."""

    def _assert_state_reset(self, enc):
        """Helper: verify all password-related state is clean."""
        assert enc._attempts == 0
        assert enc._failed_before is False
        assert enc._password is None or enc._password == ""

    # ---- _prompt_password 入口中断测试 ----

    @mock.patch("jrnl.encryption.BasePasswordEncryption.prompt_password")
    def test_prompt_password_keyboard_interrupt_raises_cancel(
        self, mock_prompt, enc
    ):
        mock_prompt.side_effect = KeyboardInterrupt()

        with pytest.raises(JrnlException) as excinfo:
            enc._prompt_password()

        assert excinfo.value.has_message_text(MsgText.PasswordEntryCancelled)

    @mock.patch("jrnl.encryption.BasePasswordEncryption.prompt_password")
    def test_prompt_password_keyboard_interrupt_resets_state(
        self, mock_prompt, enc
    ):
        enc._attempts = 2
        enc._failed_before = True
        enc._password = "dirty_password"
        mock_prompt.side_effect = KeyboardInterrupt()

        try:
            enc._prompt_password()
        except JrnlException:
            pass

        self._assert_state_reset(enc)

    @mock.patch("jrnl.encryption.BasePasswordEncryption.prompt_password")
    def test_prompt_password_eof_raises_eof_message(self, mock_prompt, enc):
        mock_prompt.side_effect = EOFError()

        with pytest.raises(JrnlException) as excinfo:
            enc._prompt_password()

        assert excinfo.value.has_message_text(MsgText.EOFOnInput)

    @mock.patch("jrnl.encryption.BasePasswordEncryption.prompt_password")
    def test_prompt_password_eof_resets_state(self, mock_prompt, enc):
        enc._attempts = 1
        enc._failed_before = True
        enc._password = "some_pw"
        mock_prompt.side_effect = EOFError()

        try:
            enc._prompt_password()
        except JrnlException:
            pass

        self._assert_state_reset(enc)

    @mock.patch("jrnl.encryption.BasePasswordEncryption.prompt_password")
    def test_prompt_password_interrupt_attempts_not_incremented(
        self, mock_prompt, enc
    ):
        mock_prompt.side_effect = KeyboardInterrupt()
        initial_attempts = enc._attempts

        try:
            enc._prompt_password()
        except JrnlException:
            pass

        assert enc._attempts == 0
        assert enc._attempts == initial_attempts

    # ---- decrypt 入口中断测试（通过 _prompt_password） ----

    @mock.patch("jrnl.encryption.BasePasswordEncryption.get_keyring_password")
    @mock.patch("jrnl.encryption.BasePasswordEncryption.prompt_password")
    def test_decrypt_keyboard_interrupt_on_first_prompt(
        self, mock_prompt, mock_keyring, enc
    ):
        mock_keyring.return_value = None
        mock_prompt.side_effect = KeyboardInterrupt()
        some_ciphertext = b"doesnt_matter"

        with pytest.raises(JrnlException) as excinfo:
            enc.decrypt(some_ciphertext)

        assert excinfo.value.has_message_text(MsgText.PasswordEntryCancelled)

    @mock.patch("jrnl.encryption.BasePasswordEncryption.get_keyring_password")
    @mock.patch("jrnl.encryption.BasePasswordEncryption.prompt_password")
    def test_decrypt_eof_on_first_prompt(
        self, mock_prompt, mock_keyring, enc
    ):
        mock_keyring.return_value = None
        mock_prompt.side_effect = EOFError()
        some_ciphertext = b"doesnt_matter"

        with pytest.raises(JrnlException) as excinfo:
            enc.decrypt(some_ciphertext)

        assert excinfo.value.has_message_text(MsgText.EOFOnInput)

    @mock.patch("jrnl.encryption.BasePasswordEncryption.get_keyring_password")
    @mock.patch("jrnl.encryption.BasePasswordEncryption.prompt_password")
    def test_decrypt_interrupt_after_wrong_password_resets_state(
        self, mock_prompt, mock_keyring, enc
    ):
        mock_keyring.return_value = None
        mock_prompt.side_effect = ["wrong1", KeyboardInterrupt()]
        some_ciphertext = b"garbage_that_wont_decrypt"

        try:
            enc.decrypt(some_ciphertext)
        except JrnlException:
            pass

        self._assert_state_reset(enc)

    # ---- encrypt 入口中断测试（通过 create_password） ----

    @mock.patch("jrnl.encryption.BasePasswordEncryption.create_password")
    @mock.patch("jrnl.encryption.BasePasswordEncryption.get_keyring_password")
    def test_encrypt_create_password_keyboard_interrupt(
        self, mock_keyring, mock_create, enc
    ):
        mock_keyring.return_value = None
        mock_create.side_effect = KeyboardInterrupt()

        with pytest.raises(JrnlException) as excinfo:
            enc.encrypt("some plain text")

        assert excinfo.value.has_message_text(MsgText.PasswordEntryCancelled)

    @mock.patch("jrnl.encryption.BasePasswordEncryption.create_password")
    @mock.patch("jrnl.encryption.BasePasswordEncryption.get_keyring_password")
    def test_encrypt_create_password_eof(
        self, mock_keyring, mock_create, enc
    ):
        mock_keyring.return_value = None
        mock_create.side_effect = EOFError()

        with pytest.raises(JrnlException) as excinfo:
            enc.encrypt("some plain text")

        assert excinfo.value.has_message_text(MsgText.EOFOnInput)

    @mock.patch("jrnl.encryption.BasePasswordEncryption.create_password")
    @mock.patch("jrnl.encryption.BasePasswordEncryption.get_keyring_password")
    def test_encrypt_interrupt_resets_state(
        self, mock_keyring, mock_create, enc
    ):
        enc._attempts = 2
        enc._failed_before = True
        enc._password = "preexisting_pw"
        enc.password = None
        mock_keyring.return_value = None
        mock_create.side_effect = KeyboardInterrupt()

        try:
            enc.encrypt("hello world")
        except JrnlException:
            pass

        self._assert_state_reset(enc)

    # ---- 状态重置深度验证 ----

    def test_reset_password_state_clears_all_fields(self, enc):
        enc._attempts = 3
        enc._failed_before = True
        enc._password = "secret123"

        enc._reset_password_state()

        self._assert_state_reset(enc)

    def test_clear_resets_attempts_and_failed_before(self, enc):
        enc._attempts = 3
        enc._failed_before = True
        enc._password = "stale_pw"
        enc.check_keyring = True

        enc.clear()

        self._assert_state_reset(enc)
        assert enc.check_keyring is False

    # ---- 连续中断后重试能正常解锁流程 ----

    @mock.patch("jrnl.encryption.BasePasswordEncryption.get_keyring_password")
    @mock.patch("jrnl.encryption.BasePasswordEncryption.prompt_password")
    def test_interrupt_then_retry_succeeds_from_clean_state(
        self, mock_prompt, mock_keyring, enc
    ):
        plaintext = "hello world, this is a test"
        correct_pw = "correct_password"
        enc2 = Jrnlv2Encryption("test", {"journal": "test.txt"})
        enc2.password = correct_pw
        ciphertext = enc2.encrypt(plaintext)

        mock_keyring.return_value = None

        call_count = {"n": 0}

        def interrupt_then_correct(**kwargs):
            call_count["n"] += 1
            if call_count["n"] == 1:
                raise KeyboardInterrupt
            return correct_pw

        mock_prompt.side_effect = interrupt_then_correct

        try:
            enc.decrypt(ciphertext)
        except JrnlException:
            pass

        self._assert_state_reset(enc)

        enc3 = Jrnlv2Encryption("test", {"journal": "test.txt"})
        mock_keyring.return_value = None
        mock_prompt.side_effect = [correct_pw]

        result = enc3.decrypt(ciphertext)
        assert result == plaintext

    @mock.patch("jrnl.encryption.BasePasswordEncryption.get_keyring_password")
    @mock.patch("jrnl.encryption.BasePasswordEncryption.prompt_password")
    def test_multiple_interrupts_then_retry(
        self, mock_prompt, mock_keyring, enc
    ):
        plaintext = "multiple interrupts test"
        correct_pw = "pw_for_retry"
        enc2 = Jrnlv2Encryption("test", {"journal": "test.txt"})
        enc2.password = correct_pw
        ciphertext = enc2.encrypt(plaintext)

        mock_keyring.return_value = None
        mock_prompt.side_effect = [
            KeyboardInterrupt(),
            EOFError(),
        ]

        for _ in range(2):
            fresh_enc = Jrnlv2Encryption("test", {"journal": "test.txt"})
            mock_keyring.return_value = None
            try:
                mock_prompt.side_effect = (
                    KeyboardInterrupt() if _ == 0 else EOFError()
                )
                fresh_enc.decrypt(ciphertext)
            except JrnlException:
                pass
            self._assert_state_reset(fresh_enc)

        final_enc = Jrnlv2Encryption("test", {"journal": "test.txt"})
        mock_prompt.side_effect = [correct_pw]
        mock_keyring.return_value = None
        result = final_enc.decrypt(ciphertext)
        assert result == plaintext

    @mock.patch("jrnl.encryption.BasePasswordEncryption.get_keyring_password")
    @mock.patch("jrnl.encryption.BasePasswordEncryption.prompt_password")
    def test_interrupt_after_keyring_failure(
        self, mock_prompt, mock_keyring, enc
    ):
        plaintext = "keyring failure then interrupt test"
        correct_pw = "good_pw"
        enc2 = Jrnlv2Encryption("test", {"journal": "test.txt"})
        enc2.password = correct_pw
        ciphertext = enc2.encrypt(plaintext)

        mock_keyring.return_value = "wrong_keyring_pw"
        mock_prompt.side_effect = KeyboardInterrupt()

        with pytest.raises(JrnlException) as excinfo:
            enc.decrypt(ciphertext)

        assert excinfo.value.has_message_text(MsgText.PasswordEntryCancelled)
        self._assert_state_reset(enc)

    @mock.patch("jrnl.encryption.BasePasswordEncryption.get_keyring_password")
    @mock.patch("jrnl.encryption.BasePasswordEncryption.prompt_password")
    def test_retry_after_interrupt_has_3_attempts_available(
        self, mock_prompt, mock_keyring, enc
    ):
        plaintext = "max attempts after retry"
        correct_pw = "max_attempts_pw"
        enc2 = Jrnlv2Encryption("test", {"journal": "test.txt"})
        enc2.password = correct_pw
        ciphertext = enc2.encrypt(plaintext)

        mock_keyring.return_value = None
        mock_prompt.side_effect = KeyboardInterrupt()

        try:
            enc.decrypt(ciphertext)
        except JrnlException:
            pass

        self._assert_state_reset(enc)

        fresh_enc = Jrnlv2Encryption("test", {"journal": "test.txt"})
        mock_keyring.return_value = None
        mock_prompt.side_effect = [
            "wrong1",
            "wrong2",
            correct_pw,
        ]

        result = fresh_enc.decrypt(ciphertext)
        assert result == plaintext
        assert fresh_enc._attempts == 3
