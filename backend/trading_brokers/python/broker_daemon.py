import sys
import os
import json
import asyncio
import logging
from typing import Dict, Any, Tuple, Optional

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

def load_env():
    candidates = [
        os.path.join(os.getcwd(), ".env"),
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".env"),
        os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"),
    ]
    for path in candidates:
        if os.path.exists(path):
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        if not line or line.startswith('#') or '=' not in line:
                            continue
                        k, v = line.split('=', 1)
                        v = v.strip('"\'')
                        if k.strip() not in os.environ:
                            os.environ[k.strip()] = v
            except Exception:
                pass

load_env()

from execute_trade import load_dynamic_broker

from logger_config import setup_logging, get_logger

setup_logging(redirect_stdio=True)
logger = get_logger("broker_daemon")

# Active in-memory sessions dictionary
# Key: f"{broker_code}:{account_identifier}:{mode}" -> Broker instance
sessions: Dict[str, Any] = {}
session_locks: Dict[str, asyncio.Lock] = {}

def get_session_key(broker_code: str, credentials: dict) -> str:
    b_code = str(broker_code).lower()
    account_id = (
        credentials.get("login") or
        credentials.get("account_id") or
        credentials.get("user") or
        credentials.get("username") or
        credentials.get("email") or
        credentials.get("ssid") or
        (os.environ.get("QUOTEX_EMAIL") if b_code == "quotex" else None) or
        (os.environ.get("IQOPTION_EMAIL") if b_code in ["iqoption", "iq_option", "iq"] else None) or
        ("env_ssid" if b_code in ["pocketoption", "pocket_option", "pocket"] and os.environ.get("POCKET_OPTION_SSID") else None) or
        ((os.environ.get("MT5_ACCOUNT") or os.environ.get("MT5_LOGIN")) if b_code in ["metatrader5", "mt5", "metatrader", "metatrader5_mac", "mt5_mac"] else None) or
        "default"
    )
    mode = credentials.get("account_mode", "PRACTICE")
    return f"{b_code}:{account_id}:{mode}"

async def get_or_create_broker(broker_code: str, credentials: dict) -> Tuple[Optional[Any], Optional[str]]:
    key = get_session_key(broker_code, credentials)
    
    if key not in session_locks:
        session_locks[key] = asyncio.Lock()
        
    async with session_locks[key]:
        broker = sessions.get(key)
        if broker is not None:
            try:
                if await broker.is_connected():
                    logger.info(f"Reusing persistent in-memory session for {key}")
                    return broker, None
            except Exception as e:
                logger.warning(f"Session check error for {key}: {e}")
            
            # Connection lost or check failed -> purge old session
            try:
                await broker.close()
            except Exception:
                pass
            sessions.pop(key, None)

        # Create & connect new broker instance
        logger.info(f"Connecting new session for {key}...")
        broker = None
        b_code = str(broker_code).lower()

        try:
            if b_code == "quotex":
                from models.quotex import QuotexBroker
                email = credentials.get("email") or credentials.get("login") or credentials.get("username") or os.environ.get("QUOTEX_EMAIL")
                password = credentials.get("password") or os.environ.get("QUOTEX_PASSW") or os.environ.get("QUOTEX_PASSWORD")
                account_mode = credentials.get("account_mode", "PRACTICE")
                broker = QuotexBroker(email=email, password=password, account_mode=account_mode)

            elif b_code in ["pocketoption", "pocket_option", "pocket"]:
                from models.pocketoption import PocketOptionBroker
                ssid = credentials.get("ssid") or os.environ.get("POCKET_OPTION_SSID") or os.environ.get("POCKETOPTION_SSID")
                broker = PocketOptionBroker(ssid=ssid)

            elif b_code in ["iqoption", "iq_option", "iq"]:
                from models.iqoption import IQOptionBroker
                email = credentials.get("email") or credentials.get("login") or credentials.get("username") or os.environ.get("IQOPTION_EMAIL")
                password = credentials.get("password") or os.environ.get("IQOPTION_PASSW") or os.environ.get("IQOPTION_PASSWORD")
                account_mode = credentials.get("account_mode", "PRACTICE")
                broker = IQOptionBroker(email=email, password=password, account_mode=account_mode)

            elif b_code in ["metatrader5", "mt5", "metatrader", "metatrader5_mac", "mt5_mac"]:
                try:
                    login_val = int(credentials.get("login") or credentials.get("account_id") or os.environ.get("MT5_ACCOUNT") or os.environ.get("MT5_LOGIN") or 0)
                except (ValueError, TypeError):
                    login_val = 0
                password = credentials.get("password") or os.environ.get("MT5_PASSWD") or os.environ.get("MT5_PASSWORD") or os.environ.get("MT5_PASSW")
                server = credentials.get("server") or os.environ.get("MT5_SERVER")
                path = credentials.get("path") or os.environ.get("MT5_PATH")

                if sys.platform.startswith(("darwin", "linux")) or b_code in ["metatrader5_mac", "mt5_mac"]:
                    from models.metatrader5_mac import MetaTrader5MacBroker
                    host = credentials.get("host") or os.environ.get("MT5_BRIDGE_HOST") or "127.0.0.1"
                    port_val = credentials.get("port") or os.environ.get("MT5_MAC_PORT_API") or os.environ.get("MT5_BRIDGE_PORT") or 18812
                    try:
                        port_int = int(port_val)
                    except (ValueError, TypeError):
                        port_int = 18812
                    broker = MetaTrader5MacBroker(login=login_val, password=password, server=server, path=path, host=host, port=port_int)
                else:
                    from models.metatrader5 import MetaTrader5Broker
                    broker = MetaTrader5Broker(login=login_val, password=password, server=server, path=path)

            else:
                broker = load_dynamic_broker(broker_code, credentials)
        except ImportError as ie:
            err_msg = f"Missing Python dependency: {ie.name or str(ie)}. Please install it using pip."
            logger.error(err_msg)
            return None, err_msg
        except Exception as e:
            err_msg = f"Error initializing broker {broker_code}: {str(e)}"
            logger.error(err_msg)
            return None, err_msg

        if not broker:
            return None, f"Unsupported or not found broker: {broker_code}"

        try:
            connected = await broker.connect()
        except Exception as conn_err:
            err_msg = f"Connection error for {broker_code}: {str(conn_err)}"
            logger.error(err_msg)
            return None, err_msg

        if connected:
            sessions[key] = broker
            logger.info(f"Successfully authenticated and stored session for {key}")
            return broker, None
        else:
            err_msg = f"Authentication failed for broker {broker_code}. Check credentials or broker status."
            logger.error(err_msg)
            return None, err_msg

async def handle_request(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
    try:
        header_lines = []
        content_length = 0
        while True:
            line = await reader.readline()
            if not line or line == b'\r\n' or line == b'\n':
                break
            header_str = line.decode('utf-8', errors='ignore')
            header_lines.append(header_str)
            if header_str.lower().startswith('content-length:'):
                content_length = int(header_str.split(':')[1].strip())

        request_line = header_lines[0] if header_lines else ""
        parts = request_line.split()
        method = parts[0] if parts else "GET"
        path = parts[1] if len(parts) > 1 else "/"

        body_bytes = b""
        if content_length > 0:
            body_bytes = await reader.readexactly(content_length)

        body_json = {}
        if body_bytes:
            try:
                body_json = json.loads(body_bytes.decode('utf-8'))
            except Exception:
                pass

        response_data = {}
        status_code = 200

        if path == "/health" or path == "/status":
            response_data = {
                "status": "ok",
                "active_sessions": list(sessions.keys()),
                "total_sessions": len(sessions)
            }

        elif path == "/connect":
            broker_code = body_json.get("broker", "")
            credentials = body_json.get("credentials", {})
            broker, err_msg = await get_or_create_broker(broker_code, credentials)
            if broker:
                try:
                    balance = await broker.get_balance()
                except Exception:
                    balance = 0.0
                response_data = {
                    "success": True,
                    "connected": True,
                    "balance": balance,
                    "session_key": get_session_key(broker_code, credentials)
                }
            else:
                status_code = 400
                response_data = {
                    "success": False,
                    "connected": False,
                    "error": err_msg or f"Failed to authenticate with broker {broker_code}"
                }

        elif path == "/price":
            broker_code = body_json.get("broker", "")
            credentials = body_json.get("credentials", {})
            asset = body_json.get("asset")
            if not asset:
                status_code = 400
                response_data = {"success": False, "error": "Asset not specified"}
            else:
                broker, err_msg = await get_or_create_broker(broker_code, credentials)
                if not broker:
                    status_code = 400
                    response_data = {"success": False, "error": err_msg or f"Session not connected for broker {broker_code}"}
                else:
                    try:
                        price = await broker.get_current_price(asset)
                        if price is not None:
                            response_data = {
                                "success": True,
                                "price": price,
                                "asset": asset,
                                "broker": broker_code,
                                "error": None
                            }
                        else:
                            status_code = 400
                            response_data = {
                                "success": False,
                                "price": None,
                                "asset": asset,
                                "broker": broker_code,
                                "error": f"Failed to retrieve price for {asset} from broker {broker_code}"
                            }
                    except Exception as e:
                        status_code = 400
                        response_data = {"success": False, "error": str(e)}

        elif path == "/trade":
            broker_code = body_json.get("broker", "")
            credentials = body_json.get("credentials", {})
            action = body_json.get("action")
            if action is None:
                status_code = 400
                response_data = {"success": False, "error": "Action not specified"}
            else:
                asset = body_json.get("asset")
                if asset is None:
                    status_code = 400
                    response_data = {"success": False, "error": "Asset not specified"}
                else:
                    amount = float(body_json.get("amount", 1.0))
                    duration = body_json.get("duration")
                    tp = body_json.get("tp")
                    sl = body_json.get("sl")
                    entry_price = body_json.get("entry_price")
                    entry_range = body_json.get("entry_range")
                    verify_price = body_json.get("verify_price", False)
                    price_timeout_sec = float(body_json.get("price_timeout") or 60.0)
                    metric_id = body_json.get("metric_id")

                    broker, err_msg = await get_or_create_broker(broker_code, credentials)
                    if not broker:
                        status_code = 400
                        response_data = {"success": False, "error": err_msg or f"Session not connected for broker {broker_code}"}
                    else:
                        current_market_price = None
                        price_verified = None
                        price_rejected = False

                        if entry_range is not None or entry_price is not None or verify_price:
                            tol = float(body_json.get("tolerance", 0.0001))
                            action_type_check = "buy" if action.lower() in ["buy", "call", "up"] else "sell"
                            start_wait = asyncio.get_event_loop().time()
                            price_matched = False
                            last_checked_price = None

                            logger.info(f"[{broker_code}] Monitoring price for {asset} (target: price={entry_price}, range={entry_range}, timeout={price_timeout_sec}s)...")

                            while (asyncio.get_event_loop().time() - start_wait) <= price_timeout_sec:
                                try:
                                    current_market_price = await broker.get_current_price(asset)
                                    if current_market_price is not None and current_market_price > 0:
                                        last_checked_price = current_market_price
                                        is_valid = False

                                        if entry_range is not None and isinstance(entry_range, (list, tuple)) and len(entry_range) >= 2:
                                            p1, p2 = float(entry_range[0]), float(entry_range[1])
                                            min_p, max_p = min(p1, p2) - tol, max(p1, p2) + tol
                                            if min_p <= current_market_price <= max_p:
                                                is_valid = True
                                        elif entry_price is not None:
                                            target_p = float(entry_price)
                                            if action_type_check == "buy" and current_market_price <= target_p + tol:
                                                is_valid = True
                                            elif action_type_check == "sell" and current_market_price >= target_p - tol:
                                                is_valid = True
                                        else:
                                            is_valid = True

                                        if is_valid:
                                            price_matched = True
                                            price_verified = True
                                            break
                                except Exception as pe:
                                    logger.warning(f"Error checking price during wait loop: {pe}")

                                await asyncio.sleep(1.0)

                            if not price_matched:
                                price_rejected = True
                                status_code = 200
                                response_data = {
                                    "success": False,
                                    "result": "timeout",
                                    "error": f"Price timeout ({price_timeout_sec:.0f}s): Target price was not reached in time. Operation cancelled.",
                                    "current_price": last_checked_price,
                                    "price_verified": False,
                                    "timeout": True
                                }

                        if not price_rejected:
                            trade_id = None
                            action_type = "buy" if action.lower() in ["buy", "call", "up"] else "sell"

                            if hasattr(broker, 'buy_market') and (sl is not None or tp is not None):
                                sl_val = float(sl) if sl is not None else None
                                tp_val = float(tp) if tp is not None else None
                                if action_type == "buy":
                                    trade_id = await broker.buy_market(asset, amount, sl=sl_val, tp=tp_val)
                                else:
                                    trade_id = await broker.sell_market(asset, amount, sl=sl_val, tp=tp_val)

                                if not trade_id:
                                    status_code = 400
                                    response_data = {"success": False, "error": "Trade execution returned no trade ID"}
                                else:
                                    try:
                                        balance = await broker.get_balance()
                                    except Exception:
                                        balance = 0.0

                                    response_data = {
                                        "success": True,
                                        "trade_id": str(trade_id),
                                        "result": "open",
                                        "balance_after": balance,
                                        "current_price": current_market_price,
                                        "price_verified": price_verified,
                                        "error": None
                                    }
                            else:
                                duration_val = int(duration) if duration is not None else 60
                                gale_steps = int(body_json.get("gale_steps") or 0)
                                gale_multiplier = float(body_json.get("gale_multiplier") or 2.0)

                                current_step_amount = amount
                                total_invested = current_step_amount
                                last_trade_id = None
                                final_result = "loss"
                                step_won = None

                                for step in range(gale_steps + 1):
                                    step_lbl = f"Gale {step}" if step > 0 else "Base"
                                    if step > 0 and metric_id:
                                        logger.info(f"[{broker_code}] Trade #{metric_id} entering Martingale Gale {step}...")
                                        try:
                                            def _notify_martingale(mid, st):
                                                try:
                                                    import sqlite3
                                                    c = sqlite3.connect('trading_signals.db')
                                                    c.execute("UPDATE operation_metrics SET result = 'martingale' WHERE id = ?", (mid,))
                                                    c.commit()
                                                    c.close()
                                                except Exception:
                                                    pass
                                                try:
                                                    import urllib.request
                                                    req_m = urllib.request.Request(
                                                        "http://127.0.0.1:8081/api/trade/status",
                                                        data=json.dumps({"id": mid, "status": "martingale", "result": "martingale", "step": st}).encode("utf-8"),
                                                        headers={"Content-Type": "application/json"}
                                                    )
                                                    urllib.request.urlopen(req_m, timeout=1.5)
                                                except Exception:
                                                    pass
                                            asyncio.create_task(asyncio.to_thread(_notify_martingale, metric_id, step))
                                        except Exception as n_err:
                                            logger.warning(f"Could not notify martingale state: {n_err}")

                                    logger.info(f"[{broker_code}] Executing {step_lbl} binary trade: {action_type} {asset} amount={current_step_amount} duration={duration_val}s")
                                    if action_type == "buy":
                                        last_trade_id = await broker.buy(asset, current_step_amount, duration_val)
                                    else:
                                        last_trade_id = await broker.sell(asset, current_step_amount, duration_val)

                                    if not last_trade_id:
                                        logger.error(f"[{broker_code}] {step_lbl} trade returned no trade ID")
                                        if step == 0:
                                            final_result = "error"
                                        break

                                    # Wait for candle expiration + 2s buffer for broker settlement
                                    await asyncio.sleep(duration_val + 2)

                                    try:
                                        won = await broker.get_trade_result(last_trade_id)
                                    except Exception as e:
                                        logger.warning(f"Error checking trade result for {last_trade_id}: {e}")
                                        won = False

                                    if won:
                                        final_result = "win"
                                        step_won = step
                                        logger.info(f"[{broker_code}] {step_lbl} WON! Sequence finished.")
                                        break
                                    else:
                                        logger.info(f"[{broker_code}] {step_lbl} LOST.")
                                        if step < gale_steps:
                                            current_step_amount = round(current_step_amount * gale_multiplier, 2)
                                            total_invested += current_step_amount
                                        else:
                                            final_result = "loss"

                                if final_result == "error" or not last_trade_id:
                                    status_code = 400
                                    response_data = {"success": False, "error": "Trade execution returned no trade ID"}
                                else:
                                    try:
                                        balance = await broker.get_balance()
                                    except Exception:
                                        balance = 0.0

                                    profit_loss = 0.0
                                    if final_result == "win":
                                        payout_ratio = 0.85
                                        profit_loss = round((current_step_amount * payout_ratio) - (total_invested - current_step_amount), 2)
                                    elif final_result == "loss":
                                        profit_loss = round(-total_invested, 2)

                                    response_data = {
                                        "success": True,
                                        "trade_id": str(last_trade_id),
                                        "result": final_result,
                                        "profit_loss": profit_loss,
                                        "executed_amount": total_invested,
                                        "gale_step_won": step_won,
                                        "balance_after": balance,
                                        "current_price": current_market_price,
                                        "price_verified": price_verified,
                                        "error": None
                                    }

        elif path == "/order_status":
            broker_code = body_json.get("broker", "")
            credentials = body_json.get("credentials", {})
            ticket = body_json.get("ticket")
            broker, err_msg = await get_or_create_broker(broker_code, credentials)
            if not broker:
                status_code = 400
                response_data = {"success": False, "error": err_msg or f"Session not connected for broker {broker_code}"}
            else:
                if hasattr(broker, "get_order_status"):
                    status_info = await broker.get_order_status(ticket)
                    response_data = {"success": True, **status_info}
                else:
                    won = await broker.get_trade_result(ticket)
                    response_data = {
                        "success": True,
                        "status": "closed" if won is not None else "open",
                        "result": "win" if won else "loss",
                        "profit": 0.0
                    }

        elif path == "/disconnect":
            broker_code = body_json.get("broker", "")
            credentials = body_json.get("credentials", {})
            key = get_session_key(broker_code, credentials)
            broker = sessions.pop(key, None)
            if broker:
                try:
                    await broker.close()
                except Exception:
                    pass
            response_data = {"success": True, "message": f"Disconnected session {key}"}

        else:
            status_code = 404
            response_data = {"error": "Not Found"}

        resp_body = json.dumps(response_data).encode('utf-8')
        status_text = "OK" if status_code == 200 else ("Bad Request" if status_code == 400 else "Not Found")
        
        response_header = (
            f"HTTP/1.1 {status_code} {status_text}\r\n"
            f"Content-Type: application/json; charset=utf-8\r\n"
            f"Content-Length: {len(resp_body)}\r\n"
            f"Connection: close\r\n\r\n"
        ).encode('utf-8')

        writer.write(response_header + resp_body)
        await writer.drain()
    except Exception as e:
        logger.exception(f"Error handling request: {e}")
        try:
            err_resp = json.dumps({"success": False, "error": str(e)}).encode('utf-8')
            writer.write(
                f"HTTP/1.1 500 Internal Server Error\r\nContent-Type: application/json; charset=utf-8\r\nContent-Length: {len(err_resp)}\r\nConnection: close\r\n\r\n".encode('utf-8') + err_resp
            )
            await writer.drain()
        except Exception:
            pass
    finally:
        writer.close()
        await writer.wait_closed()

async def keepalive_loop():
    """Background task to ping active broker sessions every 30s and keep connections alive."""
    while True:
        await asyncio.sleep(30)
        for key, broker in list(sessions.items()):
            try:
                connected = await broker.is_connected()
                if not connected:
                    logger.info(f"Keepalive: session {key} disconnected, purging.")
                    sessions.pop(key, None)
                else:
                    logger.debug(f"Keepalive: session {key} active.")
            except Exception as e:
                logger.warning(f"Keepalive ping failed for {key}: {e}")
                sessions.pop(key, None)

async def main():
    port = 8090
    server = await asyncio.start_server(handle_request, "127.0.0.1", port)
    logger.info(f"Persistent Broker Session Daemon listening on http://127.0.0.1:{port}")
    
    asyncio.create_task(keepalive_loop())

    async with server:
        await server.serve_forever()

if __name__ == "__main__":
    asyncio.run(main())
