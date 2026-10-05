import os
import sys
import time
import logging
from datetime import datetime

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("CustomMT5App")

try:
    import MetaTrader5 as mt5
except ImportError:
    logger.error("No se pudo importar MetaTrader5. Recuerda ejecutar este script con 'wine python' dentro del contenedor.")
    sys.exit(1)

def main():
    logger.info("=== Iniciando Aplicación Personalizada MetaTrader 5 ===")

    # Obtener variables de entorno
    login_str = os.getenv("MT5_LOGIN", "")
    password = os.getenv("MT5_PASSWORD", "")
    server = os.getenv("MT5_SERVER", "")
    path = os.getenv("MT5_PATH", r"C:\Program Files\MetaTrader 5\terminal64.exe")

    login = int(login_str) if login_str.isdigit() else None

    # Parámetros de inicialización
    init_kwargs = {}
    if path:
        init_kwargs["path"] = path
    if login and password and server:
        init_kwargs["login"] = login
        init_kwargs["password"] = password
        init_kwargs["server"] = server
        logger.info(f"Intentando conectar con cuenta: {login} en el servidor: {server}")
    else:
        logger.info("No se proporcionaron credenciales completas de login/password/server. Conectando a terminal local abierto.")

    # Inicializar MetaTrader 5
    if not mt5.initialize(**init_kwargs):
        error_code = mt5.last_error()
        logger.error(f"Fallo al inicializar MetaTrader 5. Error: {error_code}")
        logger.info("Esperando 10 segundos antes de reintentar...")
        time.sleep(10)
        return

    # Obtener información de la versión de MT5
    version = mt5.version()
    logger.info(f"Conexión exitosa. Versión de MetaTrader 5: {version}")

    # Obtener información de la cuenta
    account_info = mt5.account_info()
    if account_info is not None:
        logger.info(f"--- Datos de la Cuenta ---")
        logger.info(f"Login: {account_info.login}")
        logger.info(f"Servidor: {account_info.server}")
        logger.info(f"Nombre: {account_info.name}")
        logger.info(f"Balance: {account_info.balance} {account_info.currency}")
        logger.info(f"Equidad: {account_info.equity} {account_info.currency}")
        logger.info(f"Apalancamiento: 1:{account_info.leverage}")
    else:
        logger.warning(f"No se pudo obtener la información de la cuenta. Error: {mt5.last_error()}")

    # Bucle principal de ejemplo (puedes reemplazar esto con tu estrategia, bot, FastAPI, etc.)
    logger.info("Iniciando bucle de monitoreo (presiona Ctrl+C para detener)...")
    symbol = "EURUSD"

    # Asegurar que el símbolo esté seleccionado en Market Watch
    if not mt5.symbol_select(symbol, True):
        logger.warning(f"No se pudo seleccionar el símbolo {symbol}.")

    try:
        while True:
            tick = mt5.symbol_info_tick(symbol)
            if tick:
                logger.info(f"[{symbol}] Bid: {tick.bid} | Ask: {tick.ask} | Spread: {(tick.ask - tick.bid):.5f}")
            else:
                logger.info(f"Esperando cotizaciones para {symbol}...")

            time.sleep(5)
    except KeyboardInterrupt:
        logger.info("Deteniendo aplicación...")
    finally:
        mt5.shutdown()
        logger.info("Conexión con MetaTrader 5 cerrada correctamente.")

if __name__ == "__main__":
    main()
