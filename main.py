# main.py
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware # ADICIONADO PARA CORS
import httpx
import asyncio
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any

# --- Configurações ---
API_FUTEBOL_BASE_URL = "https://api.api-futebol.com.br/v1"
API_FUTEBOL_KEY = "live_e25d485aad41c97d4c33f8ebf4f35c" # Sua chave API OFICIAL
CAMPEONATO_BRASILEIRAO_ID = "10" # ID do campeonato
# Cache da API FastAPI válido por 1 hora (3600 segundos)
CACHE_DURATION_SECONDS = 1 * 60 * 60
# API FastAPI busca novos dados da api-futebol a cada 8 horas (28800 segundos)
UPDATE_INTERVAL_SECONDS = 8 * 60 * 60

app = FastAPI(
    title="API Tabela Brasileirão com Cache",
    description="Fornece a tabela de classificação do Brasileirão (ID 10) com cache.",
    version="1.2.2" # Versão incrementada para refletir a adição do CORS
)

# --- Configuração do CORS ---
# Lista de origens permitidas. Adicione outros domínios se necessário.
origins = [
    "http://localhost",         # Para testes locais comuns
    "http://localhost:8000",    # Para testes locais com FastAPI rodando na porta 8000
    "http://127.0.0.1:5500",   # Exemplo se usar Live Server do VSCode em uma porta específica
    "null",                     # Para permitir testes com arquivos HTML abertos localmente (origin: "null")
    "https://htmlonlineviewer.net", # Para o visualizador que você está usando
    # "https://SEU_DOMINIO_WORDPRESS.com", # DESCOMENTE E ADICIONE SEU DOMÍNIO WORDPRESS REAL AQUI QUANDO FOR USAR
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,       # Permite as origens listadas
    # allow_origins=["*"],       # Alternativa: Permite TODAS as origens (menos seguro para produção)
    allow_credentials=True,      # Permite cookies (não estamos usando, mas é uma boa prática incluir)
    allow_methods=["GET"],       # Permite apenas o método GET para esta API específica
    allow_headers=["*"],         # Permite todos os cabeçalhos
)

# --- Cache Simples em Memória --- (Restante do código permanece o mesmo)
tabela_cache: Dict[str, Any] = {
    "data": None,
    "last_updated": None,
    "is_updating": False, 
    "last_attempt_successful": True
}

# --- Função para buscar dados da API externa ---
async def fetch_data_from_external_api() -> Optional[List[Dict[str, Any]]]:
    target_url = f"{API_FUTEBOL_BASE_URL}/campeonatos/{CAMPEONATO_BRASILEIRAO_ID}/tabela"
    headers = {"Authorization": f"Bearer {API_FUTEBOL_KEY}"} 
    print(f"[{datetime.now()}] Tentando buscar dados frescos de {target_url} com header: {headers.get('Authorization', 'Chave não encontrada no header')[:15]}...")
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(target_url, headers=headers, timeout=30.0)
            response.raise_for_status()
            print(f"[{datetime.now()}] Sucesso ao buscar dados da API externa. Status: {response.status_code}")
            return response.json()
        except httpx.TimeoutException:
            print(f"[{datetime.now()}] Timeout ao buscar dados da API externa.")
            return None
        except httpx.HTTPStatusError as e:
            print(f"[{datetime.now()}] Erro HTTP da API externa: {e.response.status_code} - {e.response.text}")
            return None
        except Exception as e:
            print(f"[{datetime.now()}] Erro genérico ao buscar dados da API externa: {e}")
            return None

# --- Função de atualização do cache ---
async def update_cache_if_needed():
    global tabela_cache
    if tabela_cache["is_updating"]:
        print(f"[{datetime.now()}] Atualização do cache já em progresso. Pulando.")
        return
    tabela_cache["is_updating"] = True
    print(f"[{datetime.now()}] Iniciando atualização do cache...")
    data = await fetch_data_from_external_api()
    if data:
        tabela_cache["data"] = data
        tabela_cache["last_updated"] = datetime.now()
        tabela_cache["last_attempt_successful"] = True
        print(f"[{datetime.now()}] Cache atualizado com sucesso.")
    else:
        tabela_cache["last_attempt_successful"] = False
        print(f"[{datetime.now()}] Falha ao buscar novos dados para o cache. Cache anterior mantido (se existir).")
    tabela_cache["is_updating"] = False

# --- Tarefa de atualização periódica do cache ---
async def periodic_cache_updater():
    await asyncio.sleep(45) 
    await update_cache_if_needed() 
    while True:
        await asyncio.sleep(UPDATE_INTERVAL_SECONDS)
        await update_cache_if_needed()

@app.on_event("startup")
async def startup_event():
    asyncio.create_task(periodic_cache_updater())
    print(f"[{datetime.now()}] API iniciada. Tarefa de atualização periódica de cache agendada.")

# --- Endpoint da API ---
@app.get("/api/brasileirao/tabela", tags=["Classificação"])
async def get_tabela_brasileirao():
    global tabela_cache
    if tabela_cache["data"] and tabela_cache["last_updated"] and \
       (datetime.now() < tabela_cache["last_updated"] + timedelta(seconds=CACHE_DURATION_SECONDS)):
        print(f"[{datetime.now()}] Servindo dados do cache (frescos).")
        return tabela_cache["data"]
    if tabela_cache["is_updating"]:
        if tabela_cache["data"]:
             print(f"[{datetime.now()}] Atualização em progresso, servindo dados antigos do cache.")
             return tabela_cache["data"]
        else:
            print(f"[{datetime.now()}] Atualização inicial em progresso, cache vazio. Tente novamente em breve.")
            raise HTTPException(status_code=503, detail="Dados sendo preparados. Tente novamente em alguns instantes.")
    if not tabela_cache["data"]:
        print(f"[{datetime.now()}] Cache vazio e nenhuma atualização em progresso. Disparando atualização...")
        asyncio.create_task(update_cache_if_needed())
        raise HTTPException(status_code=503, detail="Cache inicializando. Tente novamente em alguns instantes.")
    else: 
        print(f"[{datetime.now()}] Cache desatualizado, servindo dados antigos. Atualização em background deve ocorrer.")
        return tabela_cache["data"]
