import io
import json
import unicodedata
import pandas as pd
import numpy as np
import os

import sodapy
from sodapy import Socrata

import requests
import urllib.parse
from datetime import datetime


# ── Normalización de nombres ───────────────────────────────────────────────────

# Nombres de departamento en SPOA/DANE que difieren del GeoJSON
DEPT_NAME_MAP = {
    'BOGOTÁ, D. C.':               'Bogotá, D.C.',
    'Boyaca':                       'Boyacá',
    'Archipiélago de San Andrés':  'Archipiélago de San Andrés, Providencia y Santa Catalina',
    'Quindio':                      'Quindío',
}

# Nombres de municipio en SPOA que difieren del GeoJSON (no solucionables solo con tildes)
MPIO_MANUAL_MAP = {
    'BARRANCO MINAS':              '94343',  # Barrancominas (Guainía)
    'CALI':                        '76001',  # Santiago de Cali
    'CARTAGENA':                   '13001',  # Cartagena de Indias
    'CERRO SAN ANTONIO':           '47161',  # Cerro de San Antonio (Magdalena)
    'CÚCUTA':                      '54001',  # San José de Cúcuta
    'DON MATÍAS':                  '05237',  # Donmatías (Antioquia)
    'EL CARMEN DE ATRATO':         '27245',  # El Carmen (Chocó)
    'EL CARMEN DE CHUCURÍ':        '68235',  # El Carmen (Santander)
    'EL CARMEN DE VIBORAL':        '05148',  # Carmen de Viboral (Antioquia)
    'EL SANTUARIO':                '05697',  # Santuario (Antioquia)
    'EL TABLÓN DE GÓMEZ':          '52258',  # El Tablón (Nariño)
    'FUENTE DE ORO':               '50287',  # Fuentedeoro (Meta)
    'GUADALAJARA DE BUGA':         '76111',  # Buga (Valle del Cauca)
    'GÜICÁN':                      '15332',  # Güicán de la Sierra (Boyacá)
    'LA MONTAÑITA':                '18410',  # Montañita (Caquetá)
    'PIENDAMÓ':                    '19548',  # Piendamó Tunia (Cauca)
    'RETIRO':                      '05607',  # El Retiro (Antioquia)
    'RÍO VIEJO':                   '13600',  # Rioviejo (Bolívar)
    'SAN ANDRÉS SOTAVENTO':        '23670',  # San Andrés de Sotavento (Córdoba)
    'SAN LUIS DE SINCÉ':           '70742',  # Sincé (Sucre)
    'SANTAFÉ DE ANTIOQUIA':        '05042',  # Santa Fe de Antioquia
    'SANTIAGO DE TOLÚ':            '70820',  # Tolú (Sucre)
    'TOLÚ VIEJO':                  '70823',  # Toluviejo (Sucre)
    'VILLA DE LEYVA':              '15407',  # Villa de Leiva (Boyacá)
    'VILLA DE SAN DIEGO DE UBATE': '25843',  # Ubaté (Cundinamarca)
}

AGES_0_17 = [f'Total_{i}' for i in range(18)]


def _strip_accents(s):
    return ''.join(c for c in unicodedata.normalize('NFD', s)
                   if unicodedata.category(c) != 'Mn').upper()


def _build_geo_lookups():
    """Lee los GeoJSON y construye dicts nombre→código para deptos y municipios."""
    with open('assets/geojson/departamentos.geojson', encoding='utf-8') as f:
        geo_dep = json.load(f)
    with open('assets/geojson/municipios.geojson', encoding='utf-8') as f:
        geo_mun = json.load(f)

    dep_lookup = {feat['properties']['nombre']: feat['properties']['cod_dep']
                  for feat in geo_dep['features']}

    # Municipios: mapa por nombre normalizado (sin tildes, upper) → cod_mun
    mun_lookup = {_strip_accents(feat['properties']['nombre']): feat['properties']['cod_mun']
                  for feat in geo_mun['features']}

    return dep_lookup, mun_lookup


def _get_cod_mun(name, mun_lookup):
    """Resuelve cod_mun para un nombre de municipio con 3 capas de fallback."""
    if not isinstance(name, str) or name.strip().upper() == 'SIN DATO':
        return None
    upper = name.strip().upper()
    # 1. Mapeo manual
    if upper in MPIO_MANUAL_MAP:
        return MPIO_MANUAL_MAP[upper]
    # 2. Nombre normalizado (sin tildes)
    return mun_lookup.get(_strip_accents(name))


# ── SPOA ───────────────────────────────────────────────────────────────────────

def etl_spoa_process():
    # Extract
    categories = ('DELITOS SEXUALES',
                  'LIBERTAD INDIVIDUAL Y OTRAS GARANTIAS',
                  'TRATA DE PERSONAS')
    client = Socrata("www.datos.gov.co", None)
    results = client.get("4mnf-va5w",
                         limit=500000,
                         where=f"grupo_delito in {str(categories)}")
    results_df = pd.DataFrame.from_records(results)

    # Transform
    delito = results_df['delito'].str.split("AGRAVADO ", n=1, expand=True)
    results_df = results_df.drop(columns='delito')

    escnna = pd.concat([results_df, delito.rename(columns={0: "delito", 1: "agravante"})],
                        axis=1)

    escnna['delito'] = escnna['delito'].apply(lambda x: x.strip().upper())

    escnna = escnna.loc[(escnna['delito'].str.contains('CONSTREÑIMIENTO')) |
                        (escnna['delito'].str.contains('DEMANDA')) |
                        (escnna['delito'].str.contains('ESTIMULO')) |
                        (escnna['delito'].str.contains('INDUCCION')) |
                        (escnna['delito'].str.contains('PROSTITUCION')) |
                        (escnna['delito'].str.contains('PORNOGRAFIA')) |
                        (escnna['delito'].str.contains('PROXENETISMO')) |
                        (escnna['delito'].str.contains('TRATA DE PERSONAS')) |
                        (escnna['delito'].str.contains('TRAFICO')) |
                        (escnna['delito'].str.contains('TURISMO')) |
                        (escnna['delito'].str.contains('UTILIZAC')), :]

    escnna.loc[escnna['delito'].str.contains('CONSTREÑIMIENTO'), 'delito'] = 'CONSTREÑIMIENTO A LA PROSTITUCION ART. 214'
    escnna.loc[escnna['delito'].str.contains('DEMANDA'), 'delito'] = 'DEMANDA DE EXPLOT.SEX. COMERC. MENOR DE 18 AÑOS ART. 217A'
    escnna.loc[escnna['delito'].str.contains('ESTIMULO'), 'delito'] = 'ESTIMULO A LA PROSTITUCION DE MENORES. ART. 217'
    escnna.loc[escnna['delito'].str.contains('INDUCCION'), 'delito'] = 'INDUCCION A LA PROSTITUCION ART. 213'
    escnna.loc[escnna['delito'].str.contains('PORNOGRAFIA'), 'delito'] = 'PORNOGRAFIA CON MENORES ART. 218'
    escnna.loc[escnna['delito'].str.contains('PROSTITUCION FORZADA O ESCLAVITUD SEXUAL'), 'delito'] = 'PROSTITUCION FORZADA O ESCLAVITUD SEXUAL ART. 141'
    escnna.loc[escnna['delito'].str.contains('PROXENETISMO'), 'delito'] = 'PROXENETISMO CON MENOR DE EDAD ART. 213A'
    escnna.loc[(escnna['delito'].str.contains('TRATA')) | (escnna['delito'].str.contains('TRAFICO')), 'delito'] = escnna['delito'].apply(lambda x: x.replace(' C.P.', ''))
    escnna.loc[escnna['delito'].str.contains('TRAFICO DE MIGRANTES'), 'delito'] = 'TRAFICO DE MIGRANTES ART. 188'
    escnna.loc[escnna['delito'].str.contains('TRAFICO DE NIÑAS'), 'delito'] = 'TRAFICO DE NIÑAS, NIÑOS Y ADOLESCENTES ART 188C'
    escnna.loc[escnna['delito'].str.contains('188B'), 'delito'] = 'TRATA DE PERSONAS ART. 188B'
    escnna.loc[escnna['delito'].str.contains('TURISMO'), 'delito'] = 'TURISMO SEXUAL. ART. 219'
    escnna.loc[escnna['delito'].str.contains('UTILIZAC'), 'delito'] = 'UTILIZAC.O FACILITAC.MEDIOS DE COMUNICAC.PARA OFRECER ACTIV. SEXUALES CON MENORES DE 18 AÑOS ART. 219A'

    delitos_nna = ['CONSTREÑIMIENTO A LA PROSTITUCION ART. 214',
                   'INDUCCION A LA PROSTITUCION ART. 213',
                   'PROSTITUCION FORZADA EN PERSONA PROTEGIDA ART. 141',
                   'PROSTITUCION FORZADA O ESCLAVITUD SEXUAL ART. 141',
                   'TRAFICO DE MIGRANTES ART. 188',
                   'TRATA DE PERSONAS ART. 188A',
                   'TRATA DE PERSONAS ART. 188A CUANDO LA FINALIDAD SEA EL MATRIMONIO SERVIL',
                   'TRATA DE PERSONAS ART. 188A CUANDO LA FINALIDAD SEA EL TRABAJO FORZADO',
                   'TRATA DE PERSONAS ART. 188A CUANDO LA FINALIDAD SEA LA ESCLAVITUD',
                   'TRATA DE PERSONAS ART. 188A CUANDO LA FINALIDAD SEA LA EXTRACCION DE ORGANOS',
                   'TRATA DE PERSONAS ART. 188A CUANDO LA FINALIDAD SEA LA MENDICIDAD',
                   'TRATA DE PERSONAS ART. 188A CUANDO LA FINALIDAD SEA LA PORNOGRAFÍA',
                   'TRATA DE PERSONAS ART. 188A CUANDO LA FINALIDAD SEA LA PROSTITUCION',
                   'TRATA DE PERSONAS ART. 188A CUANDO LA FINALIDAD SEA LA SERVIDUMBRE',
                   'TRATA DE PERSONAS ART. 188B',
                   'TRATA DE PERSONAS EN PERSONA PROTEGIDA CON FINES DE EXPLOTACION SEXUAL ART. 141B',
                   'TRATA DE PERSONAS TRANSNACIONAL ART. 188A CUANDO LA FINALIDAD SEA LA SERVIDUMBRE',
                   'TURISMO SEXUAL. ART. 219']

    escnna.drop(escnna.loc[(escnna['delito'].isin(delitos_nna)) & (escnna['aplica_nna'] == 'NO')].index, inplace=True)

    escnna['Type'] = 'ESCNNA'
    escnna.loc[(escnna['delito'].str.contains('TRATA')) | (escnna['delito'].str.contains('TRAFICO')), 'Type'] = 'Trata con NNA'

    escnna.loc[escnna['grupo_etario'] == 'Adolescente de 14 a 17 años.', 'grupo_etario'] = 'ADOLESCENTE (14-17 años)'
    escnna.loc[(escnna['grupo_etario'].str.contains('Joven')) | (escnna['grupo_etario'].str.contains('Adulto')), 'grupo_etario'] = 'ADULTO'
    escnna.loc[escnna['grupo_etario'] == 'Niño, Niña. Población de 0 a 13 años.', 'grupo_etario'] = 'NIÑA-NIÑO (0-13 años)'

    escnna.columns = ['criminalidad', 'es_archivo', 'es_preclusion', 'estado', 'etapa_caso',
           'ley', 'pais_hecho', 'departamento_hecho', 'municipio_hecho',
           'seccional', 'anio_hechos', 'anio_entrada', 'anio_denuncia',
           'grupo_delito', 'victima_consumado', 'sexo', 'grupo_etario',
           'pais_nacimiento', 'aplica_lgbti', 'aplica_nna', 'indigena',
           'afrodescendiente', 'total_victimas', 'delito', 'agravante', 'Type']

    escnna['total_victimas'] = pd.to_numeric(escnna['total_victimas'], errors='coerce').fillna(0).astype(int)

    escnna['total_victimas_nna'] = escnna.apply(
        lambda row: row['total_victimas'] if str(row['aplica_nna']).strip().upper() == 'SI' else 0,
        axis=1
    )

    # Normalizar nombres de departamento
    escnna['departamento_hecho'] = escnna['departamento_hecho'].replace(DEPT_NAME_MAP)

    # Agregar foreign keys cod_dep y cod_mun
    dep_lookup, mun_lookup = _build_geo_lookups()
    escnna['cod_dep'] = escnna['departamento_hecho'].map(dep_lookup)
    escnna['cod_mun'] = escnna['municipio_hecho'].apply(lambda x: _get_cod_mun(x, mun_lookup))

    matched_dep = escnna['cod_dep'].notna().sum()
    matched_mun = escnna['cod_mun'].notna().sum()
    print(f"  cod_dep match: {matched_dep}/{len(escnna)} ({matched_dep/len(escnna)*100:.1f}%)")
    print(f"  cod_mun match: {matched_mun}/{len(escnna)} ({matched_mun/len(escnna)*100:.1f}%)")

    # Load
    os.makedirs('data', exist_ok=True)
    escnna.to_csv('data/victimas.csv', index=False, encoding='utf-8-sig')
    print(f"victimas.csv guardado: {len(escnna)} registros")


# ── DANE Departamental ─────────────────────────────────────────────────────────

def _process_dane_depto_file(name, url):
    """Descarga y transforma un archivo de proyecciones departamentales del DANE."""
    excel_url = urllib.parse.unquote(url)
    print(f"Descargando {name} ...")
    response = requests.get(excel_url)
    response.raise_for_status()

    with open(name, "wb") as f:
        f.write(response.content)

    df = pd.read_excel(name)
    df.dropna(inplace=True)

    df.columns = df.iloc[0].reset_index(drop=True).to_list()

    current_year = datetime.now().year

    df_menores = df[df['ÁREA GEOGRÁFICA'] == 'Total'][
        ['DP', 'DPNOM', 'AÑO'] + AGES_0_17
    ].copy()

    df_menores[['AÑO'] + AGES_0_17] = df_menores[['AÑO'] + AGES_0_17].astype(int)
    df_menores['Total'] = df_menores[AGES_0_17].sum(axis=1)
    df_menores = df_menores[df_menores['AÑO'] <= current_year][['DP', 'DPNOM', 'AÑO', 'Total']]
    df_menores['DPNOM'] = df_menores['DPNOM'].replace(DEPT_NAME_MAP)

    # Agregar cod_dep
    dep_lookup, _ = _build_geo_lookups()
    df_menores['cod_dep'] = df_menores['DPNOM'].map(dep_lookup)

    df_menores.to_excel(name, index=False)
    print(f"  {name} procesado: {len(df_menores)} registros")


def etl_dane_depto_process():
    """Descarga proyecciones departamentales DANE y genera data/poblacion_depto.csv."""
    links = {
        "pob_depto_2005_2019.xlsx": r"https%3A%2F%2Fwww.dane.gov.co%2Ffiles%2Fcenso2018%2Fproyecciones-de-poblacion%2FDepartamental%2FDCD-area-sexo-edad-proypoblacion-dep-2005-2019.xlsx",
        "pob_depto_2020_2050.xlsx": r"https%3A%2F%2Fwww.dane.gov.co%2Ffiles%2Fcenso2018%2Fproyecciones-de-poblacion%2FDepartamental%2FDCD-area-sexo-edad-proyepoblacion-dep-2020-2050-ActPostCOVID-19.xlsx",
    }

    for name, url in links.items():
        _process_dane_depto_file(name, url)

    df_2005 = pd.read_excel("pob_depto_2005_2019.xlsx")
    df_2020 = pd.read_excel("pob_depto_2020_2050.xlsx")

    df_combined = pd.concat([df_2005, df_2020], axis=0, ignore_index=True)
    df_combined = df_combined.sort_values(['cod_dep', 'AÑO']).reset_index(drop=True)

    os.makedirs('data', exist_ok=True)
    df_combined.to_csv('data/poblacion_depto.csv', index=False, encoding='utf-8-sig')

    os.remove("pob_depto_2005_2019.xlsx")
    os.remove("pob_depto_2020_2050.xlsx")

    print(f"poblacion_depto.csv guardado: {len(df_combined)} registros")


# ── DANE Municipal ─────────────────────────────────────────────────────────────

def _process_dane_mpio_file(url, sheet_name, skiprows, age_start_col, code_col, name_col):
    """
    Descarga y transforma un archivo de proyecciones municipales del DANE.

    Parámetros:
    - sheet_name:    hoja de datos dentro del Excel
    - skiprows:      filas a saltar antes de los datos (títulos + headers)
    - age_start_col: columna (índice 0-based) donde empieza Total_0
    - code_col:      índice de la columna con el código DIVIPOLA del municipio
    - name_col:      índice de la columna con el nombre del municipio
                     2005-2017: code_col=3, name_col=2  (MPIO y DPMP invertidos)
                     2018-2042: code_col=2, name_col=3
    """
    print(f"Descargando {url.split('/')[-1]} ...")
    response = requests.get(url)
    response.raise_for_status()

    current_year = datetime.now().year

    id_cols  = list(range(6))
    age_cols = list(range(age_start_col, age_start_col + 18))

    df = pd.read_excel(
        io.BytesIO(response.content),
        sheet_name=sheet_name,
        header=None,
        skiprows=skiprows,
        usecols=id_cols + age_cols,
        dtype={0: str, code_col: str}
    )

    rename_map = {
        0: 'DP', 1: 'DPNOM', code_col: 'cod_mun', name_col: 'MPNOM', 4: 'AÑO', 5: 'AREA',
        **{age_start_col + i: f'T{i}' for i in range(18)}
    }
    df = df.rename(columns=rename_map)

    age_col_names = [f'T{i}' for i in range(18)]
    df[['AÑO'] + age_col_names] = df[['AÑO'] + age_col_names].apply(pd.to_numeric, errors='coerce').fillna(0).astype(int)

    df = df[(df['AREA'] == 'Total') & (df['AÑO'] <= current_year)].copy()
    df['Total'] = df[age_col_names].sum(axis=1)

    # Zero-pad cod_mun a 5 dígitos
    df['cod_mun'] = df['cod_mun'].astype(str).str.strip().str.zfill(5)

    df['DPNOM'] = df['DPNOM'].replace(DEPT_NAME_MAP)

    # Agregar cod_dep desde los primeros 2 dígitos del código municipal
    df['cod_dep'] = df['cod_mun'].str[:2]

    df = df[['cod_dep', 'DP', 'DPNOM', 'cod_mun', 'MPNOM', 'AÑO', 'Total']]

    print(f"  Procesado: {len(df)} registros")
    return df


def etl_dane_mpio_process():
    """Descarga proyecciones municipales DANE (con edad) y genera data/poblacion_mpio.csv."""
    # 2005-2017: cols 2=nombre, 3=código (invertidos vs 2018-2042)
    url_2005 = "https://www.dane.gov.co/files/censo2018/proyecciones-de-poblacion/Municipal/DCD-area-sexo-edad-proypoblacion-Mun-2005-2017_VP.xlsx"
    # 2018-2042: cols 2=código, 3=nombre
    url_2018 = "https://www.dane.gov.co/files/censo2018/proyecciones-de-poblacion/Municipal/PPED-AreaSexoEdadMun-2018-2042_VP.xlsx"

    df_2005 = _process_dane_mpio_file(
        url_2005, sheet_name='NuevaMpal', skiprows=12, age_start_col=178,
        code_col=3, name_col=2
    )
    df_2018 = _process_dane_mpio_file(
        url_2018, sheet_name='PobMunicipalxÁreaSexoEdad', skiprows=9, age_start_col=211,
        code_col=2, name_col=3
    )

    df_combined = pd.concat([df_2005, df_2018], axis=0, ignore_index=True)
    df_combined = df_combined.sort_values(['cod_dep', 'cod_mun', 'AÑO']).reset_index(drop=True)

    os.makedirs('data', exist_ok=True)
    df_combined.to_csv('data/poblacion_mpio.csv', index=False, encoding='utf-8-sig')

    print(f"poblacion_mpio.csv guardado: {len(df_combined)} registros")


# ── Ejecución ─────────────────────────────────────────────────────────────────
etl_spoa_process()
etl_dane_depto_process()
etl_dane_mpio_process()
