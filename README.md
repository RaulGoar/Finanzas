# Finanzas

Gestor financiero personal local, construido con Python, Streamlit, SQLite, SQLAlchemy, Pandas y Plotly. Los datos permanecen en `data/finanzas.db`; la aplicación no almacena credenciales bancarias, no se conecta a entidades y no consulta precios de mercado.

## Ejecutar en GitHub Codespaces

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

Codespaces abrirá la aplicación en el navegador. También se puede instalar con `pip install -r requirements.txt` en un entorno Python ya activo y ejecutar directamente `streamlit run app.py`.

## Configuración

La moneda predeterminada es EUR. Se puede seleccionar otra moneda antes del primer uso mediante la variable de entorno `FINANZAS_CURRENCY` (`EUR`, `USD` o `GBP`). Los importes históricos no se convierten; todos los saldos de cuentas, presupuestos, activos, deudas e inversiones deben registrarse en esa moneda.

La base de datos se puede mover o sustituir con `DATABASE_URL`, por ejemplo `sqlite:////ruta/finanzas.db`. La capa de modelos usa SQLAlchemy y claves foráneas para facilitar una migración posterior a PostgreSQL. No se incluyen credenciales ni claves API.

## Funcionalidades

- Resumen mensual con patrimonio neto, cuentas, ingresos, gastos, ahorro, gráficos interactivos y capturas del patrimonio.
- Cuentas corrientes, de ahorro y efectivo, saldos iniciales, movimientos y transferencias atómicas entre cuentas.
- Ingresos y gastos con categorías personalizadas, filtros, búsqueda, edición, borrado y exportación CSV; reglas recurrentes mensuales procesadas manualmente.
- Presupuestos mensuales por categoría con avisos de consumo y objetivos de ahorro con aportaciones.
- Activos, deudas e inversiones; operaciones de compra/venta con comisiones, coste FIFO, beneficios realizados y no realizados.
- Informes mensuales/anuales y exportación CSV/Excel.
- Copia de seguridad descargable desde el panel lateral.

Los precios de inversión son exclusivamente los introducidos al registrar operaciones. La app no inventa cotizaciones ni integra APIs externas. No se realiza conversión de divisas.

## Pruebas

```bash
pytest
```

Las pruebas usan una base SQLite temporal en memoria y no modifican los datos de la aplicación.

## Estructura

```text
app.py                 Entrada y navegación Streamlit
config/                Configuración
database/              Motor, sesiones y copias de seguridad
models/                Entidades SQLAlchemy
services/              Validaciones y lógica financiera
pages/                 Vistas de la aplicación
components/            Componentes visuales compartidos
tests/                 Pruebas automatizadas
data/                  Base SQLite local (ignorada por Git)
```

## Consideraciones

La base local no está cifrada. Protege el dispositivo y las copias descargadas como cualquier archivo con información financiera. No se guardan contraseñas bancarias ni se realizan conexiones bancarias. Las reglas recurrentes generan apuntes contables al procesarlas, pero nunca realizan pagos ni conectan con bancos.
