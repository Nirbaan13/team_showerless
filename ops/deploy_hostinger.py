import ftplib
import os
import sys

def main():
    server = os.environ.get('HOSTINGER_FTP_SERVER', '145.79.30.251')
    user = os.environ.get('HOSTINGER_FTP_USERNAME', 'u701878864')
    pwd = os.environ.get('HOSTINGER_FTP_PASSWORD', '')

    if not pwd:
        print("ERROR: HOSTINGER_FTP_PASSWORD is not set.")
        sys.exit(1)

    print(f"Connecting to {server}:21 as {user} via FTPS...")
    ftps = ftplib.FTP_TLS()
    ftps.connect(server, 21, timeout=30)
    ftps.login(user, pwd)
    ftps.prot_p()
    pwd_dir = ftps.pwd()
    print(f"Logged in successfully. Remote PWD: {pwd_dir}")

    # Remove accidental nested public_html directory if it was created
    try:
        entries = ftps.nlst()
        if 'public_html' in entries or './public_html' in entries:
            print("Cleaning up accidental nested public_html folder...")
            def cleanup_recursive(path):
                try:
                    for item in ftps.nlst(path):
                        if item.endswith('/.') or item.endswith('/..'):
                            continue
                        try:
                            ftps.delete(item)
                        except Exception:
                            cleanup_recursive(item)
                    ftps.rmd(path)
                except Exception as e:
                    print(f"Cleanup warning for {path}: {e}")
            cleanup_recursive('public_html')
    except Exception as e:
        print(f"Check nested dir note: {e}")

    dist_dir = os.path.abspath('frontend/dist')
    if not os.path.isdir(dist_dir):
        print(f"ERROR: Build directory {dist_dir} does not exist.")
        sys.exit(1)

    def upload_recursive(local_base, remote_base=''):
        for item in sorted(os.listdir(local_base)):
            local_path = os.path.join(local_base, item)
            remote_path = f"{remote_base}/{item}".lstrip('/')
            if os.path.isdir(local_path):
                try:
                    ftps.mkd(remote_path)
                    print(f"📁 Created directory: {remote_path}")
                except Exception:
                    pass
                upload_recursive(local_path, remote_path)
            else:
                size = os.path.getsize(local_path)
                with open(local_path, 'rb') as f:
                    ftps.storbinary(f"STOR {remote_path}", f)
                print(f"📄 Uploaded: {remote_path} ({size:,} bytes)")

    print(f"\nDeploying files from {dist_dir} directly to {pwd_dir}...")
    upload_recursive(dist_dir)
    print("\n✅ Hostinger deployment completed successfully!")
    ftps.quit()

if __name__ == '__main__':
    main()
