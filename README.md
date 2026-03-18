# Observatorio ESCNNA — Dashboard Web

Dashboard interactivo para el análisis de la **Explotación Sexual Comercial de Niñas, Niños y Adolescentes (ESCNNA)** y la **Trata de Personas con NNA** en Colombia.

Reemplaza un flujo anterior basado en Google Drive + Tableau por una solución completamente gratuita, de código abierto y desplegable en la nube.

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
GitHub Actions (cron)
        │
        ▼
  scripts/etl.py          ← Descarga y transforma datos
        │
        ├── data/victimas.csv
        ├── data/poblacion_depto.csv
        └── data/poblacion_mpio.csv
                │
                ▼
         scripts/app.py   ← Dash app (Python + Plotly)
                │
                ▼
           Render.com      ← Hosting gratuito (Web Service)
```

El ETL se ejecuta automáticamente dos veces al mes via GitHub Actions. Los datos quedan como CSV versionados en el repositorio. Render redespliega la app automáticamente al detectar el nuevo commit.

---

## Fuentes de información

### 1. SPOA — Fiscalía General de la Nación
- **Qué contiene:** Registros de casos de delitos sexuales, libertad individual y trata de personas
- **Acceso:** API pública Socrata (`www.datos.gov.co`, dataset `4mnf-va5w`)
- **Delitos incluidos:** 23 tipos de delito relacionados con ESCNNA y trata de personas con NNA, clasificados según artículos del Código Penal colombiano (Arts. 141, 188, 213–219A)
- **Variables clave:** año de denuncia, departamento, municipio, delito, grupo etario, sexo, estado del caso, condición LGBTIQ+, etnia

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
- **CRS original:** ESRI:103599 (proyección local Colombia)
- **Uso:** Base para los mapas coropléticos

---

## Pipeline ETL

El script `scripts/etl.py` ejecuta tres procesos en secuencia:

### `etl_spoa_process()`
1. Extrae registros via API Socrata filtrando por `grupo_delito`
2. Clasifica y estandariza los 23 tipos de delito ESCNNA
3. Descarta registros adultos para delitos que no aplican a NNA
4. Clasifica víctimas por grupo etario (NIÑA-NIÑO / ADOLESCENTE / ADULTO)
5. Normaliza nombres de departamento para que coincidan con el GeoJSON
6. Agrega `cod_dep` (2 dígitos DIVIPOLA) y `cod_mun` (5 dígitos DIVIPOLA) como llaves foráneas
7. Exporta `data/victimas.csv`

**Cobertura de llaves foráneas:** 100% para `cod_dep`, ~100% para `cod_mun` (los únicos sin match son registros `SIN DATO`).

**Normalización de municipios:** Se aplican tres capas en orden:
1. Mapeo manual para ~25 municipios con nombres oficiales distintos (ej. `CALI` → `Santiago de Cali`, `CARTAGENA` → `Cartagena De Indias`)
2. Normalización sin tildes para ~40 municipios con errores tipográficos
3. Match exacto case-insensitive para el resto

### `etl_dane_depto_process()`
1. Descarga los dos archivos departamentales del DANE
2. Filtra por `ÁREA GEOGRÁFICA == 'Total'`
3. Suma edades 0–17 para obtener la población menor de 18 años
4. Agrega `cod_dep` y exporta `data/poblacion_depto.csv`

### `etl_dane_mpio_process()`
Maneja dos archivos con estructuras distintas:

| Archivo | Hoja | Header | Total_0 en col |
|---|---|---|---|
| 2005–2017 | `NuevaMpal` | Fila 12, cols 2/3 invertidas | 178 |
| 2018–2042 | `PobMunicipalxÁreaSexoEdad` | Doble header filas 8–9 | 211 |

> **Nota importante:** En el archivo 2005–2017 las columnas de código y nombre del municipio están invertidas respecto al archivo 2018–2042. El ETL maneja esto con el parámetro `code_col`/`name_col`. Los códigos del archivo 2005–2017 también requieren zero-padding a 5 dígitos.

Exporta `data/poblacion_mpio.csv` con `cod_mun` como llave.

---

## Creación de los mapas

Los mapas usan polígonos oficiales del IGAC en formato GeoJSON (almacenados en `assets/geojson/`).

### Proceso de conversión (único, ya ejecutado)

```python
import geopandas as gpd

# Departamentos
gdf = gpd.read_file('assets/departamentos-col.gdb', layer='Depto')
gdf = gdf.to_crs(epsg=4326)          # WGS84 para web
gdf = gdf[gdf['DeCodigo'] != '00']   # Eliminar área en litigio
# Bogotá D.C. se extrae de la capa de municipios (cod 11001)
# y se agrega como departamento con cod_dep='11'
gdf.to_file('assets/geojson/departamentos.geojson', driver='GeoJSON')

# Municipios
gdf = gpd.read_file('assets/municipios-col.gdb', layer='Munpio')
gdf = gdf.to_crs(epsg=4326)
gdf['geometry'] = gdf['geometry'].simplify(0.005, preserve_topology=True)
gdf.to_file('assets/geojson/municipios.geojson', driver='GeoJSON')
```

Los archivos `.gdb` originales fueron eliminados del repositorio tras la conversión (peso reducido de ~100MB a ~2.75MB total).

### Tamaños finales

| Archivo | Registros | Tamaño |
|---|---|---|
| `departamentos.geojson` | 33 | 0.29 MB |
| `municipios.geojson` | 1,123 | 2.46 MB |

Los polígonos se unen con los datos via `cod_dep` (departamentos) y `cod_mun` (municipios), ambos en formato DIVIPOLA.

---

## Lógica del dashboard

### Filtros
| Filtro | Campo | Tipo |
|---|---|---|
| Año de denuncia | `anio_denuncia` | RangeSlider (2010–2026) |
| Grupo de delito | `grupo_delito` | Dropdown multi |
| Departamento | `departamento_hecho` | Dropdown simple |
| Delito | `delito` | Dropdown multi |

### Mapas (4)
| Mapa | Métrica |
|---|---|
| Víctimas por departamento | `SUM(total_victimas_nna)` agrupado por `cod_dep` |
| Tasa ESCNNA por departamento | `SUM(victimas_nna) / SUM(población_menor_18) × 100.000` |
| Víctimas por municipio | `SUM(total_victimas_nna)` agrupado por `cod_mun` |
| Tasa ESCNNA por municipio | `SUM(victimas_nna) / SUM(población_menor_18) × 100.000` |

**Definición de Tasa ESCNNA:**
> Total de víctimas NNA en un territorio y periodo dado, dividido entre la población menor de 18 años en ese mismo territorio y periodo, multiplicado por 100.000.

La tasa se calcula sobre el rango completo de años seleccionados (suma de víctimas / suma de población), no como promedio de tasas anuales.

Cuando se selecciona un departamento en el filtro, los mapas de municipio hacen zoom automáticamente a ese departamento.

### Gráficas (6)
| Gráfica | Tipo | Variables |
|---|---|---|
| Histórico de casos y víctimas | Barras + línea (eje dual) | `anio_denuncia`, `total_victimas` |
| Víctimas por sexo | Donut | `sexo`, `total_victimas` |
| Víctimas por grupo etario | Barras horizontales | `grupo_etario`, `total_victimas` |
| Identidad y etnia | Barras horizontales | `aplica_lgbti`, `indigena`, `afrodescendiente` |
| Estado de casos por año | Barras apiladas | `estado`, `anio_denuncia` |
| Top 15 delitos por víctimas NNA | Barras horizontales | `delito`, `total_victimas_nna` |

### Paleta de colores

**Primarios:** `#0c71e3` `#003893` `#17365d` `#0f4861` `#366091`

**Secundarios:** `#02c3ec` `#d5d5ff` `#C3a5fb` `#7030a0` `#FFde59` `#ff1616` `#2ecc71` `#f39c12` `#1abc9c` `#95a5a6`

---

## Estructura del proyecto

```
dash_valientes/
├── scripts/
│   ├── etl.py              # Pipeline ETL completo
│   └── app.py              # Dash web app
├── assets/
│   └── geojson/
│       ├── departamentos.geojson
│       └── municipios.geojson
├── data/                   # Generado por el ETL (en .gitignore)
│   ├── victimas.csv
│   ├── poblacion_depto.csv
│   └── poblacion_mpio.csv
├── .github/
│   └── workflows/
│       └── data_pipeline.yml
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
# Windows (CMD)
C:\venv\web-app-valientes\Scripts\activate.bat

# Windows (PowerShell)
C:\venv\web-app-valientes\Scripts\Activate.ps1

# macOS / Linux
source C:/venv/web-app-valientes/bin/activate
```

### 3. Instalar dependencias

```bash
pip install -r requirements.txt
```

### 4. Ejecutar el ETL (genera los CSV en `data/`)

```bash
python scripts/etl.py
```

> El ETL descarga ~200 MB de archivos del DANE. Tarda entre 5 y 10 minutos dependiendo de la conexión.

### 5. Correr la app localmente

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
3. Los datos (`data/`) deben estar presentes en el repo o el ETL debe correr como paso de build

Render redespliega automáticamente cada vez que se hace push al branch principal.

> **Nota:** La carpeta `data/` está en `.gitignore` para desarrollo local, pero debe incluirse en el repositorio para que Render tenga acceso a los datos sin requerir ejecutar el ETL en cada deploy. Considera quitarla del `.gitignore` para producción o configurar el ETL como Build Command.
