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

    ftps.cwd('/')
    print("Logged in at root /")

    target_dirs = []
    try:
        domain_entries = ftps.nlst('domains')
        print("Raw domains entries:", domain_entries)
        for entry in domain_entries:
            entry_name = entry.rstrip('/').split('/')[-1]
            if entry_name in ('.', '..'):
                continue
            target_dirs.append(f"/domains/{entry_name}/public_html")
    except Exception as e:
        print("Listing domains error:", e)

    target_dirs.append('/public_html')
    print("Identified deployment targets:", target_dirs)

    dist_dir = os.path.abspath('frontend/dist')

    for docroot in target_dirs:
        print(f"\n==========================================")
        print(f"Deploying to: {docroot}")
        print(f"==========================================")
        try:
            ftps.cwd(docroot)
        except Exception as e:
            print(f"Directory {docroot} does not exist or cannot be accessed ({e}). Skipping.")
            continue

        print(f"Current PWD: {ftps.pwd()}")
        print("Files currently in directory:")
        ftps.dir()

        def upload_recursive(local_base, remote_base=''):
            for item in sorted(os.listdir(local_base)):
                local_path = os.path.join(local_base, item)
                remote_path = f"{remote_base}/{item}".lstrip('/')
                if os.path.isdir(local_path):
                    try:
                        ftps.mkd(remote_path)
                    except Exception:
                        pass
                    upload_recursive(local_path, remote_path)
                else:
                    size = os.path.getsize(local_path)
                    with open(local_path, 'rb') as f:
                        ftps.storbinary(f"STOR {remote_path}", f)
                    print(f"  📄 Uploaded {remote_path} ({size:,} bytes)")

        upload_recursive(dist_dir)

    print("\n✅ All target docroots synchronized successfully!")
    ftps.quit()

if __name__ == '__main__':
    main()
