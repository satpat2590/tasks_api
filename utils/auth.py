from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials

security = HTTPBasic()

def verify_credentials(credentials: HTTPBasicCredentials = Depends(security)):
    if credentials.username != "your_username" or credentials.password != "your_password":
        raise HTTPException(status_code=401)
    return credentials

