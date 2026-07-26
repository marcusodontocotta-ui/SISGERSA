"""
Script de deploy manual para Render.com
=========================================
Uso:
  1. Gere uma API key em https://dashboard.render.com/u/settings#api-keys
  2. Crie um arquivo .env na raiz do projeto com:
       RENDER_API_KEY=rk_sua_chave_aqui
       RENDER_SERVICE_ID=srv-xxxxx  (encontrado na URL do servico no dashboard)
  3. Rode: python deploy.py

Ou passe direto:
  python deploy.py --api-key rk_xxx --service-id srv_xxx
"""

import os
import sys
import time
import json

try:
    import httpx
except ImportError:
    print("Instalando httpx...")
    os.system(f"{sys.executable} -m pip install httpx -q")
    import httpx


def load_env():
    env_path = os.path.join(os.path.dirname(__file__), ".env")
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip())


def get_args():
    import argparse
    parser = argparse.ArgumentParser(description="Deploy manual Render.com")
    parser.add_argument("--api-key", help="Render API key")
    parser.add_argument("--service-id", help="Render service ID (srv_xxx)")
    parser.add_argument("--status", action="store_true", help="Apenas verificar status")
    parser.add_argument("--clear-cache", action="store_true", help="Limpar cache e redesployar")
    return parser.parse_args()


def main():
    args = get_args()
    load_env()

    api_key = args.api_key or os.environ.get("RENDER_API_KEY")
    service_id = args.service_id or os.environ.get("RENDER_SERVICE_ID")

    if not api_key:
        print("ERRO: API key necessaria.")
        print("Gere em: https://dashboard.render.com/u/settings#api-keys")
        print("Salve no .env como RENDER_API_KEY=rk_xxx")
        sys.exit(1)

    if not service_id:
        print("ERRO: Service ID necessario.")
        print("Encontre na URL do dashboard: https://dashboard.render.com/services/srv-xxxxx")
        print("Salve no .env como RENDER_SERVICE_ID=srv-xxxxx")
        sys.exit(1)

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    base = "https://api.render.com/v1"

    print(f"Servico: {service_id}")

    # 1. Check status
    print("\n[1/3] Verificando status do servico...")
    r = httpx.get(f"{base}/services/{service_id}", headers=headers, timeout=30)
    if r.status_code != 200:
        print(f"ERRO ao consultar servico: {r.status_code}")
        print(r.text)
        sys.exit(1)

    svc = r.json()
    status = svc.get("status", "unknown")
    name = svc.get("name", "N/A")
    region = svc.get("region", "N/A")
    print(f"  Nome: {name}")
    print(f"  Regiao: {region}")
    print(f"  Status: {status}")

    if args.status:
        return

    # 2. Check latest deploy
    print("\n[2/3] Verificando ultimo deploy...")
    r = httpx.get(
        f"{base}/services/{service_id}/deploys",
        headers=headers,
        params={"limit": 1},
        timeout=30,
    )
    if r.status_code == 200:
        deploys = r.json()
        if deploys:
            latest = deploys[0]
            print(f"  Deploy ID: {latest.get('id', 'N/A')}")
            print(f"  Status: {latest.get('status', 'N/A')}")
            print(f"  Commit: {latest.get('commit', {}).get('id', 'N/A')[:7] if isinstance(latest.get('commit'), dict) else latest.get('commit', 'N/A')[:7]}")
            print(f"  Criado: {latest.get('created_at', 'N/A')}")
    else:
        print(f"  Nao foi possivel consultar deploys: {r.status_code}")

    # 3. Trigger deploy
    print(f"\n[3/3] Disparando deploy manual...")
    payload = {"clearCache": args.clear_cache}
    r = httpx.post(
        f"{base}/services/{service_id}/deploys",
        headers=headers,
        json=payload,
        timeout=30,
    )

    if r.status_code in (200, 201):
        deploy = r.json()
        deploy_id = deploy.get("id", "N/A")
        print(f"  Deploy disparado com sucesso!")
        print(f"  Deploy ID: {deploy_id}")
        print(f"  Acompanhe em: https://dashboard.render.com/services/{service_id}")

        # Poll status
        print("\nAcompanhando deploy (poll a cada 15s)...")
        for i in range(20):
            time.sleep(15)
            r2 = httpx.get(
                f"{base}/services/{service_id}/deploys",
                headers=headers,
                params={"limit": 1},
                timeout=30,
            )
            if r2.status_code == 200:
                deploys2 = r2.json()
                if deploys2:
                    d = deploys2[0]
                    st = d.get("status", "unknown")
                    print(f"  [{i*15}s] Status: {st}")
                    if st in ("live", "deactivated", "canceled", "build_failed"):
                        if st == "live":
                            url = svc.get("service_details", {}).get("url", "")
                            if not url:
                                url = f"https://{name}.onrender.com"
                            print(f"\n  DEPLOY CONCLUIDO COM SUCESSO!")
                            print(f"  URL: {url}")
                        else:
                            print(f"\n  Deploy finalizou com status: {st}")
                            print(f"  Verifique os logs no dashboard.")
                        return
        print("\n  Timeout ao aguardar deploy. Verifique o dashboard.")
    else:
        print(f"  ERRO ao disparar deploy: {r.status_code}")
        print(f"  {r.text}")
        sys.exit(1)


if __name__ == "__main__":
    main()
