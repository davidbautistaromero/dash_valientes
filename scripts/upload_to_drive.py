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

def check_folder_is_shared_drive():
    """Check if the folder is on a Shared Drive"""
    try:
        folder_info = drive.files().get(
            fileId=FOLDER_ID, 
            fields='id,name,driveId,capabilities',
            supportsAllDrives=True
        ).execute()
        
        print(f"Folder name: {folder_info.get('name')}")
        print(f"Folder ID: {folder_info.get('id')}")
        print(f"Drive ID: {folder_info.get('driveId', 'None - This is a PERSONAL Drive folder!')}")
        
        if 'driveId' not in folder_info:
            print("\n⚠️  ERROR: This folder is NOT on a Shared Drive!")
            print("Service accounts cannot upload to personal Drive folders.")
            print("\nSOLUTION:")
            print("1. Create a Shared Drive in Google Workspace")
            print("2. Create a folder in that Shared Drive")
            print("3. Share the Shared Drive with your service account email")
            print("4. Update GDRIVE_FOLDER_ID to the new folder ID")
            return False
        else:
            print("✓ Folder is on a Shared Drive - should work!")
            return True
    except Exception as e:
        print(f"Error checking folder: {e}")
        return False

def upload_xlsx(local_path, filename):
    # busca archivo existente
    q = f"name='{filename}' and '{FOLDER_ID}' in parents"
    files = drive.files().list(
        q=q, 
        fields='files(id)', 
        supportsAllDrives=True, 
        includeItemsFromAllDrives=True
    ).execute().get('files',[])
    media = MediaFileUpload(local_path, mimetype='application/vnd.ms-excel')
    if files:
        drive.files().update(
            fileId=files[0]['id'], 
            media_body=media,
            supportsAllDrives=True
        ).execute()
    else:
        meta = {'name': filename, 'parents':[FOLDER_ID]}
        drive.files().create(
            body=meta, 
            media_body=media, 
            fields='id',
            supportsAllDrives=True
        ).execute()

if __name__=='__main__':
    print("Checking folder configuration...")
    if not check_folder_is_shared_drive():
        print("\n❌ Cannot proceed - folder is not on a Shared Drive")
        exit(1)
    
    print("\nUploading files...")
    upload_xlsx("Conteo_de_Victimas_ESCNNA_Fiscalia.xlsx","Conteo_de_Victimas_ESCNNA_Fiscalia.xlsx")
    upload_xlsx("proyecciones_pob_2005_2050.xlsx","proyecciones_pob_2005_2050.xlsx")
    print("✓ Upload complete!")
