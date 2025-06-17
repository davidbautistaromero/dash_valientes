import os
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

FOLDER_ID = os.getenv('GDRIVE_FOLDER_ID')
SA_FILE  = os.getenv('GCP_SERVICE_ACCOUNT_PATH', 'service_account.json')

creds = service_account.Credentials.from_service_account_file(
    SA_FILE,
    scopes=['https://www.googleapis.com/auth/drive']
)
drive = build('drive','v3',credentials=creds)

def upload_xlsx(local_path, filename):
    # busca archivo existente
    q = f"name='{filename}' and '{FOLDER_ID}' in parents"
    files = drive.files().list(q=q, fields='files(id)').execute().get('files',[])
    media = MediaFileUpload(local_path, mimetype='application/vnd.ms-excel')
    if files:
        drive.files().update(fileId=files[0]['id'], media_body=media).execute()
    else:
        meta = {'name': filename, 'parents':[FOLDER_ID]}
        drive.files().create(body=meta, media_body=media, fields='id').execute()

if __name__=='__main__':
    upload_xlsx("Conteo_de_Victimas_ESCNNA_Fiscalia.xlsx","Conteo_de_Victimas_ESCNNA_Fiscalia.xlsx")
    upload_xlsx("proyecciones_pob_2005_2019.xlsx","proyecciones_pob_2005_2019.xlsx")
    upload_xlsx("proyecciones_pob_2020_2050.xlsx","proyecciones_pob_2020_2050.xlsx")