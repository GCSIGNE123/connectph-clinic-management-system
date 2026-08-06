# Starts the portable dev Postgres instance provisioned for CONNECT.PH local development.
# Data directory: D:\Projects\CMS\.devdb\data
# Port: 5433
# Superuser role: clinic_user / clinic_password (also has role "postgres" via trust auth)
#
# Usage: powershell -File backend/scripts/start_dev_postgres.ps1
# Stop with: D:\Projects\CMS\.devdb\pgsql\bin\pg_ctl.exe -D D:\Projects\CMS\.devdb\data stop

$pgBin = "D:\Projects\CMS\.devdb\pgsql\bin"
$dataDir = "D:\Projects\CMS\.devdb\data"
$logFile = "D:\Projects\CMS\.devdb\logfile.txt"

& "$pgBin\pg_ctl.exe" -D $dataDir -l $logFile -o "-p 5433" start
& "$pgBin\pg_isready.exe" -p 5433
