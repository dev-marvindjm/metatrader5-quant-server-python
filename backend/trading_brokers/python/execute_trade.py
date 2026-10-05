import sys
import json
import asyncio
import os

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

# pyrefly: ignore [missing-import]
from logger_config import setup_logging, get_logger
setup_logging(redirect_stdio=False)
logger = get_logger("execute_trade")

def load_dynamic_broker(broker_code: str, credentials: dict):
    import importlib.util
    import inspect
    
    brokers_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "brokers")
    file_path = os.path.join(brokers_dir, f"{broker_code}.py")
    if not os.path.exists(file_path):
        return None
        
    if brokers_dir not in sys.path:
        sys.path.append(brokers_dir)
        
    spec = importlib.util.spec_from_file_location(broker_code, file_path)
    if spec is None or spec.loader is None:
        return None
        
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    
    # pyrefly: ignore [missing-import]
    from models.base_broker import BaseBroker, MarketBaseBroker
    
    for name, obj in inspect.getmembers(module, inspect.isclass):
        if issubclass(obj, BaseBroker) and obj not in (BaseBroker, MarketBaseBroker):
            try:
                sig = inspect.signature(obj.__init__)
                kwargs = {}
                for param_name, param in sig.parameters.items():
                    if param_name == "self":
                        continue
                    if param_name in credentials:
                        val = credentials[param_name]
                        if param_name == "login" and val is not None:
                            try:
                                val = int(val)
                            except:
                                pass
                        kwargs[param_name] = val
                    elif param.default == inspect.Parameter.empty:
                        kwargs[param_name] = None
                
                if any(p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values()):
                    kwargs.update(credentials)
                
                return obj(**kwargs)
            except Exception as e:
                try:
                    return obj(**credentials)
                except Exception as inner_e:
                    raise Exception(f"Failed to instantiate {name}: {str(e)} / {str(inner_e)}")
            
    return None

async def main():
    try:
        input_data = sys.stdin.read()
        if not input_data.strip():
            print(json.dumps({"success": False, "error": "No input provided"}))
            return
        
        params = json.loads(input_data)
        broker_code = params.get("broker")
        credentials = params.get("credentials", {})
        action = params.get("action", "").lower()
        asset = params.get("asset")
        amount = float(params.get("amount", 1.0))
        duration = params.get("duration")
        sl = params.get("sl")
        tp = params.get("tp")
        entry_price = params.get("entry_price")
        entry_range = params.get("entry_range")
        verify_price = params.get("verify_price", False)
        
        if action in ["connect", "login", "test", "ping"]:
            action_type = "connect"
        elif action in ["price", "get_price", "quote", "check_price"]:
            action_type = "price"
        elif action in ["buy", "call", "up"]:
            action_type = "buy"
        elif action in ["sell", "put", "down"]:
            action_type = "sell"
        else:
            print(json.dumps({"success": False, "error": f"Invalid action: {action}"}))
            return

        broker = None
        try:
            if broker_code == "quotex":
                # pyrefly: ignore [missing-import]
                from models.quotex import QuotexBroker
                email = credentials.get("email") or credentials.get("login") or credentials.get("username")
                password = credentials.get("password")
                account_mode = credentials.get("account_mode", "PRACTICE")
                broker = QuotexBroker(email=email, password=password, account_mode=account_mode)
            elif broker_code == "pocketoption":
                # pyrefly: ignore [missing-import]
                from models.pocketoption import PocketOptionBroker
                ssid = credentials.get("ssid")
                broker = PocketOptionBroker(ssid=ssid)
            elif broker_code == "iqoption":
                # pyrefly: ignore [missing-import]
                from models.iqoption import IQOptionBroker
                email = credentials.get("email") or credentials.get("login") or credentials.get("username")
                password = credentials.get("password")
                account_mode = credentials.get("account_mode", "PRACTICE")
                broker = IQOptionBroker(email=email, password=password, account_mode=account_mode)
            elif broker_code in ["metatrader5", "mt5", "metatrader", "metatrader5_mac", "mt5_mac"]:
                try:
                    login_val = int(credentials.get("login") or credentials.get("account_id") or os.environ.get("MT5_ACCOUNT") or os.environ.get("MT5_LOGIN") or 0)
                except (ValueError, TypeError):
                    login_val = 0
                password = credentials.get("password") or os.environ.get("MT5_PASSWD") or os.environ.get("MT5_PASSWORD") or os.environ.get("MT5_PASSW")
                server = credentials.get("server") or os.environ.get("MT5_SERVER")
                path = credentials.get("path") or os.environ.get("MT5_PATH")

                if sys.platform.startswith(("darwin", "linux")) or broker_code in ["metatrader5_mac", "mt5_mac"]:
                    # pyrefly: ignore [missing-import]
                    from models.metatrader5_mac import MetaTrader5MacBroker
                    host = credentials.get("host") or os.environ.get("MT5_BRIDGE_HOST") or "127.0.0.1"
                    port_val = credentials.get("port") or os.environ.get("MT5_MAC_PORT_API") or os.environ.get("MT5_BRIDGE_PORT") or 18812
                    try:
                        port_int = int(port_val)
                    except (ValueError, TypeError):
                        port_int = 18812
                    broker = MetaTrader5MacBroker(login=login_val, password=password, server=server, path=path, host=host, port=port_int)
                else:
                    # pyrefly: ignore [missing-import]
                    from models.metatrader5 import MetaTrader5Broker
                    broker = MetaTrader5Broker(login=login_val, password=password, server=server, path=path)
            else:
                broker = load_dynamic_broker(broker_code, credentials)
        except ImportError as ie:
            print(json.dumps({"success": False, "error": f"Missing Python dependency: {ie.name or str(ie)}. Please install it using pip."}))
            return
        except Exception as dyn_err:
            print(json.dumps({"success": False, "error": f"Error initializing broker {broker_code}: {str(dyn_err)}"}))
            return
        
        if not broker:
            print(json.dumps({"success": False, "error": f"Unsupported or not found broker: {broker_code}"}))
            return

        try:
            connected = await broker.connect()
        except Exception as conn_err:
            print(json.dumps({"success": False, "error": f"Connection error for {broker_code}: {str(conn_err)}"}))
            return

        if not connected:
            print(json.dumps({"success": False, "error": f"Connection failed to broker {broker_code}"}))
            return
        
        if action_type == "connect":
            try:
                balance = await broker.get_balance()
            except Exception:
                balance = 0.0
            print(json.dumps({
                "success": True,
                "connected": True,
                "balance": balance,
                "broker": broker_code,
                "error": None
            }))
            await broker.close()
            return

        # Verify and resolve trading symbol before price check or trade execution
        if hasattr(broker, 'verify_and_resolve_symbol'):
            resolved_asset, sym_err = await broker.verify_and_resolve_symbol(asset)
            if not resolved_asset:
                print(json.dumps({
                    "success": False,
                    "error": f"Symbol verification failed: {sym_err}",
                    "asset": asset,
                    "broker": broker_code
                }))
                await broker.close()
                return
            asset = resolved_asset

        if action_type == "price":
            try:
                current_p = await broker.get_current_price(asset)
                if current_p is not None:
                    print(json.dumps({
                        "success": True,
                        "price": current_p,
                        "asset": asset,
                        "broker": broker_code,
                        "error": None
                    }))
                else:
                    print(json.dumps({
                        "success": False,
                        "price": None,
                        "asset": asset,
                        "broker": broker_code,
                        "error": f"Could not retrieve price for {asset} from broker {broker_code}"
                    }))
            except Exception as e:
                print(json.dumps({
                    "success": False,
                    "price": None,
                    "asset": asset,
                    "broker": broker_code,
                    "error": str(e)
                }))
            await broker.close()
            return

        current_market_price = None
        price_verified = None

        # Verify entry price if specified in params
        if entry_range is not None or entry_price is not None or verify_price:
            try:
                current_market_price = await broker.get_current_price(asset)
                if current_market_price is not None:
                    tol = float(params.get("tolerance", 0.0001))
                    
                    if entry_range is not None and isinstance(entry_range, (list, tuple)) and len(entry_range) >= 2:
                        p1, p2 = float(entry_range[0]), float(entry_range[1])
                        min_p, max_p = min(p1, p2) - tol, max(p1, p2) + tol
                        if not (min_p <= current_market_price <= max_p):
                            print(json.dumps({
                                "success": False,
                                "error": f"Market price {current_market_price} is outside entry range [{p1}, {p2}]",
                                "current_price": current_market_price,
                                "price_verified": False
                            }))
                            await broker.close()
                            return
                        price_verified = True
                        
                    elif entry_price is not None:
                        target_p = float(entry_price)
                        if action_type == "buy" and current_market_price > target_p + tol:
                            print(json.dumps({
                                "success": False,
                                "error": f"Market price {current_market_price} is above target buy entry {target_p}",
                                "current_price": current_market_price,
                                "price_verified": False
                            }))
                            await broker.close()
                            return
                        elif action_type == "sell" and current_market_price < target_p - tol:
                            print(json.dumps({
                                "success": False,
                                "error": f"Market price {current_market_price} is below target sell entry {target_p}",
                                "current_price": current_market_price,
                                "price_verified": False
                            }))
                            await broker.close()
                            return
                        price_verified = True
            except Exception as pe:
                logger.warning(f"Error during price verification: {pe}")
        
        trade_id = None
        if hasattr(broker, 'buy_market') and (sl is not None or tp is not None):
            sl = float(sl) if sl is not None else None
            tp = float(tp) if tp is not None else None
            if action_type == "buy":
                trade_id = await broker.buy_market(asset, amount, sl=sl, tp=tp)
            else:
                trade_id = await broker.sell_market(asset, amount, sl=sl, tp=tp)
        else:
            duration_val = int(duration) if duration is not None else 60
            if action_type == "buy":
                trade_id = await broker.buy(asset, amount, duration_val)
            else:
                trade_id = await broker.sell(asset, amount, duration_val)
        
        if not trade_id:
            print(json.dumps({"success": False, "error": "Trade execution returned no trade ID"}))
            await broker.close()
            return
            
        try:
            balance = await broker.get_balance()
        except:
            balance = 0.0
        
        result = "pending"
        if duration and int(duration) <= 300:
            await asyncio.sleep(int(duration) + 2)
            try:
                win = await broker.get_trade_result(trade_id)
                result = "win" if win else "loss"
            except Exception as e:
                result = f"error: {str(e)}"
        
        print(json.dumps({
            "success": True,
            "trade_id": str(trade_id),
            "result": result,
            "balance_after": balance,
            "current_price": current_market_price,
            "price_verified": price_verified,
            "error": None
        }))
        
        await broker.close()

    except Exception as e:
        import traceback
        print(json.dumps({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }))

if __name__ == "__main__":
    asyncio.run(main())
