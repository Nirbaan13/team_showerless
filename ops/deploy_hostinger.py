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

    print("Initial PWD:", ftps.pwd())
    try:
        ftps.cwd('/')
        print("Root PWD:", ftps.pwd())
    except Exception as e:
        print("Could not cwd to /:", e)

    print("\nListing root directory:")
    ftps.dir()

    # Find the target directory where the live site files reside
    target_dirs = []
    def find_doc_roots(current_path=''):
        try:
            items = ftps.nlst(current_path)
            for item in items:
                base = item.rstrip('/').split('/')[-1]
                if base in ('.', '..'): continue
                if 'index-Cg5wohe9.js' in base:
                    parent = os.path.dirname(item)
                    grandparent = os.path.dirname(parent)
                    print(f"🎯 FOUND LIVE FILE at: {item} -> Docroot is: {grandparent or '/'}")
                    if grandparent not in target_dirs:
                        target_dirs.append(grandparent or '/')
                # Recurse into directories
                try:
                    # test if it's a dir
                    ftps.cwd(item)
                    ftps.cwd('..')
                    find_doc_roots(item)
                except Exception:
                    pass
        except Exception as e:
            pass

    find_doc_roots()
    print("Discovered target docroots:", target_dirs)

    # If not found via search, fallback to PWD
    if not target_dirs:
        # Check domains/ directory
        try:
            domains = ftps.nlst('domains')
            print("Found domains:", domains)
            for d in domains:
                target_dirs.append(f"{d}/public_html")
        except Exception:
            pass

    if not target_dirs:
        target_dirs = ['/public_html', '/']

    dist_dir = os.path.abspath('frontend/dist')

    for docroot in target_dirs:
        print(f"\n==========================================")
        print(f"Deploying to docroot: {docroot}")
        print(f"==========================================")
        try:
            ftps.cwd(docroot)
        except Exception as e:
            print(f"Could not cwd to {docroot}: {e}")
            continue

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
                    print(f"📄 Uploaded to {docroot}/{remote_path} ({size:,} bytes)")

        upload_recursive(dist_dir)

    print("\n✅ All target docroots synchronized successfully!")
    ftps.quit()

if __name__ == '__main__':
    main()
