---
title: Observatorio ESCNNA Colombia
emoji: 🇨🇴
colorFrom: blue
colorTo: red
sdk: docker
app_port: 7860
pinned: false
---

# Aplicativo de Cifras sobre ESCNNA y Trata con NNA en Colombia

Dashboard interactivo para el análisis de la **Explotación Sexual Comercial de Niñas, Niños y Adolescentes (ESCNNA)** y la **Trata de Personas con NNA** en Colombia.

Desarrollado por el **Observatorio ESCNNA-Valientes Colombia**. Reemplaza un flujo anterior basado en Google Drive + Tableau por una solución completamente gratuita, de código abierto y desplegable en la nube.

---

## Tabla de contenido

1. [Arquitectura general](#arquitectura-general)
2. [Fuentes de información](#fuentes-de-información)
3. [Pipeline ETL](#pipeline-etl)
4. [Creación de los mapas](#creación-de-los-mapas)
5. [Lógica del dashboard](#lógica-del-dashboard)
6. [Estructura del proyecto](#estructura-del-proyecto)
7. [Instalación y uso local](#instalación-y-uso-local)
8. [Despliegue en Render](#despliegue-en-render)

---

## Arquitectura general

```
GitHub Actions (cron — 2 veces/mes)
        │
        ▼
  scripts/etl.py          ← Descarga y transforma datos
        │
        ├── data/victimas.csv
        ├── data/poblacion_depto.csv
        └── data/poblacion_mpio.csv
                │
                ▼  (commit + push automático al repo)
         scripts/app.py   ← Dash app (Python + Plotly)
                │
                ▼
           Render.com      ← Hosting gratuito (Web Service)
```

El ETL se ejecuta automáticamente dos veces al mes via GitHub Actions, actualiza los CSV en el repositorio con un commit automático, y Render redespliega la app al detectar el nuevo push.

---

## Fuentes de información

### 1. SPOA — Fiscalía General de la Nación
- **Qué contiene:** Registros de casos de delitos sexuales, libertad individual y trata de personas con NNA
- **Acceso:** API pública Socrata (`www.datos.gov.co`, dataset `4mnf-va5w`)
- **Grupos de delito incluidos:**
  - **ESCNNA:** delitos sexuales (Arts. 141, 213–219A Código Penal)
  - **Trata de Personas:** trata de personas y delitos contra la libertad individual con NNA (Art. 188)
- **Variables clave:** año de denuncia, departamento, municipio, delito, grupo etario, sexo, etapa del caso, condición LGBTIQ+, etnia

### 2. DANE — Proyecciones de Población

| Nivel | Periodo | Archivo |
|---|---|---|
| Departamental | 2005–2019 | `DCD-area-sexo-edad-proypoblacion-dep-2005-2019.xlsx` |
| Departamental | 2020–2050 | `DCD-area-sexo-edad-proyepoblacion-dep-2020-2050-ActPostCOVID-19.xlsx` |
| Municipal | 2005–2017 | `DCD-area-sexo-edad-proypoblacion-Mun-2005-2017_VP.xlsx` |
| Municipal | 2018–2042 | `PPED-AreaSexoEdadMun-2018-2042_VP.xlsx` |

- **Variable usada:** Población total de 0 a 17 años (edades simples `Total_0` a `Total_17`)
- **Fuente:** [dane.gov.co — Proyecciones de Población](https://www.dane.gov.co/index.php/estadisticas-por-tema/demografia-y-poblacion/proyecciones-de-poblacion)

### 3. IGAC — Cartografía oficial de Colombia
- **Formato original:** File Geodatabase (`.gdb`) con capas `Depto` y `Munpio`
- **CRS original:** ESRI:103599 (proyección local Colombia) → convertido a EPSG:4326 (WGS84)
- **Uso:** Base para los mapas coropléticos

---

## Pipeline ETL

El script `scripts/etl.py` ejecuta tres procesos en secuencia:

### `etl_spoa_process()`
1. Extrae registros via API Socrata filtrando por `grupo_delito`
2. Clasifica y estandariza los 23 tipos de delito ESCNNA y Trata
3. Descarta registros adultos para delitos que no aplican a NNA
4. Clasifica víctimas por grupo etario (NIÑA-NIÑO / ADOLESCENTE / ADULTO)
5. Normaliza nombres de departamento para que coincidan con el GeoJSON
6. Agrega `cod_dep` (2 dígitos DIVIPOLA) y `cod_mun` (5 dígitos DIVIPOLA) como llaves foráneas
7. Exporta `data/victimas.csv`

**Cobertura de llaves foráneas:** 100% `cod_dep`, ~100% `cod_mun` (sin match solo registros `SIN DATO`).

**Normalización de municipios (3 capas):**
1. Mapeo manual para ~25 municipios con nombres oficiales distintos (ej. `CALI` → `Santiago de Cali`, `CARTAGENA` → `Cartagena De Indias`)
2. Normalización sin tildes para ~40 municipios con variaciones tipográficas
3. Match exacto case-insensitive para el resto

### `etl_dane_depto_process()`
1. Descarga los dos archivos departamentales del DANE
2. Filtra por `ÁREA GEOGRÁFICA == 'Total'`
3. Suma edades 0–17 para obtener la población menor de 18 años
4. Agrega `cod_dep` con zero-padding a 2 dígitos y exporta `data/poblacion_depto.csv`

> **Nota técnica:** Los archivos DANE almacenan `cod_dep` sin zero-padding (ej. `5` en lugar de `05`). El ETL aplica `.str.zfill(2)` al leer de vuelta los Excel intermedios para garantizar consistencia con el `cod_dep` de `victimas.csv`.

### `etl_dane_mpio_process()`
Maneja dos archivos con estructuras distintas:

| Archivo | Hoja | Header | `Total_0` en col |
|---|---|---|---|
| 2005–2017 | `NuevaMpal` | Fila 12, cols código/nombre **invertidas** | 178 |
| 2018–2042 | `PobMunicipalxÁreaSexoEdad` | Doble header filas 8–9 | 211 |

> En el archivo 2005–2017 las columnas de código y nombre del municipio están invertidas respecto al archivo 2018–2042. El ETL lo maneja con los parámetros `code_col`/`name_col`. Los códigos también requieren zero-padding a 5 dígitos.

Exporta `data/poblacion_mpio.csv` con `cod_mun` como llave.

---

## Creación de los mapas

Los mapas usan polígonos oficiales del IGAC en formato GeoJSON (almacenados en `assets/geojson/`). La conversión fue un proceso único ya ejecutado.

### Proceso de conversión

```python
import geopandas as gpd

# Departamentos (incluye Bogotá D.C. extraída de la capa de municipios cod=11001)
gdf = gpd.read_file('assets/departamentos-col.gdb', layer='Depto')
gdf = gdf.to_crs(epsg=4326)
gdf['geometry'] = gdf['geometry'].simplify(0.01, preserve_topology=True)
gdf.to_file('assets/geojson/departamentos.geojson', driver='GeoJSON')

# Municipios
gdf = gpd.read_file('assets/municipios-col.gdb', layer='Munpio')
gdf = gdf.to_crs(epsg=4326)
gdf['geometry'] = gdf['geometry'].simplify(0.005, preserve_topology=True)
gdf.to_file('assets/geojson/municipios.geojson', driver='GeoJSON')
```

Los archivos `.gdb` originales fueron eliminados tras la conversión (peso reducido de ~100 MB a ~2.75 MB).

### Tamaños finales

| Archivo | Polígonos | Tamaño |
|---|---|---|
| `departamentos.geojson` | 33 | 0.29 MB |
| `municipios.geojson` | 1,123 | 2.46 MB |

Los polígonos se unen con los datos via `cod_dep` y `cod_mun` (DIVIPOLA). Los polígonos **sin datos** aparecen en el mapa en gris neutro con tooltip "Sin datos" (implementado con dos trazas `go.Choropleth` apiladas). Los bounds de cada mapa se precalculan al inicio de la app para que el mapa llene el espacio disponible.

---

## Lógica del dashboard

### Filtros

| Filtro | Campo origen | Tipo |
|---|---|---|
| Año de denuncia | `anio_denuncia` | RangeSlider |
| Grupo de delito | `grupo_delito` | Dropdown multi — `ESCNNA` / `Trata de Personas` |
| Departamento | `departamento_hecho` | Dropdown simple |
| Delito | `delito` | Dropdown multi |

> El filtro de año **no afecta** los gráficos históricos (se usan siempre todos los años para mostrar la serie completa).

### Sección: Casos y Víctimas

| Componente | Descripción |
|---|---|
| KPIs | Casos registrados y total víctimas en el período seleccionado |
| Histórico | Barras (víctimas) + línea (casos) en eje Y único — no afectado por filtro de año |
| Mapa departamentos | Coroplético conteo víctimas NNA + tabla lateral con todos los departamentos |
| Mapa municipios | Coroplético conteo víctimas NNA + tabla lateral top 20 municipios |
| Víctimas por sexo | Donut |
| Víctimas por grupo etario | Barras horizontales con porcentaje en tooltip |
| Diversidad sexual | Donut LGBTIQ+ vs No identificado |
| Diversidad étnica | Donut Ninguna / Indígena / Afrodescendiente |

### Sección: Tasa de ESCNNA

**Definición:**
> Número de víctimas NNA en un territorio y período, dividido entre la población menor de 18 años en ese mismo territorio y período, multiplicado por 100.000.

La tasa se calcula sobre el rango de años seleccionado (suma acumulada), no como promedio de tasas anuales.

| Componente | Descripción |
|---|---|
| Mapa tasa departamentos | Coroplético tasa de ESCNNA + tabla lateral |
| Mapa tasa municipios | Coroplético tasa de ESCNNA + tabla top 20 |
| Histórico tasa | Línea con área rellena — no afectado por filtro de año |

### Sección: Justicia y Delitos

| Componente | Descripción |
|---|---|
| Top 15 delitos | Barras horizontales con porcentaje en tooltip |
| Etapa de casos por año | Barras apiladas por `etapa_caso` |

### Paleta de colores

**Primarios:** `#0c71e3` · `#003893` · `#17365d` · `#0f4861` · `#366091`

**Secundarios:** `#02c3ec` · `#d5d5ff` · `#C3a5fb` · `#7030a0` · `#FFde59` · `#ff1616` · `#2ecc71` · `#f39c12` · `#1abc9c` · `#95a5a6`

---

## Estructura del proyecto

```
dash_valientes/
├── scripts/
│   ├── etl.py              # Pipeline ETL — SPOA + DANE
│   └── app.py              # Dash web app
├── assets/
│   └── geojson/
│       ├── departamentos.geojson
│       └── municipios.geojson
├── data/                   # CSVs versionados en el repo (actualizados por ETL)
│   ├── victimas.csv
│   ├── poblacion_depto.csv
│   └── poblacion_mpio.csv
├── .github/
│   └── workflows/
│       └── data_pipeline.yml   # Cron: ejecuta ETL y hace commit de datos
├── requirements.txt
├── .gitignore
└── README.md
```

---

## Instalación y uso local

### 1. Crear el ambiente virtual

```bash
python -m venv C:\venv\web-app-valientes
```

### 2. Activar el ambiente

```bash
# Windows (PowerShell)
C:\venv\web-app-valientes\Scripts\Activate.ps1

# Windows (CMD)
C:\venv\web-app-valientes\Scripts\activate.bat

# macOS / Linux
source C:/venv/web-app-valientes/bin/activate
```

### 3. Instalar dependencias

```bash
pip install -r requirements.txt
```

### 4. (Opcional) Correr el ETL para actualizar los datos

```bash
python scripts/etl.py
```

> Descarga ~200 MB del DANE. Tarda entre 5 y 10 minutos según la conexión. Los CSV ya están en el repositorio, por lo que este paso solo es necesario para actualizar los datos.

### 5. Correr la app

```bash
python scripts/app.py
```

Abre el browser en **http://127.0.0.1:8050**

---

## Despliegue en Render

1. Conectar el repositorio de GitHub a [render.com](https://render.com) como **Web Service**
2. Configurar:
   - **Runtime:** Python
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `gunicorn scripts.app:server`
3. Activar **Auto-Deploy** en el branch principal — Render redesplegará automáticamente cada vez que el ETL haga push de datos nuevos

### Automatización del ETL

El workflow `.github/workflows/data_pipeline.yml` se ejecuta automáticamente los lunes primero y tercero de cada mes (2 AM UTC) y también puede dispararse manualmente desde GitHub Actions. Al finalizar, hace commit y push de los CSV actualizados al repositorio, lo que activa el redespliegue en Render.

```yaml
# Disparadores
on:
  schedule:
    - cron: '0 2 1-7,15-21 * 1'  # Lunes 1°-7° y 15°-21° de cada mes
  workflow_dispatch:               # Ejecución manual
```
