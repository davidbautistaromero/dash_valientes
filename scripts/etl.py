import pandas as pd
import numpy as np
import os

import sodapy
from sodapy import Socrata

import requests
import urllib.parse
from datetime import datetime


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
    delito = results_df['delito'].str.split("AGRAVADO ", n=1, expand = True)
    results_df = results_df.drop(columns='delito')

    escnna = pd.concat([results_df, delito.rename(columns={0:"delito", 1:"agravante"})], 
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
                        (escnna['delito'].str.contains('UTILIZAC')),:]

    escnna.loc[escnna['delito'].str.contains('CONSTREÑIMIENTO'),'delito'] = 'CONSTREÑIMIENTO A LA PROSTITUCION ART. 214'
    escnna.loc[escnna['delito'].str.contains('DEMANDA'),'delito'] = 'DEMANDA DE EXPLOT.SEX. COMERC. MENOR DE 18 AÑOS ART. 217A'
    escnna.loc[escnna['delito'].str.contains('ESTIMULO'),'delito'] = 'ESTIMULO A LA PROSTITUCION DE MENORES. ART. 217'
    escnna.loc[escnna['delito'].str.contains('INDUCCION'),'delito'] = 'INDUCCION A LA PROSTITUCION ART. 213'
    escnna.loc[escnna['delito'].str.contains('PORNOGRAFIA'),'delito'] = 'PORNOGRAFIA CON MENORES ART. 218'
    escnna.loc[escnna['delito'].str.contains('PROSTITUCION FORZADA O ESCLAVITUD SEXUAL'),'delito'] = 'PROSTITUCION FORZADA O ESCLAVITUD SEXUAL ART. 141'
    escnna.loc[escnna['delito'].str.contains('PROXENETISMO'),'delito'] = 'PROXENETISMO CON MENOR DE EDAD ART. 213A'
    escnna.loc[(escnna['delito'].str.contains('TRATA')) | (escnna['delito'].str.contains('TRAFICO')),'delito'] = escnna['delito'].apply(lambda x: x.replace(' C.P.',''))
    escnna.loc[escnna['delito'].str.contains('TRAFICO DE MIGRANTES'),'delito'] = 'TRAFICO DE MIGRANTES ART. 188'
    escnna.loc[escnna['delito'].str.contains('TRAFICO DE NIÑAS'),'delito'] = 'TRAFICO DE NIÑAS, NIÑOS Y ADOLESCENTES ART 188C'
    escnna.loc[escnna['delito'].str.contains('188B'),'delito'] = 'TRATA DE PERSONAS ART. 188B'
    escnna.loc[escnna['delito'].str.contains('TURISMO'),'delito'] = 'TURISMO SEXUAL. ART. 219'
    escnna.loc[escnna['delito'].str.contains('UTILIZAC'),'delito'] = 'UTILIZAC.O FACILITAC.MEDIOS DE COMUNICAC.PARA OFRECER ACTIV. SEXUALES CON MENORES DE 18 AÑOS ART. 219A'

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

    escnna.drop(escnna.loc[(escnna['delito'].isin(delitos_nna)) & (escnna['aplica_nna']=='NO')].index, inplace=True)

    escnna['Type'] = 'ESCNNA'
    escnna.loc[(escnna['delito'].str.contains('TRATA')) | (escnna['delito'].str.contains('TRAFICO')),'Type'] = 'Trata con NNA'

    escnna.loc[escnna['grupo_etario']=='Adolescente de 14 a 17 años.','grupo_etario'] = 'ADOLESCENTE (14-17 años)'
    escnna.loc[(escnna['grupo_etario'].str.contains('Joven')) | (escnna['grupo_etario'].str.contains('Adulto')),'grupo_etario'] = 'ADULTO'
    escnna.loc[escnna['grupo_etario']=='Niño, Niña. Población de 0 a 13 años.','grupo_etario'] = 'NIÑA-NIÑO (0-13 años)'

    escnna.columns = ['criminalidad', 'es_archivo', 'es_preclusion', 'estado', 'etapa_caso',
           'ley', 'pais_hecho', 'departamento_hecho', 'municipio_hecho',
           'seccional', 'anio_hechos', 'anio_entrada', 'anio_denuncia',
           'grupo_delito', 'victima_consumado', 'sexo', 'grupo_etario',
           'pais_nacimiento', 'aplica_lgbti', 'aplica_nna', 'indigena',
           'afrodescendiente', 'total_victimas', 'delito', 'agravante', 'Type']

    escnna['total_victimas'] = escnna['total_victimas'].astype('int')

    # Load
    escnna.to_excel("Conteo_de_Victimas_ESCNNA_Fiscalia.xlsx", 
                    index=False)
    

def etl_dane_process(links):

       for name, url in links.items():

              ## Extract
    
              excel_url = urllib.parse.unquote(url)
              print(f"URL del archivo Excel: {excel_url}")


              # Descarga el archivo
              print(f"Descargando {name} ...")
              response = requests.get(excel_url)
              response.raise_for_status()

              with open(name, "wb") as f:
                     f.write(response.content) 

              print(f"Archivo guardado como {name}")

              ## Transform

              df = pd.read_excel(name)

              df.dropna(inplace=True)

              new_columns =df.iloc[0].reset_index(drop=True).to_list()

              current_year = datetime.now().year

              df.columns = new_columns

              df_menores = df[(df['ÁREA GEOGRÁFICA'] == 'Total')][['DP','DPNOM','AÑO','Total_0','Total_1','Total_2','Total_3','Total_4','Total_5','Total_6','Total_7','Total_8','Total_9','Total_10','Total_11','Total_12','Total_13','Total_14','Total_15','Total_16','Total_17']]

              df_menores[['AÑO','Total_0','Total_1','Total_2','Total_3','Total_4','Total_5','Total_6','Total_7','Total_8','Total_9','Total_10','Total_11','Total_12','Total_13','Total_14','Total_15','Total_16','Total_17']] = df_menores[['AÑO','Total_0','Total_1','Total_2','Total_3','Total_4','Total_5','Total_6','Total_7','Total_8','Total_9','Total_10','Total_11','Total_12','Total_13','Total_14','Total_15','Total_16','Total_17']].astype(int)

              df_menores['Total'] = df_menores[['Total_0','Total_1','Total_2','Total_3','Total_4','Total_5','Total_6','Total_7','Total_8','Total_9','Total_10','Total_11','Total_12','Total_13','Total_14','Total_15','Total_16','Total_17']].sum(axis=1)

              df_menores = df_menores[df_menores['AÑO'] <= current_year][['DP','DPNOM','AÑO','Total']]

              df_menores['DPNOM'] = np.where(df_menores['DPNOM'] == 'Archipiélago de San Andrés', 'Archipiélago de San Andrés, Providencia y Santa Catalina',
                                          np.where(df_menores['DPNOM']=='Bogotá, D.C.', 'BOGOTÁ, D. C.',
                                                        np.where(df_menores['DPNOM']=='Boyacá','Boyaca',
                                                                      np.where(df_menores['DPNOM']=='Quindio','Quindío', df_menores['DPNOM']))))

              ## Load 
              df_menores.to_excel(name, index=False)

def concat_dane_files():
    """
    Concatena verticalmente los dos archivos de proyecciones de población del DANE
    y elimina los archivos originales.
    """
    try:
        # Leer los dos archivos
        print("Leyendo archivos de proyecciones de población...")
        df_2005_2019 = pd.read_excel("proyecciones_pob_2005_2019.xlsx")
        df_2020_2050 = pd.read_excel("proyecciones_pob_2020_2050.xlsx")
        
        # Concatenar verticalmente
        print("Concatenando archivos...")
        df_combined = pd.concat([df_2005_2019, df_2020_2050], axis=0, ignore_index=True)
        
        # Ordenar por departamento y año para mejor organización
        df_combined = df_combined.sort_values(['DP', 'AÑO']).reset_index(drop=True)
        
        # Guardar archivo combinado
        output_filename = "proyecciones_pob_2005_2050.xlsx"
        print(f"Guardando archivo combinado como {output_filename}...")
        df_combined.to_excel(output_filename, index=False)
        
        # Eliminar archivos originales
        print("Eliminando archivos originales...")
        os.remove("proyecciones_pob_2005_2019.xlsx")
        os.remove("proyecciones_pob_2020_2050.xlsx")
        
        print(f"Proceso completado. Archivo combinado guardado como {output_filename}")
        print(f"Registros en archivo combinado: {len(df_combined)}")
        
        return df_combined
        
    except FileNotFoundError as e:
        print(f"Error: No se encontró uno de los archivos necesarios: {e}")
        return None
    except Exception as e:
        print(f"Error durante la concatenación: {e}")
        return None

# Call the ETL process functions
etl_spoa_process()

links = {"proyecciones_pob_2005_2019.xlsx": r"https%3A%2F%2Fwww.dane.gov.co%2Ffiles%2Fcenso2018%2Fproyecciones-de-poblacion%2FDepartamental%2FDCD-area-sexo-edad-proypoblacion-dep-2005-2019.xlsx",
         "proyecciones_pob_2020_2050.xlsx": r"https%3A%2F%2Fwww.dane.gov.co%2Ffiles%2Fcenso2018%2Fproyecciones-de-poblacion%2FDepartamental%2FDCD-area-sexo-edad-proyepoblacion-dep-2020-2050-ActPostCOVID-19.xlsx"}

etl_dane_process(links)

# Concatenar los archivos del DANE
concat_dane_files()