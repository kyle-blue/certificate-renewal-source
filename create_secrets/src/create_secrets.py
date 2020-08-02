import os
from base64 import b64encode, b64decode
from kubernetes import client, config
import yaml, json
import sys
import subprocess

# // TODO Clean up this code

def createFile(file_name: str, contents: str):
    print(f"Creating file: '{file_name}'")
    os.makedirs(os.path.dirname(file_name), exist_ok=True)
    with open(file_name, mode='w') as file:
        file.write(contents)

def getFileContents(file_name) -> str:
    contents: str
    with open(file_name, mode='r') as file:
        contents = file.read()
    return contents

def encode(string: str) -> str:
    return b64encode(bytes(string, "utf-8")).decode("utf-8")

def decode(string: str) -> str:
    return b64decode(bytes(string, "utf-8")).decode("utf-8")


def mountSecrets(secrets: list, secret_names:list, server: str):
    WEBSITE: str = os.environ["WEBSITE"]
    staging_url = "https://acme-staging-v02.api.letsencrypt.org/directory"
    production_url = "https://acme-v02.api.letsencrypt.org/directory"
    force_update = False

    cert_data = secrets[secret_names.index("certificate-secret")].data
    config_data = decode(secrets[secret_names.index("letsencrypt-config")].data[f"{WEBSITE}.conf"])

    new_config_data = config_data.replace(staging_url, production_url) if server == "" else config_data.replace(production_url, staging_url)
    if new_config_data != config_data:
        force_update = True 
        config_data = new_config_data   

    if server == "" and config_data.find(staging_url) != -1:
        return # Don't mount files, force update!

    print(f"Config Data {config_data}", flush=True)
    createFile(f"/etc/letsencrypt/renewal/{WEBSITE}.conf", config_data)
    for key, value in cert_data.items():
        createFile(f"/etc/letsencrypt/archive/{WEBSITE}/{key[:-4]}1.pem", decode(value))
        os.makedirs(os.path.dirname(f"/etc/letsencrypt/live/{WEBSITE}/{key}"), exist_ok=True)
        os.symlink(f"/etc/letsencrypt/archive/{WEBSITE}/{key[:-4]}1.pem", f"/etc/letsencrypt/live/{WEBSITE}/{key}")
    return force_update





print("\nNote: In order for this to work, WEBSITE, SERVER (staging | production) and SUBDOMAINS('subdomain1 subdomain2') environment variables should be specified...")
config.load_incluster_config()
v1 = client.CoreV1Api()

secrets = list(v1.list_namespaced_secret("app").items)
secret_names = list(map(lambda x: x.metadata.name, secrets))

WEBSITE: str = os.environ["WEBSITE"]
print(f"Checking if certificate secret exists for website: {WEBSITE}")

server = ""
if "SERVER" in os.environ:
    server = "--test-cert" if os.environ["SERVER"].lower() == "staging" else ""

force_update = False
if "certificate-secret" in secret_names:
    print("\nCertificate secret exists...\nUpdating existing certificate (if required)...")
    force_update = mountSecrets(secrets, secret_names, server)
else:
    print("Certificate does NOT exist...\nCreating new certificate...\nWARNING --- MAKE SURE YOU DO NOT CREATE NEW CERTIFICATES OFTEN. THERE IS A LIMIT OF AROUND 4 PER WEEK")

# This will create a new cert if needed, otherwise will update
domains = f"-d {WEBSITE}"
for subdomain in os.environ["SUBDOMAINS"].split(' '):
    domains += f" -d {subdomain}.{WEBSITE} "
bashCommand = f'certbot certonly --standalone --keep-until-expiring --expand --agree-tos {server} {"--break-my-certs --force-renewal" if force_update else ""}\
     -n -m "kyle.blue.nuttall@gmail.com" {domains};'
print(f"\nExecuting: {bashCommand}", flush=True) 
subprocess.call(["/bin/bash", "-c", bashCommand], stdout=subprocess.PIPE)



#### Create YAML and replace secrets in cluster ####
config_data, cert_data = "", dict()
base_yaml = f"""
apiVersion: v1
kind: Secret
type: Opaque
metadata:
    name: ""
    namespace: app
data: ""
immutable: false
"""
config_data = getFileContents(f"/etc/letsencrypt/renewal/{WEBSITE}.conf")
config_body = yaml.load(base_yaml, Loader=yaml.FullLoader)
config_body["metadata"]["name"] = "letsencrypt-config"
config_body["data"] = {f"{WEBSITE}.conf": encode(config_data)}


if "letsencrypt-config" in secret_names:
    print(f"Replacing letsencrypt-config secret:\n{config_body}")
    v1.replace_namespaced_secret("letsencrypt-config", "app", config_body)
else:
    print(f"Creating letsencrypt-config secret:\n{config_body}")
    v1.create_namespaced_secret("app", config_body)


cert_data["cert.pem"] = getFileContents(f"/etc/letsencrypt/live/{WEBSITE}/cert.pem") 
cert_data["chain.pem"] = getFileContents(f"/etc/letsencrypt/live/{WEBSITE}/chain.pem")
cert_data["fullchain.pem"] = getFileContents(f"/etc/letsencrypt/live/{WEBSITE}/fullchain.pem")
cert_data["privkey.pem"] = getFileContents(f"/etc/letsencrypt/live/{WEBSITE}/privkey.pem")

cert_body = yaml.load(base_yaml, Loader=yaml.FullLoader)
cert_body["metadata"]["name"] = "certificate-secret"
cert_body["data"] = {
    "cert.pem": encode(cert_data["cert.pem"]),
    "chain.pem": encode(cert_data["chain.pem"]),
    "fullchain.pem": encode(cert_data["fullchain.pem"]),
    "privkey.pem": encode(cert_data["privkey.pem"]),
    "tls.crt": encode(cert_data["cert.pem"]),
    "tls.key": encode(cert_data["privkey.pem"])
}

if "certificate-secret" in secret_names:
    print(f"Replacing certificate-secret secret:\n{cert_body}")
    v1.replace_namespaced_secret("certificate-secret", "app", cert_body)
else:
    print(f"Create certificate-secret secret:\n{cert_body}")
    v1.create_namespaced_secret("app", cert_body)

