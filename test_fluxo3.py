import sys
sys.path.insert(0, '.')
from main import app
from fastapi.testclient import TestClient

client = TestClient(app)

print("=== 1. Login ===")
r = client.post("/login", data={"email": "guiaparaoinesperado@gmail.com", "senha": "Ong6132"}, follow_redirects=False)
print(f"Status: {r.status_code}")
estab = r.cookies.get('estabelecimento_id', 'NAO SETADO')
print(f"Estab cookie: {estab}")

print("\n=== 2. Dashboard ===")
r2 = client.get("/dashboard", follow_redirects=False)
print(f"Status: {r2.status_code}")
if r2.status_code == 200:
    import re
    title = re.search(r'<h2[^>]*>(.*?)</h2>', r2.text)
    print(f"Titulo: {title.group(1).strip() if title else 'nao encontrado'}")
    if "Selecionar Estabelecimento" in r2.text:
        print(">>> TELA DE SELECAO (ERRADO - era pra ir direto)")
    elif "Consultorio" in r2.text or "Marcus Cotta" in r2.text:
        print(">>> CORRETO: Entrou direto no consultorio!")
    elif "Meu Estabelecimento" in r2.text:
        print(">>> Generico")
    else:
        print(">>> Template: " + ("admin_estab" if "admin_estab" in r2.text else "outro"))
