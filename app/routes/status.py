"""Status, log, plan, and payment-related routes."""
import threading
from pathlib import Path
from fastapi import APIRouter
from app.config_loader import load_app_config_validated
from app.notify import send_payment_confirmed_email
from app.state import (
    clear_log,
    confirm_payment,
    get_log,
    get_pending_payment,
    get_plan,
    get_status,
    log,
    set_pending_payment,
)
from config import get_buff
from pydantic import BaseModel
from utils.time import (
    now_in_configured_timezone,
    resolve_configured_timezone,
    timestamp_in_configured_timezone,
)
router = APIRouter()
class ConfirmBody(BaseModel):
    ok: bool
@router.get("/api/status")
def api_status():
    st = get_status()
    buff_creds = get_buff()
    st["buff_no_cookie"] = not bool((buff_creds.get("cookies") or "").strip())
    return st

@router.get("/api/log")
def api_log(since: int = 0):
    return {"lines": get_log(since)}
@router.post("/api/log/clear")
def api_log_clear():
    clear_log()
    return {"ok": True}
@router.post("/api/log/export")
def api_log_export():
    lines = get_log(0)
    log_dir = Path("log")
    log_dir.mkdir(exist_ok=True)
    configured_timezone, timezone_label = resolve_configured_timezone(
        (load_app_config_validated().get("system") or {})
    )
    ts = now_in_configured_timezone(configured_timezone).strftime("%Y%m%d_%H%M%S")
    filename = log_dir / f"debug_{ts}.txt"
    def fmt_time(t):
        if t is None:
            return ""
        return timestamp_in_configured_timezone(
            t,
            configured_timezone,
        ).strftime("%Y-%m-%d %H:%M:%S")
    content = "\n".join(
        f"{fmt_time(e.get('t'))} [{e.get('level', 'info')}] {e.get('msg', '')}"
        for e in lines
    ) + f"\n# timezone: {timezone_label}\n"
    filename.write_text(content, encoding="utf-8")
    return {"ok": True, "path": str(filename), "lines": len(lines)}
@router.get("/api/plan")
def api_plan():
    return {"plan": get_plan()}
@router.get("/api/pending_payment")
def api_pending_payment():
    return {"pending": get_pending_payment()}
@router.post("/api/confirm_payment")
def api_confirm_payment(body: ConfirmBody):
    confirm_payment(body.ok)
    set_pending_payment(None)
    return {"ok": True}
'''
    if body.ok:
        # 点击「已完成支付」后，自动向配置邮箱（2545875330@qq.com）发送
        # 一封主题与正文均为「已确认成功付款」的邮件，不阻塞本次确认。
        threading.Thread(target=_send_payment_confirmed_mail, daemon=True).start()
    return {"ok": True}
def _send_payment_confirmed_mail() -> None:
    try:
        sent = send_payment_confirmed_email(load_app_config_validated())
        if sent:
            log("已自动发送「已确认成功付款」邮件到配置邮箱", "info", "payment")
        else:
            log(
                "「已确认成功付款」邮件发送失败：请检查系统设置中邮箱账号/授权码是否填写，且邮箱已开启 SMTP 服务",
                "warn",
                "payment",
            )
    except Exception as e:
        log(f"发送「已确认成功付款」邮件异常: {e}", "warn", "payment")
'''

@router.post("/api/send_payment_confirmed_mail")
def api_send_payment_confirmed_mail():
    """
    手动发送「已确认成功付款」邮件。
    不修改订单状态，不执行支付确认。
    """

    threading.Thread(
        target=_send_payment_confirmed_mail,
        daemon=True
    ).start()

    return {
        "ok": True
    }
def _send_payment_confirmed_mail() -> None:
    try:
        sent = send_payment_confirmed_email(
            load_app_config_validated()
        )

        if sent:
            log(
                "已发送「已确认成功付款」邮件到配置邮箱",
                "info",
                "payment"
            )
        else:
            log(
                "「已确认成功付款」邮件发送失败：请检查系统设置中邮箱账号/授权码是否填写，且邮箱已开启 SMTP 服务",
                "warn",
                "payment"
            )

    except Exception as e:
        log(
            f"发送「已确认成功付款」邮件异常: {e}",
            "warn",
            "payment"
        )