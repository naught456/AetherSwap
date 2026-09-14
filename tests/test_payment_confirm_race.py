"""回归测试：手动确认付款后，过期的邮件监听结果不得污染后续购买流程。

背景 bug：配置邮箱监听时，`_do_payment_notify_and_wait` 会启动后台线程监听邮箱。
用户手动点击「已完成支付」后主流程继续，但邮件监听线程在超时后仍会调用
`confirm_payment(False)`，导致下一件商品的付款等待被误判为取消/失败，
进而触发「停止后续全部购买请求」。
"""
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import pipeline_steps
from app.state import State


_EMAIL_CONFIG = {
    "notify": {
        "email_user": "user@example.com",
        "email_pass": "secret",
        "email_timeout_seconds": 5,
    }
}


def _fake_email_listener_that_keeps_running(monkeypatch, result="timeout"):
    """模拟真实行为：邮件监听直到超时/取消前一直在轮询。"""
    def fake_wait_email_command(cfg, timeout_seconds=300, is_stop_requested=None, log_fn=None):
        deadline = time.time() + 5
        while time.time() < deadline:
            if is_stop_requested and is_stop_requested():
                return result
            time.sleep(0.01)
        return result

    monkeypatch.setattr(pipeline_steps, "wait_email_command", fake_wait_email_command)


def test_manual_confirm_discards_stale_email_timeout(monkeypatch):
    _fake_email_listener_that_keeps_running(monkeypatch, result="timeout")
    state = State()

    def manual_confirm_later() -> None:
        time.sleep(0.2)
        state.confirm_payment(True)  # 用户点击「已完成支付」

    threading.Thread(target=manual_confirm_later, daemon=True).start()

    ok = pipeline_steps._do_payment_notify_and_wait(
        {"name": "测试物品"},
        _EMAIL_CONFIG,
        10.0,
        1,
        "http://pay.example/url",
        "wechat",
        "order-1",
        0.0,
        state.set_pending_payment,
        state.wait_payment_confirm,
        state.confirm_payment,
        lambda: False,
        None,
    )

    assert ok is True
    # 等待邮件监听线程退出（round_done 后它应在极短时间内返回）
    time.sleep(0.3)
    # 关键断言：过期的邮件超时结果不得回写为 False
    assert state._user_confirmed is True


def test_state_ignores_confirm_when_no_wait_active():
    state = State()
    # 无等待进行时的过期回调应被忽略，而不是留下残留状态
    state.confirm_payment(False)
    assert state._user_confirmed is None


def test_next_round_not_poisoned_after_manual_confirm(monkeypatch):
    _fake_email_listener_that_keeps_running(monkeypatch, result="timeout")
    state = State()

    def manual_confirm_later() -> None:
        time.sleep(0.1)
        state.confirm_payment(True)

    threading.Thread(target=manual_confirm_later, daemon=True).start()

    ok = pipeline_steps._do_payment_notify_and_wait(
        {"name": "第一件"},
        _EMAIL_CONFIG,
        10.0,
        1,
        "http://pay.example/url",
        "alipay",
        "order-1",
        0.0,
        state.set_pending_payment,
        state.wait_payment_confirm,
        state.confirm_payment,
        lambda: False,
        None,
    )
    assert ok is True

    time.sleep(0.3)  # 让上一轮的邮件监听线程彻底退出

    # 第二轮付款等待：0.2 秒后手动确认成功
    def second_round_confirm() -> None:
        time.sleep(0.2)
        state.confirm_payment(True)

    threading.Thread(target=second_round_confirm, daemon=True).start()
    started = time.time()
    ok2 = state.wait_payment_confirm(timeout_seconds=5.0)
    elapsed = time.time() - started

    # 第二轮应等到手动确认为止（若被上一轮过期回调污染会立即返回 False）
    assert ok2 is True
    assert elapsed >= 0.15
