# Tu Proyecto Personalizado dentro de MetaTrader 5 Docker

Este directorio `./custom_app` está montado como un volumen directo dentro del contenedor Docker en `/custom_app`.

## ¿Cómo funciona?

1. **Código fuente en tiempo real**: Cualquier archivo que agregues o modifiques en esta carpeta se reflejará inmediatamente dentro del contenedor.
2. **Dependencias automáticas**: Si incluyes librerías en `requirements.txt`, los scripts de arranque del contenedor las instalarán en el entorno de Python de Wine la primera vez que se inicie.
3. **Punto de entrada (`CUSTOM_SCRIPT`)**: Por defecto, el contenedor ejecuta `wine python /custom_app/main.py`. Puedes cambiar esto en `.env.standalone` mediante la variable `CUSTOM_SCRIPT` o usar `CUSTOM_COMMAND`.

## Ejecución manual / Desarrollo interactivo

Para entrar al contenedor y ejecutar tus scripts de prueba manualmente:

```bash
docker exec -it mt5-standalone bash
```

Y una vez dentro:

```bash
# Recuerda: MetaTrader5 requiere el Python de Wine (no el de Linux):
wine python /custom_app/main.py
```
