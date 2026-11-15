import ftplib
import os
import ssl

server = os.environ.get('HOSTINGER_FTP_SERVER', '145.79.30.251')
user = os.environ.get('HOSTINGER_FTP_USERNAME', 'u701878864')
pwd = os.environ.get('HOSTINGER_FTP_PASSWORD', '')

ftps = ftplib.FTP_TLS()
ftps.connect(server, 21)
ftps.login(user, pwd)
ftps.prot_p()
print("PWD:", ftps.pwd())
print("LIST of root:")
ftps.dir()
try:
    print("\nLIST of domains:")
    ftps.dir('domains')
except Exception as e:
    print("No domains dir:", e)

try:
    print("\nLIST of public_html:")
    ftps.dir('public_html')
except Exception as e:
    print("Error listing public_html:", e)

ftps.quit()
