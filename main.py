# main.py (VERSÃO COM CORS - COLE ESTA NO SEU GITHUB SE AINDA NÃO O FEZ)
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware # IMPORTANTE PARA CORS
import httpx
import asyncio
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any

# --- Configurações ---
API_FUTEBOL_BASE_URL = "https://api.api-futebol.com.br/v1"
API_FUTEBOL_KEY = "live_e25d485aad41c97d4c33f8ebf4f35c" 
CAMPEONATO_BRASILEIRAO_ID = "10" 
CACHE_DURATION_SECONDS = 1 * 60 * 60
UPDATE_INTERVAL_SECONDS = 8 * 60 * 60

app = FastAPI(
    title="API Tabela Brasileirão com Cache",
    description="Fornece a tabela de classificação do Brasileirão (ID 10) com cache.",
    version="1.2.3" # Nova versão para CORS e logs
)

# --- Configuração do CORS ---
origins = [
    "http://localhost",
    "http://localhost:8000",
    "http://127.0.0.1", # Para cobrir variações de localhost
    "http://127.0.0.1:5500", 
    "null", 
    "https://htmlonlineviewer.net",
    "http://lncc.br", # Adicionando o domínio onde você está testando
    "https://lncc.br", # Adicionando com https também
    # Adicione seu domínio WordPress aqui quando for usá-lo
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins, 
    allow_credentials=True,
    allow_methods=["GET"], 
    allow_headers=["*"],
)

tabela_cache: Dict[str, Any] = {
    "data": None, "last_updated": None, "is_updating": False, "last_attempt_successful": True
}

async def fetch_data_from_external_api() -> Optional[List[Dict[str, Any]]]:
    target_url = f"{API_FUTEBOL_BASE_URL}/campeonatos/{CAMPEONATO_BRASILEIRAO_ID}/tabela"
    headers = {"Authorization": f"Bearer {API_FUTEBOL_KEY}"} 
    print(f"[{datetime.now()}] Tentando buscar dados: {target_url} Header Auth: {headers.get('Authorization', '')[:15]}...")
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(target_url, headers=headers, timeout=30.0)
            print(f"[{datetime.now()}] API Externa Respondeu. Status: {response.status_code}") # Log do status
            response.raise_for_status()
            print(f"[{datetime.now()}] Sucesso ao buscar dados da API externa.")
            return response.json()
        except httpx.TimeoutException:
            print(f"[{datetime.now()}] Timeout API externa.")
            return None
        except httpx.HTTPStatusError as e:
            print(f"[{datetime.now()}] Erro HTTP API externa: {e.response.status_code} - {e.response.text}")
            return None
        except Exception as e:
            print(f"[{datetime.now()}] Erro genérico API externa: {e}")
            return None

async def update_cache_if_needed():
    global tabela_cache
    if tabela_cache["is_updating"]:
        print(f"[{datetime.now()}] Atualização cache em progresso. Pulando.")
        return
    tabela_cache["is_updating"] = True
    print(f"[{datetime.now()}] Iniciando atualização cache.")
    data = await fetch_data_from_external_api()
    if data:
        tabela_cache["data"] = data
        tabela_cache["last_updated"] = datetime.now()
        tabela_cache["last_attempt_successful"] = True
        print(f"[{datetime.now()}] Cache atualizado.")
    else:
        tabela_cache["last_attempt_successful"] = False
        print(f"[{datetime.now()}] Falha atualizar cache.")
    tabela_cache["is_updating"] = False

async def periodic_cache_updater():
    await asyncio.sleep(15) # Reduzido para teste mais rápido da primeira carga
    print(f"[{datetime.now()}] Periodic updater: Chamando update_cache_if_needed pela primeira vez.")
    await update_cache_if_needed() 
    while True:
        await asyncio.sleep(UPDATE_INTERVAL_SECONDS)
        print(f"[{datetime.now()}] Periodic updater: Chamando update_cache_if_needed.")
        await update_cache_if_needed()

@app.on_event("startup")
async def startup_event():
    print(f"[{datetime.now()}] Evento Startup: Agendando periodic_cache_updater.")
    asyncio.create_task(periodic_cache_updater())
    print(f"[{datetime.now()}] API iniciada. Tarefa de atualização agendada.")

@app.get("/api/brasileirao/tabela", tags=["Classificação"])
async def get_tabela_brasileirao():
    global tabela_cache
    print(f"[{datetime.now()}] Endpoint /tabela chamado.")
    if tabela_cache["data"] and tabela_cache["last_updated"] and \
       (datetime.now() < tabela_cache["last_updated"] + timedelta(seconds=CACHE_DURATION_SECONDS)):
        print(f"[{datetime.now()}] Servindo do cache (fresco).")
        return tabela_cache["data"]
    if tabela_cache["is_updating"]:
        if tabela_cache["data"]:
             print(f"[{datetime.now()}] Atualização em progresso, servindo cache antigo.")
             return tabela_cache["data"]
        else:
            print(f"[{datetime.now()}] Atualização inicial em progresso, cache vazio.")
            raise HTTPException(status_code=503, detail="Dados sendo preparados. Tente em instantes.")
    if not tabela_cache["data"]:
        print(f"[{datetime.now()}] Cache vazio, disparando atualização.")
        asyncio.create_task(update_cache_if_needed())
        raise HTTPException(status_code=503, detail="Cache inicializando. Tente em instantes.")
    else: 
        print(f"[{datetime.now()}] Cache desatualizado, servindo dados antigos.")
        return tabela_cache["data"]
