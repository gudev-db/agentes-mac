import streamlit as st
import io
import google.generativeai as genai
from PIL import Image
import requests
import datetime
import os
from pymongo import MongoClient
from bson import ObjectId
import json
import hashlib
from google.genai import types
import PyPDF2
from pptx import Presentation
import docx
import openai
from typing import List, Dict, Tuple
import hashlib
import pandas as pd
import re

# Configuração inicial
st.set_page_config(
    layout="wide",
    page_title="Agente Social",
    page_icon="🤖"
)

import os
import PyPDF2
import pdfplumber
from pathlib import Path

def extract_text_from_pdf(pdf_path):
    """
    Extract text from a PDF file using multiple methods for better coverage
    """
    text = ""

    # Method 1: Try with pdfplumber (better for some PDFs)
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"
    except Exception as e:
        print(f"pdfplumber failed for {pdf_path}: {e}")

    # Method 2: Fallback to PyPDF2 if pdfplumber didn't extract much text
    if len(text.strip()) < 100:  # If very little text was extracted
        try:
            with open(pdf_path, 'rb') as file:
                pdf_reader = PyPDF2.PdfReader(file)
                for page in pdf_reader.pages:
                    page_text = page.extract_text()
                    if page_text:
                        text += page_text + "\n"
        except Exception as e:
            print(f"PyPDF2 also failed for {pdf_path}: {e}")

    return text
    


# --- Sistema de Autenticação ---
def make_hashes(password):
    return hashlib.sha256(str.encode(password)).hexdigest()

def check_hashes(password, hashed_text):
    return make_hashes(password) == hashed_text

# Dados de usuário (em produção, isso deve vir de um banco de dados seguro)
users = {
    "admin": make_hashes("senha1234"),  # admin/senha1234
    "user1": make_hashes("password1"),  # user1/password1
    "user2": make_hashes("password2")   # user2/password2
}


import os
from pathlib import Path
from pptx import Presentation

def extract_text_from_pptx(pptx_path):
    """
    Extract text from a PowerPoint file (.pptx)
    """
    text = ""
    
    try:
        # Open the presentation
        prs = Presentation(pptx_path)
        
        # Process each slide
        for slide_number, slide in enumerate(prs.slides, 1):
            text += f"\n--- Slide {slide_number} ---\n"
            
            # Extract text from shapes
            for shape in slide.shapes:
                if hasattr(shape, "text") and shape.text:
                    text += shape.text + "\n"
                
                # Handle tables
                if shape.shape_type == 19:  # Table shape type
                    table = shape.table
                    for row in table.rows:
                        row_text = " | ".join(cell.text for cell in row.cells if cell.text)
                        if row_text:
                            text += row_text + "\n"
            
            text += "\n"  # Add spacing between slides
    
    except Exception as e:
        print(f"Error processing {pptx_path}: {e}")
        text = f"ERROR: Could not extract text from {pptx_path}\nError: {e}"
    
    return text

def extract_metadata_from_pptx(pptx_path):
    """
    Extract metadata from PowerPoint file
    """
    try:
        prs = Presentation(pptx_path)
        metadata = {
            'slides_count': len(prs.slides),
            'slide_layouts': len(prs.slide_layouts),
            'slide_masters': len(prs.slide_masters)
        }
        return metadata
    except Exception as e:
        return {'error': str(e)}



def login():
    """Formulário de login"""
    st.title("🔒 Agente Social - Login")
    
    with st.form("login_form"):
        username = st.text_input("Usuário")
        password = st.text_input("Senha", type="password")
        submit_button = st.form_submit_button("Login")
        
        if submit_button:
            if username in users and check_hashes(password, users[username]):
                st.session_state.logged_in = True
                st.session_state.user = username
                st.success("Login realizado com sucesso!")
                st.rerun()
            else:
                st.error("Usuário ou senha incorretos")

# Verificar se o usuário está logado
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False

if not st.session_state.logged_in:
    login()
    st.stop()

# --- CONEXÃO MONGODB (após login) ---
client = MongoClient("mongodb+srv://gustavoromao3345:RqWFPNOJQfInAW1N@cluster0.5iilj.mongodb.net/auto_doc?retryWrites=true&w=majority&ssl=true&ssl_cert_reqs=CERT_NONE&tlsAllowInvalidCertificates=true")
db = client['agentes_personalizados']
collection_agentes = db['agentes']
collection_conversas = db['conversas']

# Configuração da API do Gemini
gemini_api_key = os.getenv("GEM_API_KEY")
if not gemini_api_key:
    st.error("GEMINI_API_KEY não encontrada nas variáveis de ambiente")
    st.stop()

genai.configure(api_key=gemini_api_key)
modelo_vision = genai.GenerativeModel("gemini-2.5-flash", generation_config={"temperature": 0.1})
modelo_texto = genai.GenerativeModel("gemini-2.5-flash")

# Configuração da API do Perplexity
perp_api_key = os.getenv("PERP_API_KEY")
if not perp_api_key:
    st.error("PERP_API_KEY não encontrada nas variáveis de ambiente")

# --- Configuração de Autenticação de Administrador ---
def check_admin_password():
    """Retorna True para usuários admin sem verificação de senha."""
    return st.session_state.user == "admin"

# --- Funções CRUD para Agentes ---
def criar_agente(nome, system_prompt, base_conhecimento, comments, planejamento, categoria, agente_mae_id=None, herdar_elementos=None):
    """Cria um novo agente no MongoDB"""
    agente = {
        "nome": nome,
        "system_prompt": system_prompt,
        "base_conhecimento": base_conhecimento,
        "comments": comments,
        "planejamento": planejamento,
        "categoria": categoria,
        "agente_mae_id": agente_mae_id,
        "herdar_elementos": herdar_elementos or [],
        "data_criacao": datetime.datetime.now(),
        "ativo": True
    }
    result = collection_agentes.insert_one(agente)
    return result.inserted_id

def listar_agentes():
    """Retorna todos os agentes ativos"""
    return list(collection_agentes.find({"ativo": True}).sort("data_criacao", -1))

def listar_agentes_para_heranca(agente_atual_id=None):
    """Retorna todos os agentes ativos que podem ser usados como mãe"""
    query = {"ativo": True}
    if agente_atual_id:
        # Excluir o próprio agente da lista de opções para evitar auto-herança
        if isinstance(agente_atual_id, str):
            agente_atual_id = ObjectId(agente_atual_id)
        query["_id"] = {"$ne": agente_atual_id}
    return list(collection_agentes.find(query).sort("data_criacao", -1))

def obter_agente(agente_id):
    """Obtém um agente específico pelo ID"""
    if isinstance(agente_id, str):
        agente_id = ObjectId(agente_id)
    return collection_agentes.find_one({"_id": agente_id})

def atualizar_agente(agente_id, nome, system_prompt, base_conhecimento, comments, planejamento, categoria, agente_mae_id=None, herdar_elementos=None):
    """Atualiza um agente existente"""
    if isinstance(agente_id, str):
        agente_id = ObjectId(agente_id)
    return collection_agentes.update_one(
        {"_id": agente_id},
        {
            "$set": {
                "nome": nome,
                "system_prompt": system_prompt,
                "base_conhecimento": base_conhecimento,
                "comments": comments,
                "planejamento": planejamento,
                "categoria": categoria,
                "agente_mae_id": agente_mae_id,
                "herdar_elementos": herdar_elementos or [],
                "data_atualizacao": datetime.datetime.now()
            }
        }
    )

def desativar_agente(agente_id):
    """Desativa um agente (soft delete)"""
    if isinstance(agente_id, str):
        agente_id = ObjectId(agente_id)
    return collection_agentes.update_one(
        {"_id": agente_id},
        {"$set": {"ativo": False, "data_desativacao": datetime.datetime.now()}}
    )

def obter_agente_com_heranca(agente_id):
    """Obtém um agente com os elementos herdados aplicados"""
    agente = obter_agente(agente_id)
    if not agente or not agente.get('agente_mae_id'):
        return agente
    
    agente_mae = obter_agente(agente['agente_mae_id'])
    if not agente_mae:
        return agente
    
    elementos_herdar = agente.get('herdar_elementos', [])
    agente_completo = agente.copy()
    
    for elemento in elementos_herdar:
        if elemento == 'system_prompt' and not agente_completo.get('system_prompt'):
            agente_completo['system_prompt'] = agente_mae.get('system_prompt', '')
        elif elemento == 'base_conhecimento' and not agente_completo.get('base_conhecimento'):
            agente_completo['base_conhecimento'] = agente_mae.get('base_conhecimento', '')
        elif elemento == 'comments' and not agente_completo.get('comments'):
            agente_completo['comments'] = agente_mae.get('comments', '')
        elif elemento == 'planejamento' and not agente_completo.get('planejamento'):
            agente_completo['planejamento'] = agente_mae.get('planejamento', '')
    
    return agente_completo

def salvar_conversa(agente_id, mensagens, segmentos_utilizados=None):
    """Salva uma conversa no histórico"""
    if isinstance(agente_id, str):
        agente_id = ObjectId(agente_id)
    conversa = {
        "agente_id": agente_id,
        "mensagens": mensagens,
        "segmentos_utilizados": segmentos_utilizados,
        "data_criacao": datetime.datetime.now()
    }
    return collection_conversas.insert_one(conversa)

def obter_conversas(agente_id, limite=10):
    """Obtém o histórico de conversas de um agente"""
    if isinstance(agente_id, str):
        agente_id = ObjectId(agente_id)
    return list(collection_conversas.find(
        {"agente_id": agente_id}
    ).sort("data_criacao", -1).limit(limite))

# --- Função para construir contexto com segmentos selecionados ---
def construir_contexto(agente, segmentos_selecionados, historico_mensagens=None):
    """Constrói o contexto com base nos segmentos selecionados"""
    contexto = ""
    
    if "system_prompt" in segmentos_selecionados and agente.get('system_prompt'):
        contexto += f"### INSTRUÇÕES DO SISTEMA ###\n{agente['system_prompt']}\n\n"
    
    if "base_conhecimento" in segmentos_selecionados and agente.get('base_conhecimento'):
        contexto += f"### BASE DE CONHECIMENTO ###\n{agente['base_conhecimento']}\n\n"
    
    if "comments" in segmentos_selecionados and agente.get('comments'):
        contexto += f"### COMENTÁRIOS DO CLIENTE ###\n{agente['comments']}\n\n"
    
    if "planejamento" in segmentos_selecionados and agente.get('planejamento'):
        contexto += f"### PLANEJAMENTO ###\n{agente['planejamento']}\n\n"
    
    # Adicionar histórico se fornecido
    if historico_mensagens:
        contexto += "### HISTÓRICO DA CONVERSA ###\n"
        for msg in historico_mensagens:
            contexto += f"{msg['role']}: {msg['content']}\n"
        contexto += "\n"
    
    contexto += "### RESPOSTA ATUAL ###\nassistant:"
    
    return contexto

# --- NOVA SEÇÃO: SELEÇÃO DE AGENTE ANTES DA INTERFACE ---
def selecionar_agente():
    """Tela para seleção do agente antes de ativar a interface principal"""
    st.title("🤖 Selecione um Agente")
    st.markdown("Escolha um agente para começar a usar o sistema:")
    
    agentes = listar_agentes()
    if not agentes:
        st.error("❌ Nenhum agente disponível. Crie um agente primeiro na aba de Gerenciamento.")
        return False
    
    # Agrupar agentes por categoria
    agentes_por_categoria = {}
    for agente in agentes:
        categoria = agente.get('categoria', 'Social')
        if categoria not in agentes_por_categoria:
            agentes_por_categoria[categoria] = []
        agentes_por_categoria[categoria].append(agente)
    
    # Exibir agentes por categoria
    for categoria, agentes_cat in agentes_por_categoria.items():
        st.subheader(f"📁 {categoria}")
        
        for agente in agentes_cat:
            agente_completo = obter_agente_com_heranca(agente['_id'])
            
            col1, col2 = st.columns([3, 1])
            with col1:
                st.write(f"**{agente['nome']}**")
                if agente.get('agente_mae_id'):
                    st.caption("🔗 Agente com herança")
                
                # Preview das informações
                if agente_completo.get('system_prompt'):
                    st.caption(f"📝 {agente_completo['system_prompt'][:100]}...")
            
            with col2:
                if st.button("Selecionar", key=f"select_{agente['_id']}"):
                    st.session_state.agente_selecionado = agente_completo
                    st.session_state.messages = []
                    st.session_state.segmentos_selecionados = ["system_prompt", "base_conhecimento", "comments", "planejamento"]
                    st.success(f"✅ Agente '{agente['nome']}' selecionado!")
                    st.rerun()
            
            st.divider()
    
    return False

# --- Verificar se o agente já foi selecionado ---
if "agente_selecionado" not in st.session_state:
    st.session_state.agente_selecionado = None

# Se não há agente selecionado, mostrar tela de seleção
if not st.session_state.agente_selecionado:
    selecionar_agente()
    st.stop()

# --- INTERFACE PRINCIPAL (apenas se agente estiver selecionado) ---
agente_selecionado = st.session_state.agente_selecionado

# --- FUNCIONALIDADE DE BRIEFING SYNGENTA ---
def is_syngenta_agent(agent_name):
    """Verifica se o agente é da Syngenta baseado no nome"""
    return agent_name and any(keyword in agent_name.upper() for keyword in ['SYN', 'SYNGENTA'])

# Dicionário de descrições de produtos Syngenta
PRODUCT_DESCRIPTIONS = {
    "FORTENZA": "Tratamento de sementes inseticida, focado no Cerrado e posicionado para controle do complexo de lagartas e outras pragas iniciais. Comunicação focada no mercado 'on farm' (tratamento feito na fazenda).",
    "ALADE": "Fungicida para controle de doenças em soja, frequentemente posicionado em programa com Mitrion para controle de podridões de vagens e grãos.",
    "VERDAVIS": "Inseticida e acaricida composto por PLINAZOLIN® technology (nova molécula, novo grupo químico, modo de ação inédito) + lambda-cialotrina. KBFs: + mais choque, + mais espectro e + mais dias de controle.",
    "ENGEO PLENO S": "Inseticida de tradição, referência no controle de percevejos. Mote: 'Nunca foi sorte. Sempre foi Engeo Pleno S'.",
    "MEGAFOL": "Bioativador da Syngenta Biologicals. Origem 100% natural (extratos vegetais e de algas Ascophyllum nodosum). Desenvolvido para garantir que a planta alcance todo seu potencial produtivo.",
    "MIRAVIS DUO": "Fungicida da família Miravis. Traz ADEPIDYN technology (novo ingrediente ativo, novo grupo químico). Focado no controle de manchas foliares.",
    "AVICTA COMPLETO": "Oferta comercial de tratamento industrial de sementes (TSI). Composto por inseticida, fungicida e nematicida.",
    "MITRION": "Fungicida para controle de doenças em soja, frequentemente posicionado em programa com Alade.",
    "AXIAL": "Herbicida para trigo. Composto por um novo ingrediente ativo. Foco no controle do azevém.",
    "CERTANO": "Bionematicida e biofungicida. Composto pela bactéria Bacillus velezensis. Controla nematoides e fungos de solo.",
    "MANEJO LIMPO": "Programa da Syngenta para manejo integrado de plantas daninhas.",
    "ELESTAL NEO": "Fungicida para controle de doenças em soja e algodão.",
    "FRONDEO": "Inseticida para cana-de-açúcar com foco no controle da broca da cana.",
    "FORTENZA ELITE": "Oferta comercial de TSI. Solução robusta contre pragas, doenças e nematoides do Cerrado.",
    "REVERB": "Produto para manejo de doenças em soja e milho com ação prolongada ou de espectro amplo.",
    "YIELDON": "Produto focado em maximizar a produtividade das lavouras.",
    "ORONDIS FLEXI": "Fungicida com flexibilidade de uso para controle de requeima, míldios e manchas.",
    "RIZOLIQ LLI": "Inoculante ou produto para tratamento de sementes que atua na rizosfera.",
    "ARVATICO": "Fungicida ou inseticida com ação específica para controle de doenças foliares ou pragas.",
    "VERDADERO": "Produto relacionado à saúde do solo ou nutrição vegetal.",
    "MIRAVIS": "Fungicida da família Miravis para controle de doenças.",
    "MIRAVIS PRO": "Fungicida premium da família Miravis para controle avançado de doenças.",
    "INSTIVO": "Lagarticida posicionado como especialista no controle de lagartas do gênero Spodoptera.",
    "CYPRESS": "Fungicida posicionado para últimas aplicações na soja, consolidando o manejo de doenças.",
    "CALARIS": "Herbicida composto por atrazina + mesotriona para controle de plantas daninhas no milho.",
    "SPONTA": "Inseticida para algodão com PLINAZOLIN® technology para controle de bicudo e outras pragas.",
    "INFLUX": "Inseticida lagarticida premium para controle de todas as lagartas, especialmente helicoverpa.",
    "JOINER": "Inseticida acaricida com tecnologia PLINAZOLIN para culturas hortifrúti.",
    "DUAL GOLD": "Herbicida para manejo de plantas daninhas.",
}

def extract_product_info(text: str) -> Tuple[str, str, str]:
    """Extrai informações do produto do texto da célula"""
    if not text or not text.strip():
        return None, None, None
    
    text = str(text).strip()
    
    # Remover emojis e marcadores
    clean_text = re.sub(r'[🔵🟠🟢🔴🟣🔃📲]', '', text).strip()
    
    # Padrões para extração
    patterns = {
        'product': r'\b([A-Z][A-Za-z\s]+(?:PRO|S|NEO|LLI|ELITE|COMPLETO|DUO|FLEXI|PLENO|XTRA)?)\b',
        'culture': r'\b(soja|milho|algodão|cana|trigo|HF|café|citrus|batata|melão|uva|tomate|multi)\b',
        'action': r'\b(depoimento|resultados|série|reforço|controle|lançamento|importância|jornada|conceito|vídeo|ação|diferenciais|awareness|problemática|glossário|manejo|aplicação|posicionamento)\b'
    }
    
    product_match = re.search(patterns['product'], clean_text, re.IGNORECASE)
    culture_match = re.search(patterns['culture'], clean_text, re.IGNORECASE)
    action_match = re.search(patterns['action'], clean_text, re.IGNORECASE)
    
    product = product_match.group(1).strip().upper() if product_match else None
    culture = culture_match.group(0).lower() if culture_match else "multi"
    action = action_match.group(0).lower() if action_match else "conscientização"
    
    return product, culture, action

def generate_context(content, product_name, culture, action, data_input, formato_principal):
    """Gera o texto de contexto discursivo usando LLM"""
    if not gemini_api_key:
        return "API key do Gemini não configurada. Contexto não disponível."
    
    # Determinar mês em português
    meses = {
        1: "janeiro", 2: "fevereiro", 3: "março", 4: "abril",
        5: "maio", 6: "junho", 7: "julho", 8: "agosto",
        9: "setembro", 10: "outubro", 11: "novembro", 12: "dezembro"
    }
    mes = meses[data_input.month]
    
    prompt = f"""
    Como redator especializado em agronegócio da Syngenta, elabore um texto contextual discursivo de 3-4 parágrafos para uma pauta de conteúdo.

    Informações da pauta:
    - Produto: {product_name}
    - Cultura: {culture}
    - Ação/tema: {action}
    - Mês de publicação: {mes}
    - Formato principal: {formato_principal}
    - Conteúdo original: {content}

    Descrição do produto: {PRODUCT_DESCRIPTIONS.get(product_name, 'Produto agrícola Syngenta')}

    Instruções:
    - Escreva em formato discursivo e fluido, com 3-4 parágrafos bem estruturados
    - Mantenha tom técnico mas acessível, adequado para produtores rurais
    - Contextualize a importância do tema para a cultura e época do ano
    - Explique por que este conteúdo é relevante neste momento
    - Inclua considerações sobre o público-alvo e objetivos da comunicação
    - Não repita literalmente a descrição do produto, mas a incorpore naturalmente no texto
    - Use linguagem persuasiva mas factual, baseada em dados técnicos

    Formato: Texto corrido em português brasileiro
    """
    
    try:
        response = modelo_texto.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"Erro ao gerar contexto: {str(e)}"

def generate_platform_strategy(product_name, culture, action, content):
    """Gera estratégia por plataforma usando Gemini"""
    if not gemini_api_key:
        return "API key do Gemini não configurada. Estratégias por plataforma não disponíveis."
    
    prompt = f"""
    Como especialista em mídias sociais para o agronegócio Syngenta, crie uma estratégia de conteúdo detalhada:

    PRODUTO: {product_name}
    CULTURA: {culture}
    AÇÃO: {action}
    CONTEÚDO ORIGINAL: {content}
    DESCRIÇÃO DO PRODUTO: {PRODUCT_DESCRIPTIONS.get(product_name, 'Produto agrícola Syngenta')}

    FORNECER ESTRATÉGIA PARA:
    - Instagram (Feed, Reels, Stories)
    - Facebook 
    - LinkedIn
    - WhatsApp Business
    - YouTube
    - Portal Mais Agro (blog)

    INCLUIR PARA CADA PLATAFORMA:
    1. Tipo de conteúdo recomendado
    2. Formato ideal (vídeo, carrossel, estático, etc.)
    3. Tom de voz apropriado
    4. CTA específico
    5. Melhores práticas

    Formato: Texto claro com seções bem definidas
    """
    
    try:
        response = modelo_texto.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"Erro ao gerar estratégia: {str(e)}"

def generate_briefing(content, product_name, culture, action, data_input, formato_principal):
    """Gera um briefing completo em formato de texto puro"""
    description = PRODUCT_DESCRIPTIONS.get(product_name, "Descrição do produto não disponível.")
    context = generate_context(content, product_name, culture, action, data_input, formato_principal)
    platform_strategy = generate_platform_strategy(product_name, culture, action, content)
    
    briefing = f"""
BRIEFING DE CONTEÚDO - {product_name} - {culture.upper()} - {action.upper()}

CONTEXTO E OBJETIVO
{context}

DESCRIÇÃO DO PRODUTO
{description}

ESTRATÉGIA POR PLATAFORMA
{platform_strategy}

FORMATOS SUGERIDOS
- Instagram: Reels + Stories + Feed post
- Facebook: Carrossel + Link post
- LinkedIn: Artigo + Post informativo
- WhatsApp: Card informativo + Link
- YouTube: Shorts + Vídeo explicativo
- Portal Mais Agro: Blog post + Webstories

CONTATOS E OBSERVAÇÕES
- Validar com especialista técnico
- Checar disponibilidade de imagens/vídeos
- Incluir CTA para portal Mais Agro
- Seguir guidelines de marca Syngenta
- Revisar compliance regulatório

DATA PREVISTA: {data_input.strftime('%d/%m/%Y')}
FORMATO PRINCIPAL: {formato_principal}
"""
    return briefing

# --- Interface Principal ---
st.sidebar.title(f"🤖 Bem-vindo, {st.session_state.user}!")
st.sidebar.info(f"**Agente selecionado:** {agente_selecionado['nome']}")

# Botão de logout na sidebar
if st.sidebar.button("🚪 Sair", key="logout_btn"):
    for key in ["logged_in", "user", "admin_password_correct", "admin_user", "agente_selecionado"]:
        if key in st.session_state:
            del st.session_state[key]
    st.rerun()

# Botão para trocar agente
if st.sidebar.button("🔄 Trocar Agente", key="trocar_agente_global"):
    st.session_state.agente_selecionado = None
    st.session_state.messages = []
    st.rerun()

st.title(f"Agente Social - {agente_selecionado['nome']}")

# Inicializar estado da sessão
if "messages" not in st.session_state:
    st.session_state.messages = []
if "segmentos_selecionados" not in st.session_state:
    st.session_state.segmentos_selecionados = ["system_prompt", "base_conhecimento", "comments", "planejamento"]
if "show_historico" not in st.session_state:
    st.session_state.show_historico = False

# Menu de abas - DETERMINAR QUAIS ABAS MOSTRAR
abas_base = [
    "💬 Chat", 
    "⚙️ Gerenciar Agentes", 
    "✅ Validação Unificada",
    "✨ Geração de Conteúdo",
    "📝 Resumo de Textos",
    "🌐 Busca Web",
    "📝 Revisão Ortográfica",
    "Monitoramento de Redes"
]

# Adicionar aba de Briefing Syngenta apenas se o agente for da Syngenta
if is_syngenta_agent(agente_selecionado['nome']):
    abas_base.append("📋 Briefing Syngenta")

# Criar abas dinamicamente
tabs = st.tabs(abas_base)

# Mapear abas para suas respectivas funcionalidades
tab_mapping = {}
for i, aba in enumerate(abas_base):
    tab_mapping[aba] = tabs[i]

# --- ABA: CHAT ---
with tab_mapping["💬 Chat"]:
    st.header("💬 Chat com Agente")
    
    # Inicializar session_state se não existir
    if 'messages' not in st.session_state:
        st.session_state.messages = []
    if 'segmentos_selecionados' not in st.session_state:
        st.session_state.segmentos_selecionados = []
    if 'show_historico' not in st.session_state:
        st.session_state.show_historico = False
    
    agente = st.session_state.agente_selecionado
    st.subheader(f"Conversando com: {agente['nome']}")
    
    # Controles de navegação no topo
    col1, col2, col3 = st.columns([1, 1, 1])
    
    with col1:
        if st.button("📚 Carregar Histórico", key="carregar_historico"):
            st.session_state.show_historico = not st.session_state.show_historico
            st.rerun()
    
    with col2:
        if st.button("🔄 Limpar Chat", key="limpar_chat"):
            st.session_state.messages = []
            if hasattr(st.session_state, 'historico_contexto'):
                st.session_state.historico_contexto = []
            st.success("Chat limpo!")
            st.rerun()
    
    with col3:
        if st.button("🔁 Trocar Agente", key="trocar_agente_chat"):
            st.session_state.agente_selecionado = None
            st.session_state.messages = []
            st.session_state.historico_contexto = []
            st.rerun()
    
    # Mostrar se há histórico carregado
    if hasattr(st.session_state, 'historico_contexto') and st.session_state.historico_contexto:
        st.info(f"📖 Usando histórico anterior com {len(st.session_state.historico_contexto)} mensagens como contexto")
    
    # Modal para seleção de histórico
    if st.session_state.show_historico:
        with st.expander("📚 Selecionar Histórico de Conversa", expanded=True):
            conversas_anteriores = listar_conversas(agente['_id'])
            
            if conversas_anteriores:
                for i, conversa in enumerate(conversas_anteriores[:10]):  # Últimas 10 conversas
                    col_hist1, col_hist2, col_hist3 = st.columns([3, 1, 1])
                    
                    with col_hist1:
                        # CORREÇÃO: Usar get() para evitar KeyError
                        data_display = conversa.get('data_formatada', conversa.get('data', 'Data desconhecida'))
                        mensagens_count = len(conversa.get('mensagens', []))
                        st.write(f"**{data_display}** - {mensagens_count} mensagens")
                    
                    with col_hist2:
                        if st.button("👀 Visualizar", key=f"ver_{i}"):
                            st.session_state.conversa_visualizada = conversa.get('mensagens', [])
                    
                    with col_hist3:
                        if st.button("📥 Usar", key=f"usar_{i}"):
                            st.session_state.messages = conversa.get('mensagens', [])
                            st.session_state.historico_contexto = conversa.get('mensagens', [])
                            st.session_state.show_historico = False
                            st.success(f"✅ Histórico carregado: {len(conversa.get('mensagens', []))} mensagens")
                            st.rerun()
                
                # Visualizar conversa selecionada
                if hasattr(st.session_state, 'conversa_visualizada'):
                    st.subheader("👀 Visualização do Histórico")
                    for msg in st.session_state.conversa_visualizada[-6:]:  # Últimas 6 mensagens
                        with st.chat_message(msg.get("role", "user")):
                            st.markdown(msg.get("content", ""))
                    
                    if st.button("Fechar Visualização", key="fechar_visualizacao"):
                        st.session_state.conversa_visualizada = None
                        st.rerun()
            else:
                st.info("Nenhuma conversa anterior encontrada")
    
    # Mostrar informações de herança se aplicável
    if 'agente_mae_id' in agente and agente['agente_mae_id']:
        agente_original = obter_agente(agente['_id'])
        if agente_original and agente_original.get('herdar_elementos'):
            st.info(f"🔗 Este agente herda {len(agente_original['herdar_elementos'])} elementos do agente mãe")
    
    # Controles de segmentos na sidebar do chat
    st.sidebar.subheader("🔧 Configurações do Agente")
    st.sidebar.write("Selecione quais bases de conhecimento usar:")
    
    segmentos_disponiveis = {
        "Prompt do Sistema": "system_prompt",
        "Brand Guidelines": "base_conhecimento", 
        "Comentários do Cliente": "comments",
        "Planejamento": "planejamento"
    }
    
    segmentos_selecionados = []
    for nome, chave in segmentos_disponiveis.items():
        if st.sidebar.checkbox(nome, value=chave in st.session_state.segmentos_selecionados, key=f"seg_{chave}"):
            segmentos_selecionados.append(chave)
    
    st.session_state.segmentos_selecionados = segmentos_selecionados
    
    # Exibir status dos segmentos
    if segmentos_selecionados:
        st.sidebar.success(f"✅ Usando {len(segmentos_selecionados)} segmento(s)")
    else:
        st.sidebar.warning("⚠️ Nenhum segmento selecionado")
    
    # Indicador de posição na conversa
    if len(st.session_state.messages) > 4:
        st.caption(f"📄 Conversa com {len(st.session_state.messages)} mensagens")
    
    # CORREÇÃO: Exibir histórico de mensagens DENTRO do contexto correto
    # Verificar se messages existe e é iterável
    if hasattr(st.session_state, 'messages') and st.session_state.messages:
        for message in st.session_state.messages:
            # Verificar se message é um dicionário e tem a chave 'role'
            if isinstance(message, dict) and "role" in message:
                with st.chat_message(message["role"]):
                    st.markdown(message.get("content", ""))
            else:
                # Se a estrutura não for a esperada, pular esta mensagem
                continue
    else:
        # Se não houver mensagens, mostrar estado vazio
        st.info("💬 Inicie uma conversa digitando uma mensagem abaixo!")
    
    # Input do usuário
    if prompt := st.chat_input("Digite sua mensagem..."):
        # Adicionar mensagem do usuário ao histórico
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)
        
        # Construir contexto com segmentos selecionados
        contexto = construir_contexto(
            agente, 
            st.session_state.segmentos_selecionados, 
            st.session_state.messages
        )
        
        # Gerar resposta
        with st.chat_message("assistant"):
            with st.spinner('Pensando...'):
                try:
                    resposta = modelo_texto.generate_content(contexto)
                    st.markdown(resposta.text)
                    
                    # Adicionar ao histórico
                    st.session_state.messages.append({"role": "assistant", "content": resposta.text})
                    
                    # Salvar conversa com segmentos utilizados
                    salvar_conversa(
                        agente['_id'], 
                        st.session_state.messages,
                        st.session_state.segmentos_selecionados
                    )
                    
                except Exception as e:
                    st.error(f"Erro ao gerar resposta: {str(e)}")

# --- ABA: GERENCIAMENTO DE AGENTES ---
with tab_mapping["⚙️ Gerenciar Agentes"]:
    st.header("Gerenciamento de Agentes")
    
    # Verificar autenticação apenas para gerenciamento
    if st.session_state.user != "admin":
        st.warning("Acesso restrito a administradores")
    else:
        # Verificar senha de admin
        if not check_admin_password():
            st.warning("Digite a senha de administrador")
        else:
            # Mostra o botão de logout admin
            if st.button("Logout Admin", key="admin_logout"):
                if "admin_password_correct" in st.session_state:
                    del st.session_state["admin_password_correct"]
                if "admin_user" in st.session_state:
                    del st.session_state["admin_user"]
                st.rerun()
            
            st.write(f'Bem-vindo administrador!')
            
            # Subabas para gerenciamento
            sub_tab1, sub_tab2, sub_tab3 = st.tabs(["Criar Agente", "Editar Agente", "Gerenciar Agentes"])
            
            with sub_tab1:
                st.subheader("Criar Novo Agente")
                
                with st.form("form_criar_agente"):
                    nome_agente = st.text_input("Nome do Agente:")
                    
                    # Seleção de categoria
                    categoria = st.selectbox(
                        "Categoria:",
                        ["Social", "SEO", "Conteúdo"],
                        help="Organize o agente por área de atuação"
                    )
                    
                    # Opção para criar como agente filho
                    criar_como_filho = st.checkbox("Criar como agente filho (herdar elementos)")
                    
                    agente_mae_id = None
                    herdar_elementos = []
                    
                    if criar_como_filho:
                        # Listar TODOS os agentes disponíveis para herança
                        agentes_mae = listar_agentes_para_heranca()
                        if agentes_mae:
                            agente_mae_options = {f"{agente['nome']} ({agente.get('categoria', 'Social')})": agente['_id'] for agente in agentes_mae}
                            agente_mae_selecionado = st.selectbox(
                                "Agente Mãe:",
                                list(agente_mae_options.keys()),
                                help="Selecione o agente do qual este agente irá herdar elementos"
                            )
                            agente_mae_id = agente_mae_options[agente_mae_selecionado]
                            
                            st.subheader("Elementos para Herdar")
                            herdar_elementos = st.multiselect(
                                "Selecione os elementos a herdar do agente mãe:",
                                ["system_prompt", "base_conhecimento", "comments", "planejamento"],
                                help="Estes elementos serão herdados do agente mãe se não preenchidos abaixo"
                            )
                        else:
                            st.info("Nenhum agente disponível para herança. Crie primeiro um agente mãe.")
                    
                    system_prompt = st.text_area("Prompt de Sistema:", height=150, 
                                                placeholder="Ex: Você é um assistente especializado em...",
                                                help="Deixe vazio se for herdar do agente mãe")
                    base_conhecimento = st.text_area("Brand Guidelines:", height=200,
                                                   placeholder="Cole aqui informações, diretrizes, dados...",
                                                   help="Deixe vazio se for herdar do agente mãe")
                    comments = st.text_area("Comentários do cliente:", height=200,
                                                   placeholder="Cole aqui os comentários de ajuste do cliente (Se houver)",
                                                   help="Deixe vazio se for herdar do agente mãe")
                    planejamento = st.text_area("Planejamento:", height=200,
                                               placeholder="Estratégias, planejamentos, cronogramas...",
                                               help="Deixe vazio se for herdar do agente mãe")
                    
                    submitted = st.form_submit_button("Criar Agente")
                    if submitted:
                        if nome_agente:
                            agente_id = criar_agente(
                                nome_agente, 
                                system_prompt, 
                                base_conhecimento, 
                                comments, 
                                planejamento,
                                categoria,
                                agente_mae_id if criar_como_filho else None,
                                herdar_elementos if criar_como_filho else []
                            )
                            st.success(f"Agente '{nome_agente}' criado com sucesso na categoria {categoria}!")
                        else:
                            st.error("Nome é obrigatório!")
            
            with sub_tab2:
                st.subheader("Editar Agente Existente")
                
                agentes = listar_agentes()
                if agentes:
                    agente_options = {agente['nome']: agente for agente in agentes}
                    agente_selecionado_nome = st.selectbox("Selecione o agente para editar:", 
                                                         list(agente_options.keys()))
                    
                    if agente_selecionado_nome:
                        agente = agente_options[agente_selecionado_nome]
                        
                        with st.form("form_editar_agente"):
                            novo_nome = st.text_input("Nome do Agente:", value=agente['nome'])
                            
                            # Categoria
                            nova_categoria = st.selectbox(
                                "Categoria:",
                                ["Social", "SEO", "Conteúdo"],
                                index=["Social", "SEO", "Conteúdo"].index(agente.get('categoria', 'Social')),
                                help="Organize o agente por área de atuação"
                            )
                            
                            # Informações de herança
                            if agente.get('agente_mae_id'):
                                agente_mae = obter_agente(agente['agente_mae_id'])
                                if agente_mae:
                                    st.info(f"🔗 Este agente é filho de: {agente_mae['nome']}")
                                    st.write(f"Elementos herdados: {', '.join(agente.get('herdar_elementos', []))}")
                            
                            # Opção para tornar independente
                            if agente.get('agente_mae_id'):
                                tornar_independente = st.checkbox("Tornar agente independente (remover herança)")
                                if tornar_independente:
                                    agente_mae_id = None
                                    herdar_elementos = []
                                else:
                                    agente_mae_id = agente.get('agente_mae_id')
                                    herdar_elementos = agente.get('herdar_elementos', [])
                            else:
                                agente_mae_id = None
                                herdar_elementos = []
                                # Opção para adicionar herança
                                adicionar_heranca = st.checkbox("Adicionar herança de agente mãe")
                                if adicionar_heranca:
                                    # Listar TODOS os agentes disponíveis para herança (excluindo o próprio)
                                    agentes_mae = listar_agentes_para_heranca(agente['_id'])
                                    if agentes_mae:
                                        agente_mae_options = {f"{agente_mae['nome']} ({agente_mae.get('categoria', 'Social')})": agente_mae['_id'] for agente_mae in agentes_mae}
                                        if agente_mae_options:
                                            agente_mae_selecionado = st.selectbox(
                                                "Agente Mãe:",
                                                list(agente_mae_options.keys()),
                                                help="Selecione o agente do qual este agente irá herdar elementos"
                                            )
                                            agente_mae_id = agente_mae_options[agente_mae_selecionado]
                                            herdar_elementos = st.multiselect(
                                                "Elementos para herdar:",
                                                ["system_prompt", "base_conhecimento", "comments", "planejamento"],
                                                default=herdar_elementos
                                            )
                                        else:
                                            st.info("Nenhum agente disponível para herança.")
                                    else:
                                        st.info("Nenhum agente disponível para herança.")
                            
                            novo_prompt = st.text_area("Prompt de Sistema:", value=agente['system_prompt'], height=150)
                            nova_base = st.text_area("Brand Guidelines:", value=agente.get('base_conhecimento', ''), height=200)
                            nova_comment = st.text_area("Comentários:", value=agente.get('comments', ''), height=200)
                            novo_planejamento = st.text_area("Planejamento:", value=agente.get('planejamento', ''), height=200)
                            
                            submitted = st.form_submit_button("Atualizar Agente")
                            if submitted:
                                if novo_nome:
                                    atualizar_agente(
                                        agente['_id'], 
                                        novo_nome, 
                                        novo_prompt, 
                                        nova_base, 
                                        nova_comment, 
                                        novo_planejamento,
                                        nova_categoria,
                                        agente_mae_id,
                                        herdar_elementos
                                    )
                                    st.success(f"Agente '{novo_nome}' atualizado com sucesso!")
                                    st.rerun()
                                else:
                                    st.error("Nome é obrigatório!")
                else:
                    st.info("Nenhum agente criado ainda.")
            
            with sub_tab3:
                st.subheader("Gerenciar Agentes")
                
                # Filtros por categoria
                categorias = ["Todos", "Social", "SEO", "Conteúdo"]
                categoria_filtro = st.selectbox("Filtrar por categoria:", categorias)
                
                agentes = listar_agentes()
                
                # Aplicar filtro
                if categoria_filtro != "Todos":
                    agentes = [agente for agente in agentes if agente.get('categoria') == categoria_filtro]
                
                if agentes:
                    for i, agente in enumerate(agentes):
                        with st.expander(f"{agente['nome']} - {agente.get('categoria', 'Social')} - Criado em {agente['data_criacao'].strftime('%d/%m/%Y')}"):
                            
                            # Mostrar informações de herança
                            if agente.get('agente_mae_id'):
                                agente_mae = obter_agente(agente['agente_mae_id'])
                                if agente_mae:
                                    st.write(f"**🔗 Herda de:** {agente_mae['nome']}")
                                    st.write(f"**Elementos herdados:** {', '.join(agente.get('herdar_elementos', []))}")
                            
                            st.write(f"**Prompt de Sistema:** {agente['system_prompt'][:100]}..." if agente['system_prompt'] else "**Prompt de Sistema:** (herdado ou vazio)")
                            if agente.get('base_conhecimento'):
                                st.write(f"**Brand Guidelines:** {agente['base_conhecimento'][:200]}...")
                            if agente.get('comments'):
                                st.write(f"**Comentários do cliente:** {agente['comments'][:200]}...")
                            if agente.get('planejamento'):
                                st.write(f"**Planejamento:** {agente['planejamento'][:200]}...")
                            
                            col1, col2 = st.columns(2)
                            with col1:
                                if st.button("Selecionar para Chat", key=f"select_{i}"):
                                    st.session_state.agente_selecionado = obter_agente_com_heranca(agente['_id'])
                                    st.session_state.messages = []
                                    st.success(f"Agente '{agente['nome']}' selecionado!")
                                    st.rerun()
                            with col2:
                                if st.button("Desativar", key=f"delete_{i}"):
                                    desativar_agente(agente['_id'])
                                    st.success(f"Agente '{agente['nome']}' desativado!")
                                    st.rerun()
                else:
                    st.info("Nenhum agente encontrado para esta categoria.")

# --- ABA: BRIEFING SYNGENTA (APENAS SE AGENTE FOR DA SYNGENTA) ---
if "📋 Briefing Syngenta" in tab_mapping:
    with tab_mapping["📋 Briefing Syngenta"]:
        st.header("📋 Gerador de Briefings - SYN")
        st.markdown("Digite o conteúdo da célula do calendário para gerar um briefing completo no padrão SYN.")
        
        # Abas para diferentes modos de operação
        tab1, tab2 = st.tabs(["Briefing Individual", "Processamento em Lote (CSV)"])
        
        with tab1:
            st.markdown("### Digite o conteúdo da célula do calendário")

            content_input = st.text_area(
                "Conteúdo da célula:",
                placeholder="Ex: megafol - série - potencial máximo, todo o tempo",
                height=100,
                help="Cole aqui o conteúdo exato da célula do calendário do Sheets",
                key="individual_content"
            )

            # Campos opcionais para ajuste
            col1, col2 = st.columns(2)

            with col1:
                data_input = st.date_input("Data prevista:", value=datetime.datetime.now(), key="individual_date")

            with col2:
                formato_principal = st.selectbox(
                    "Formato principal:",
                    ["Reels + capa", "Carrossel + stories", "Blog + redes", "Vídeo + stories", "Multiplataforma"],
                    key="individual_format"
                )

            generate_btn = st.button("Gerar Briefing Individual", type="primary", key="individual_btn")

            # Processamento e exibição do briefing individual
            if generate_btn and content_input:
                with st.spinner("Analisando conteúdo e gerando briefing..."):
                    # Extrair informações do produto
                    product, culture, action = extract_product_info(content_input)
                    
                    if product and product in PRODUCT_DESCRIPTIONS:
                        # Gerar briefing completo
                        briefing = generate_briefing(content_input, product, culture, action, data_input, formato_principal)
                        
                        # Exibir briefing
                        st.markdown("## Briefing Gerado")
                        st.text(briefing)
                        
                        # Botão de download
                        st.download_button(
                            label="Baixar Briefing",
                            data=briefing,
                            file_name=f"briefing_{product}_{data_input.strftime('%Y%m%d')}.txt",
                            mime="text/plain",
                            key="individual_download"
                        )
                        
                        # Informações extras
                        with st.expander("Informações Extraídas"):
                            st.write(f"Produto: {product}")
                            st.write(f"Cultura: {culture}")
                            st.write(f"Ação: {action}")
                            st.write(f"Data: {data_input.strftime('%d/%m/%Y')}")
                            st.write(f"Formato principal: {formato_principal}")
                            st.write(f"Descrição: {PRODUCT_DESCRIPTIONS[product]}")
                            
                    elif product:
                        st.warning(f"Produto '{product}' não encontrado no dicionário. Verifique a grafia.")
                        st.info("Produtos disponíveis: " + ", ".join(list(PRODUCT_DESCRIPTIONS.keys())[:10]) + "...")
                    else:
                        st.error("Não foi possível identificar um produto no conteúdo. Tente formatos como:")
                        st.code("""
                        megafol - série - potencial máximo, todo o tempo
                        verdavis - soja - depoimento produtor
                        engeo pleno s - milho - controle percevejo
                        miravis duo - algodão - reforço preventivo
                        """)

        with tab2:
            st.markdown("### Processamento em Lote via CSV")
            
            st.info("""
            Faça upload de um arquivo CSV exportado do Google Sheets.
            O sistema irá processar cada linha a partir da segunda linha (ignorando cabeçalhos)
            e gerar briefings apenas para as linhas que contêm produtos reconhecidos.
            """)
            
            uploaded_file = st.file_uploader(
                "Escolha o arquivo CSV", 
                type=['csv'],
                help="Selecione o arquivo CSV exportado do Google Sheets"
            )
            
            if uploaded_file is not None:
                try:
                    # Ler o CSV
                    df = pd.read_csv(uploaded_file)
                    st.success(f"CSV carregado com sucesso! {len(df)} linhas encontradas.")
                    
                    # Mostrar prévia do arquivo
                    with st.expander("Visualizar primeiras linhas do CSV"):
                        st.dataframe(df.head())
                    
                    # Configurações para processamento em lote
                    st.markdown("### Configurações do Processamento em Lote")
                    col1, col2 = st.columns(2)
                    
                    with col1:
                        data_padrao = st.date_input(
                            "Data padrão para todos os briefings:",
                            value=datetime.datetime.now(),
                            key="batch_date"
                        )
                    
                    with col2:
                        formato_padrao = st.selectbox(
                            "Formato principal padrão:",
                            ["Reels + capa", "Carrossel + stories", "Blog + redes", "Vídeo + stories", "Multiplataforma"],
                            key="batch_format"
                        )
                    
                    # Identificar coluna com conteúdo
                    colunas = df.columns.tolist()
                    coluna_conteudo = st.selectbox(
                        "Selecione a coluna que contém o conteúdo das células:",
                        colunas,
                        help="Selecione a coluna que contém os textos das células do calendário"
                    )
                    
                    processar_lote = st.button("Processar CSV e Gerar Briefings", type="primary", key="batch_btn")
                    
                    if processar_lote:
                        briefings_gerados = []
                        linhas_processadas = 0
                        linhas_com_produto = 0
                        
                        progress_bar = st.progress(0)
                        status_text = st.empty()
                        
                        for index, row in df.iterrows():
                            linhas_processadas += 1
                            progress_bar.progress(linhas_processadas / len(df))
                            status_text.text(f"Processando linha {linhas_processadas} de {len(df)}...")
                            
                            # Pular a primeira linha (cabeçalhos)
                            if index == 0:
                                continue
                            
                            # Obter conteúdo da célula
                            content = str(row[coluna_conteudo]) if pd.notna(row[coluna_conteudo]) else ""
                            
                            if content:
                                # Extrair informações do produto
                                product, culture, action = extract_product_info(content)
                                
                                if product and product in PRODUCT_DESCRIPTIONS:
                                    linhas_com_produto += 1
                                    # Gerar briefing
                                    briefing = generate_briefing(
                                        content, 
                                        product, 
                                        culture, 
                                        action, 
                                        data_padrao, 
                                        formato_padrao
                                    )
                                    
                                    briefings_gerados.append({
                                        'linha': index + 1,
                                        'produto': product,
                                        'conteudo': content,
                                        'briefing': briefing,
                                        'arquivo': f"briefing_{product}_{index+1}.txt"
                                    })
                        
                        progress_bar.empty()
                        status_text.empty()
                        
                        # Resultados do processamento
                        st.success(f"Processamento concluído! {linhas_com_produto} briefings gerados de {linhas_processadas-1} linhas processadas.")
                        
                        if briefings_gerados:
                            # Exibir resumo
                            st.markdown("### Briefings Gerados")
                            resumo_df = pd.DataFrame([{
                                'Linha': b['linha'],
                                'Produto': b['produto'],
                                'Conteúdo': b['conteudo'][:50] + '...' if len(b['conteudo']) > 50 else b['conteudo']
                            } for b in briefings_gerados])
                            
                            st.dataframe(resumo_df)
                            
                            # Criar arquivo ZIP com todos os briefings
                            import zipfile
                            from io import BytesIO
                            
                            zip_buffer = BytesIO()
                            with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
                                for briefing_info in briefings_gerados:
                                    zip_file.writestr(
                                        briefing_info['arquivo'], 
                                        briefing_info['briefing']
                                    )
                            
                            zip_buffer.seek(0)
                            
                            # Botão para download do ZIP
                            st.download_button(
                                label="📥 Baixar Todos os Briefings (ZIP)",
                                data=zip_buffer,
                                file_name="briefings_syngenta.zip",
                                mime="application/zip",
                                key="batch_download_zip"
                            )
                            
                            # Também permitir download individual
                            st.markdown("---")
                            st.markdown("### Download Individual")
                            
                            for briefing_info in briefings_gerados:
                                col1, col2 = st.columns([3, 1])
                                with col1:
                                    st.text(f"Linha {briefing_info['linha']}: {briefing_info['produto']} - {briefing_info['conteudo'][:30]}...")
                                with col2:
                                    st.download_button(
                                        label="📄 Baixar",
                                        data=briefing_info['briefing'],
                                        file_name=briefing_info['arquivo'],
                                        mime="text/plain",
                                        key=f"download_{briefing_info['linha']}"
                                    )
                        else:
                            st.warning("Nenhum briefing foi gerado. Verifique se o CSV contém produtos reconhecidos.")
                            st.info("Produtos reconhecidos: " + ", ".join(list(PRODUCT_DESCRIPTIONS.keys())[:15]) + "...")
                            
                except Exception as e:
                    st.error(f"Erro ao processar o arquivo CSV: {str(e)}")

        # Seção de exemplos
        with st.expander("Exemplos de Conteúdo", expanded=True):
            st.markdown("""
            Formatos Reconhecidos:

            Padrão: PRODUTO - CULTURA - AÇÃO ou PRODUTO - AÇÃO

            Exemplos:
            - megafol - série - potencial máximo, todo o tempo
            - verdavis - milho - resultados do produto
            - engeo pleno s - soja - resultados GTEC
            - miravis duo - algodão - depoimento produtor
            - axial - trigo - reforço pós-emergente
            - manejo limpo - importância manejo antecipado
            - certano HF - a jornada de certano
            - elestal neo - soja - depoimento de produtor
            - fortenza - a jornada da semente mais forte - EP 01
            - reverb - vídeo conceito
            """)

        # Lista de produtos reconhecidos
        with st.expander("Produtos Reconhecidos"):
            col1, col2, col3 = st.columns(3)
            products = list(PRODUCT_DESCRIPTIONS.keys())
            
            with col1:
                for product in products[:10]:
                    st.write(f"• {product}")
            
            with col2:
                for product in products[10:20]:
                    st.write(f"• {product}")
            
            with col3:
                for product in products[20:]:
                    st.write(f"• {product}")

        # Rodapé
        st.markdown("---")
        st.caption("Ferramenta de geração automática de briefings - Padrão SYN. Digite o conteúdo da célula do calendário para gerar briefings completos.")

# --- ABA: VALIDAÇÃO UNIFICADA ---
with tab_mapping["✅ Validação Unificada"]:
    st.header("✅ Validação Unificada de Conteúdo")
    
    if not st.session_state.get('agente_selecionado'):
        st.info("Selecione um agente primeiro na aba de Chat")
    else:
        agente = st.session_state.agente_selecionado
        st.subheader(f"Validação com: {agente.get('nome', 'Agente')}")
        
        # Subabas para diferentes tipos de validação
        subtab_imagem, subtab_texto = st.tabs(["🖼️ Validação de Imagem", "📄 Validação de Documentos"])
        
        with subtab_imagem:
            st.subheader("🖼️ Validação de Imagem")
            
            uploaded_images = st.file_uploader(
                "Carregue uma ou mais imagens para análise", 
                type=["jpg", "jpeg", "png", "webp"], 
                key="image_upload_validacao",
                accept_multiple_files=True,
                help="As imagens serão analisadas individualmente conforme as diretrizes de branding do agente"
            )
            
            if uploaded_images:
                st.success(f"✅ {len(uploaded_images)} imagem(ns) carregada(s)")
                
                # Botão para validar todas as imagens
                if st.button("🔍 Validar Todas as Imagens", type="primary", key="validar_imagens_multiplas"):
                    
                    # Lista para armazenar resultados
                    resultados_analise = []
                    
                    # Loop através de cada imagem
                    for idx, uploaded_image in enumerate(uploaded_images):
                        with st.spinner(f'Analisando imagem {idx+1} de {len(uploaded_images)}: {uploaded_image.name}...'):
                            try:
                                # Criar container para cada imagem
                                with st.container():
                                    st.markdown("---")
                                    col_img, col_info = st.columns([2, 1])
                                    
                                    with col_img:
                                        # Exibir imagem
                                        image = Image.open(uploaded_image)
                                        st.image(image, use_container_width=True, caption=f"Imagem {idx+1}: {uploaded_image.name}")
                                    
                                    with col_info:
                                        # Informações da imagem
                                        st.metric("📐 Dimensões", f"{image.width} x {image.height}")
                                        st.metric("📊 Formato", uploaded_image.type)
                                        st.metric("📁 Tamanho", f"{uploaded_image.size / 1024:.1f} KB")
                                    
                                    # Análise individual
                                    with st.expander(f"📋 Análise Detalhada - Imagem {idx+1}", expanded=True):
                                        try:
                                            # Construir contexto com base de conhecimento do agente
                                            contexto = ""
                                            if "base_conhecimento" in agente:
                                                contexto = f"""
                                                DIRETRIZES DE BRANDING DO AGENTE:
                                                {agente['base_conhecimento']}
                                                
                                                Analise esta imagem e verifique se está alinhada com as diretrizes de branding acima. Ademais, analise o
                                                alinhamento tanto ortogtáficamente como alinhamento com a marca de todo ou qualquer texto na imagem analisada.
                                                """
                                            
                                            prompt_analise = f"""
                                            {contexto}
                                            
                                            Analise esta imagem e verifique o alinhamento (tanto imagem como texto na imagem analisado ortograficamente e em termos de alinhamento com branding. Revise e corrija o texto também) com as diretrizes de branding.
                                            
                                            Forneça a análise em formato claro:
                                            
                                            ## 🖼️ RELATÓRIO DE ALINHAMENTO - IMAGEM {idx+1}
                                            
                                            **Arquivo:** {uploaded_image.name}
                                            **Dimensões:** {image.width} x {image.height}
                                            
                                            ### 🎯 RESUMO DA IMAGEM
                                            [Avaliação geral de conformidade visual e textual]
                                            
                                            ### ✅ ELEMENTOS ALINHADOS 
                                            - [Itens visuais e textuais que seguem as diretrizes]
                                            
                                            ### ⚠️ ELEMENTOS FORA DO PADRÃO
                                            - [Itens visuais e textuais que não seguem as diretrizes]
                                            
                                            ### 💡 RECOMENDAÇÕES
                                            - [Sugestões para melhorar o alinhamento visual e textual]
                                            
                                            ### 🎨 ASPECTOS TÉCNICOS
                                            - [Composição, cores, tipografia, etc.]
                                            """
                                            
                                            # Processar imagem
                                            response = modelo_vision.generate_content([
                                                prompt_analise,
                                                {"mime_type": "image/jpeg", "data": uploaded_image.getvalue()}
                                            ])
                                            
                                            st.markdown(response.text)
                                            
                                            # Armazenar resultado
                                            resultados_analise.append({
                                                'nome': uploaded_image.name,
                                                'indice': idx,
                                                'analise': response.text,
                                                'dimensoes': f"{image.width}x{image.height}",
                                                'tamanho': uploaded_image.size
                                            })
                                            
                                        except Exception as e:
                                            st.error(f"❌ Erro ao processar imagem {uploaded_image.name}: {str(e)}")
                                            resultados_analise.append({
                                                'nome': uploaded_image.name,
                                                'indice': idx,
                                                'analise': f"Erro na análise: {str(e)}",
                                                'dimensoes': f"{image.width}x{image.height}",
                                                'tamanho': uploaded_image.size
                                            })
                                
                                # Separador visual entre imagens
                                if idx < len(uploaded_images) - 1:
                                    st.markdown("---")
                                    
                            except Exception as e:
                                st.error(f"❌ Erro ao carregar imagem {uploaded_image.name}: {str(e)}")
                    
                    # Resumo executivo
                    st.markdown("---")
                    st.subheader("📋 Resumo Executivo")
                    
                    col_resumo1, col_resumo2, col_resumo3 = st.columns(3)
                    with col_resumo1:
                        st.metric("📊 Total de Imagens", len(uploaded_images))
                    with col_resumo2:
                        st.metric("✅ Análises Concluídas", len(resultados_analise))
                    with col_resumo3:
                        st.metric("🖼️ Processadas", len(uploaded_images))
                    
                    # Botão para download do relatório consolidado
                    if st.button("📥 Exportar Relatório Completo", key="exportar_relatorio"):
                        relatorio = f"""
                        # RELATÓRIO DE VALIDAÇÃO DE IMAGENS
                        
                        **Agente:** {agente.get('nome', 'N/A')}
                        **Data:** {datetime.datetime.now().strftime('%d/%m/%Y %H:%M')}
                        **Total de Imagens:** {len(uploaded_images)}
                        
                        ## RESUMO EXECUTIVO
                        {chr(10).join([f"{idx+1}. {img.name}" for idx, img in enumerate(uploaded_images)])}
                        
                        ## ANÁLISES INDIVIDUAIS
                        {chr(10).join([f'### {res["nome"]} {chr(10)}{res["analise"]}' for res in resultados_analise])}
                        """
                        
                        st.download_button(
                            "💾 Baixar Relatório em TXT",
                            data=relatorio,
                            file_name=f"relatorio_validacao_imagens_{datetime.datetime.now().strftime('%Y%m%d_%H%M')}.txt",
                            mime="text/plain"
                        )
            
            else:
                st.info("📁 Carregue uma ou mais imagens para iniciar a validação de branding")
        
        with subtab_texto:
            st.subheader("📄 Validação de Documentos e Texto")
            
            # Container principal com duas colunas
            col_entrada, col_saida = st.columns([1, 1])
            
            with col_entrada:
                st.markdown("### 📥 Entrada de Conteúdo")
                
                # Opção 1: Texto direto
                texto_input = st.text_area(
                    "**✍️ Digite o texto para validação:**", 
                    height=150, 
                    key="texto_validacao",
                    placeholder="Cole aqui o texto que deseja validar...",
                    help="O texto será analisado conforme as diretrizes de branding do agente"
                )
                
                # Opção 2: Upload de múltiplos arquivos
                st.markdown("### 📎 Ou carregue arquivos")
                
                arquivos_documentos = st.file_uploader(
                    "**Documentos suportados:** PDF, PPTX, TXT, DOCX",
                    type=['pdf', 'pptx', 'txt', 'docx'],
                    accept_multiple_files=True,
                    key="arquivos_documentos_validacao",
                    help="Arquivos serão convertidos para texto e validados automaticamente"
                )
                
                # Botão de validação
                if st.button("✅ Validar Conteúdo", type="primary", key="validate_documents", use_container_width=True):
                    st.session_state.validacao_triggered = True
            
            with col_saida:
                st.markdown("### 📊 Resultados")
                
                if st.session_state.get('validacao_triggered'):
                    # Processar todos os conteúdos
                    todos_textos = []
                    arquivos_processados = []
                    
                    # Adicionar texto manual se existir
                    if texto_input and texto_input.strip():
                        todos_textos.append({
                            'nome': 'Texto_Manual',
                            'conteudo': texto_input,
                            'tipo': 'texto_direto',
                            'tamanho': len(texto_input)
                        })
                    
                    # Processar arquivos uploadados
                    if arquivos_documentos:
                        for arquivo in arquivos_documentos:
                            with st.spinner(f"Processando {arquivo.name}..."):
                                try:
                                    texto_extraido = ""
                                    
                                    if arquivo.type == "application/pdf":
                                        texto_extraido = extract_text_from_pdf(arquivo)
                                    elif arquivo.type == "application/vnd.openxmlformats-officedocument.presentationml.presentation":
                                        texto_extraido = extract_text_from_pptx(arquivo)
                                    elif arquivo.type in ["text/plain", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"]:
                                        texto_extraido = extrair_texto_arquivo(arquivo)
                                    else:
                                        st.warning(f"Tipo de arquivo não suportado: {arquivo.name}")
                                        continue
                                    
                                    if texto_extraido and texto_extraido.strip():
                                        todos_textos.append({
                                            'nome': arquivo.name,
                                            'conteudo': texto_extraido,
                                            'tipo': arquivo.type,
                                            'tamanho': len(texto_extraido)
                                        })
                                        arquivos_processados.append(arquivo.name)
                                    
                                except Exception as e:
                                    st.error(f"❌ Erro ao processar {arquivo.name}: {str(e)}")
                    
                    # Verificar se há conteúdo para validar
                    if not todos_textos:
                        st.warning("⚠️ Nenhum conteúdo válido encontrado para validação.")
                    else:
                        st.success(f"✅ {len(todos_textos)} documento(s) processado(s) com sucesso!")
                        
                        # Exibir estatísticas rápidas
                        col_docs, col_palavras, col_chars = st.columns(3)
                        with col_docs:
                            st.metric("📄 Documentos", len(todos_textos))
                        with col_palavras:
                            total_palavras = sum(len(doc['conteudo'].split()) for doc in todos_textos)
                            st.metric("📝 Palavras", total_palavras)
                        with col_chars:
                            total_chars = sum(doc['tamanho'] for doc in todos_textos)
                            st.metric("🔤 Caracteres", f"{total_chars:,}")
                        
                        # Análise individual por documento
                        st.markdown("---")
                        st.subheader("📋 Análise Individual por Documento")
                        
                        for doc in todos_textos:
                            with st.expander(f"📄 {doc['nome']} - {doc['tamanho']} chars", expanded=False):
                                # Preview do conteúdo
                                preview = doc['conteudo'][:500] + "..." if len(doc['conteudo']) > 500 else doc['conteudo']
                                st.text_area(
                                    f"Preview - {doc['nome']}",
                                    value=preview,
                                    height=150,
                                    key=f"preview_{doc['nome']}",
                                    disabled=True
                                )
                                
                                # Análise de branding
                                with st.spinner(f"Analisando {doc['nome']}..."):
                                    try:
                                        contexto = ""
                                        if "base_conhecimento" in agente:
                                            contexto = f"""
                                            DIRETRIZES DE BRANDING DO AGENTE:
                                            {agente['base_conhecimento']}
                                            """
                                        
                                        prompt_analise = f"""
                                        {contexto}
                                        
                                        ANALISE O SEGUINTE CONTEÚDO:
                                        
                                        {doc['conteudo'][:10000]}  # Limitar para não exceder tokens
                                        
                                        Forneça uma análise detalhada em português:
                                        
                                        ## 📊 RELATÓRIO DE ALINHAMENTO - {doc['nome']}
                                        
                                        ### 🎯 RESUMO EXECUTIVO
                                        [Avaliação geral em 1-2 parágrafos]
                                        
                                        ### ✅ PONTOS FORTES
                                        - [Aspectos alinhados com as diretrizes]
                                        
                                        ### ⚠️ PONTOS DE ATENÇÃO
                                        - [Desvios das diretrizes]
                                        
                                        ### 💡 RECOMENDAÇÕES
                                        - [Sugestões específicas para melhorar]
                                        
                                        ### 🎨 TOM E LINGUAGEM
                                        - [Análise do tom e adequação]
                                        """
                                        
                                        resposta = modelo_texto.generate_content(prompt_analise)
                                        st.markdown(resposta.text)
                                        
                                    except Exception as e:
                                        st.error(f"❌ Erro na análise de {doc['nome']}: {str(e)}")
                        
                        # Relatório consolidado
                        st.markdown("---")
                        st.subheader("📑 Relatório Consolidado")
                        
                        # Botão para exportar
                        if st.button("📥 Exportar Relatório Completo", key="exportar_relatorio_completo"):
                            relatorio = f"""
                            # RELATÓRIO DE VALIDAÇÃO DE CONTEÚDO
                            
                            **Agente:** {agente.get('nome', 'N/A')}
                            **Data:** {datetime.datetime.now().strftime('%d/%m/%Y %H:%M')}
                            **Total de Documentos:** {len(todos_textos)}
                            
                            ## DOCUMENTOS ANALISADOS:
                            {chr(10).join([f"{idx+1}. {doc['nome']} ({doc['tipo']}) - {doc['tamanho']} caracteres" for idx, doc in enumerate(todos_textos)])}
                            
                            ## ANÁLISES INDIVIDUAIS:
                            {chr(10).join([f'### {doc["nome"]} {chr(10)}[Análise individual aqui]' for doc in todos_textos])}
                            """
                            
                            st.download_button(
                                "💾 Baixar Relatório em TXT",
                                data=relatorio,
                                file_name=f"relatorio_validacao_{datetime.datetime.now().strftime('%Y%m%d_%H%M')}.txt",
                                mime="text/plain"
                            )
                
                else:
                    # Estado inicial - instruções
                    st.info("""
                    **📋 Como usar:**
                    1. **Digite texto** diretamente OU **carregue arquivos** (PDF, PPTX, TXT, DOCX)
                    2. Clique em **"Validar Conteúdo"**
                    
                    **✅ Suporta:**
                    - 📄 PDF (apresentações, documentos)
                    - 🎯 PPTX (apresentações PowerPoint)  
                    - 📝 TXT (arquivos de texto)
                    - 📋 DOCX (documentos Word)
                    - ✍️ Texto direto
                    """)
            
            # Funções de extração
            def extract_text_from_pdf(file):
                """Extrai texto de arquivos PDF"""
                try:
                    import PyPDF2
                    pdf_reader = PyPDF2.PdfReader(file)
                    text = ""
                    for page in pdf_reader.pages:
                        text += page.extract_text() + "\n"
                    return text
                except Exception as e:
                    return f"Erro na extração PDF: {str(e)}"
            
            def extract_text_from_pptx(file):
                """Extrai texto de arquivos PPTX"""
                try:
                    from pptx import Presentation
                    prs = Presentation(file)
                    text = ""
                    for slide_number, slide in enumerate(prs.slides, 1):
                        text += f"\n--- Slide {slide_number} ---\n"
                        for shape in slide.shapes:
                            if hasattr(shape, "text") and shape.text:
                                text += shape.text + "\n"
                    return text
                except Exception as e:
                    return f"Erro na extração PPTX: {str(e)}"
            
            def extrair_texto_arquivo(file):
                """Extrai texto de arquivos TXT e DOCX"""
                try:
                    if file.type == "text/plain":
                        return str(file.read(), "utf-8")
                    elif file.type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
                        # Implementar extração para DOCX se necessário
                        return f"Conteúdo do arquivo DOCX: {file.name}"
                    else:
                        return f"Tipo não suportado: {file.type}"
                except Exception as e:
                    return f"Erro na extração: {str(e)}"
# --- ABA: GERAÇÃO DE CONTEÚDO ---
with tab_mapping["✨ Geração de Conteúdo"]:
    st.header("✨ Geração de Conteúdo com Múltiplos Insumos")
    
    # Conexão com MongoDB para briefings
    try:
        client2 = MongoClient("mongodb+srv://gustavoromao3345:RqWFPNOJQfInAW1N@cluster0.5iilj.mongodb.net/auto_doc?retryWrites=true&w=majority&ssl=true&ssl_cert_reqs=CERT_NONE&tlsAllowInvalidCertificates=true")
        db_briefings = client2['briefings_Broto_Tecnologia']
        collection_briefings = db_briefings['briefings']
        mongo_connected_conteudo = True
    except Exception as e:
        st.error(f"Erro na conexão com MongoDB: {str(e)}")
        mongo_connected_conteudo = False

    # Função para extrair texto de diferentes tipos de arquivo
    def extrair_texto_arquivo(arquivo):
        """Extrai texto de diferentes formatos de arquivo"""
        try:
            extensao = arquivo.name.split('.')[-1].lower()
            
            if extensao == 'pdf':
                return extrair_texto_pdf(arquivo)
            elif extensao == 'txt':
                return extrair_texto_txt(arquivo)
            elif extensao in ['pptx', 'ppt']:
                return extrair_texto_pptx(arquivo)
            elif extensao in ['docx', 'doc']:
                return extrair_texto_docx(arquivo)
            else:
                return f"Formato {extensao} não suportado para extração de texto."
                
        except Exception as e:
            return f"Erro ao extrair texto do arquivo {arquivo.name}: {str(e)}"

    def extrair_texto_pdf(arquivo):
        """Extrai texto de arquivos PDF"""
        try:
            import PyPDF2
            pdf_reader = PyPDF2.PdfReader(arquivo)
            texto = ""
            for pagina in pdf_reader.pages:
                texto += pagina.extract_text() + "\n"
            return texto
        except Exception as e:
            return f"Erro na leitura do PDF: {str(e)}"

    def extrair_texto_txt(arquivo):
        """Extrai texto de arquivos TXT"""
        try:
            return arquivo.read().decode('utf-8')
        except:
            try:
                return arquivo.read().decode('latin-1')
            except Exception as e:
                return f"Erro na leitura do TXT: {str(e)}"

    def extrair_texto_pptx(arquivo):
        """Extrai texto de arquivos PowerPoint"""
        try:
            from pptx import Presentation
            import io
            prs = Presentation(io.BytesIO(arquivo.read()))
            texto = ""
            for slide in prs.slides:
                for shape in slide.shapes:
                    if hasattr(shape, "text"):
                        texto += shape.text + "\n"
            return texto
        except Exception as e:
            return f"Erro na leitura do PowerPoint: {str(e)}"

    def extrair_texto_docx(arquivo):
        """Extrai texto de arquivos Word"""
        try:
            import docx
            import io
            doc = docx.Document(io.BytesIO(arquivo.read()))
            texto = ""
            for para in doc.paragraphs:
                texto += para.text + "\n"
            return texto
        except Exception as e:
            return f"Erro na leitura do Word: {str(e)}"

    # Layout principal
    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.subheader("📝 Fontes de Conteúdo")
        
        # Opção 1: Upload de múltiplos arquivos
        st.write("**📎 Upload de Arquivos (PDF, TXT, PPTX, DOCX):**")
        arquivos_upload = st.file_uploader(
            "Selecione um ou mais arquivos:",
            type=['pdf', 'txt', 'pptx', 'ppt', 'docx', 'doc'],
            accept_multiple_files=True,
            help="Arquivos serão convertidos para texto e usados como base para geração de conteúdo"
        )
        
        # Processar arquivos uploadados
        textos_arquivos = ""
        if arquivos_upload:
            st.success(f"✅ {len(arquivos_upload)} arquivo(s) carregado(s)")
            
            with st.expander("📋 Visualizar Conteúdo dos Arquivos", expanded=False):
                for i, arquivo in enumerate(arquivos_upload):
                    st.write(f"**{arquivo.name}** ({arquivo.size} bytes)")
                    with st.spinner(f"Processando {arquivo.name}..."):
                        texto_extraido = extrair_texto_arquivo(arquivo)
                        textos_arquivos += f"\n\n--- CONTEÚDO DE {arquivo.name.upper()} ---\n{texto_extraido}"
                        
                        # Mostrar preview
                        if len(texto_extraido) > 500:
                            st.text_area(f"Preview - {arquivo.name}", 
                                       value=texto_extraido[:500] + "...", 
                                       height=100,
                                       key=f"preview_{i}")
                        else:
                            st.text_area(f"Preview - {arquivo.name}", 
                                       value=texto_extraido, 
                                       height=100,
                                       key=f"preview_{i}")
        
        # Opção 2: Selecionar briefing do banco de dados
        st.write("**🗃️ Briefing do Banco de Dados:**")
        if mongo_connected_conteudo:
            briefings_disponiveis = list(collection_briefings.find().sort("data_criacao", -1).limit(20))
            if briefings_disponiveis:
                briefing_options = {f"{briefing['nome_projeto']} ({briefing['tipo']}) - {briefing['data_criacao'].strftime('%d/%m/%Y')}": briefing for briefing in briefings_disponiveis}
                briefing_selecionado = st.selectbox("Escolha um briefing:", list(briefing_options.keys()))
                
                if briefing_selecionado:
                    briefing_data = briefing_options[briefing_selecionado]
                    st.info(f"Briefing selecionado: {briefing_data['nome_projeto']}")
            else:
                st.info("Nenhum briefing encontrado no banco de dados.")
        else:
            st.warning("Conexão com MongoDB não disponível")
        
        # Opção 3: Inserir briefing manualmente
        st.write("**✍️ Briefing Manual:**")
        briefing_manual = st.text_area("Ou cole o briefing completo aqui:", height=150,
                                      placeholder="""Exemplo:
Título: Campanha de Lançamento
Objetivo: Divulgar novo produto
Público-alvo: Empresários...
Pontos-chave: [lista os principais pontos]""")
        
        # Transcrição de áudio/vídeo
        st.write("**🎤 Transcrição de Áudio/Video:**")
        arquivos_midia = st.file_uploader(
            "Áudios/Vídeos para transcrição:",
            type=['mp3', 'wav', 'mp4', 'mov', 'avi'],
            accept_multiple_files=True,
            help="Arquivos de mídia serão transcritos automaticamente"
        )
        
        transcricoes_texto = ""
        if arquivos_midia:
            st.info(f"🎬 {len(arquivos_midia)} arquivo(s) de mídia carregado(s)")
            if st.button("🔄 Transcrever Todos os Arquivos de Mídia"):
                with st.spinner("Transcrevendo arquivos de mídia..."):
                    for arquivo in arquivos_midia:
                        tipo = "audio" if arquivo.type.startswith('audio') else "video"
                        transcricao = transcrever_audio_video(arquivo, tipo)
                        transcricoes_texto += f"\n\n--- TRANSCRIÇÃO DE {arquivo.name.upper()} ---\n{transcricao}"
                        st.success(f"✅ {arquivo.name} transcrito!")
    
    with col2:
        st.subheader("⚙️ Configurações")
        
        tipo_conteudo = st.selectbox("Tipo de Conteúdo:", 
                                   ["Post Social", "Artigo Blog", "Email Marketing", 
                                    "Landing Page", "Script Vídeo", "Relatório Técnico",
                                    "Press Release", "Newsletter", "Case Study"])
        
        tom_voz = st.selectbox("Tom de Voz:", 
                              ["Formal", "Informal", "Persuasivo", "Educativo", 
                               "Inspirador", "Técnico", "Jornalístico"])
        
        palavras_chave = st.text_input("Palavras-chave (opcional):",
                                      placeholder="separadas por vírgula")
        
        numero_palavras = st.slider("Número de Palavras:", 100, 3000, 800)
        
        # Configurações avançadas
        with st.expander("🔧 Configurações Avançadas"):
            usar_contexto_agente = st.checkbox("Usar contexto do agente selecionado", 
                                             value=bool(st.session_state.agente_selecionado))
            
            nivel_detalhe = st.select_slider("Nível de Detalhe:", 
                                           ["Resumido", "Balanceado", "Detalhado", "Completo"])
            
            incluir_cta = st.checkbox("Incluir Call-to-Action", value=True)
            
            formato_saida = st.selectbox("Formato de Saída:", 
                                       ["Texto Simples", "Markdown", "HTML Básico"])

    # Área de instruções específicas
    st.subheader("🎯 Instruções Específicas")
    instrucoes_especificas = st.text_area(
        "Diretrizes adicionais para geração:",
        placeholder="""Exemplos:
- Focar nos benefícios para o usuário final
- Incluir estatísticas quando possível
- Manter linguagem acessível
- Evitar jargões técnicos excessivos
- Seguir estrutura: problema → solução → benefícios""",
        height=100
    )

    # Botão para gerar conteúdo
    if st.button("🚀 Gerar Conteúdo com Todos os Insumos", type="primary", use_container_width=True):
        # Verificar se há pelo menos uma fonte de conteúdo
        tem_conteudo = (arquivos_upload or 
                       briefing_manual or 
                       ('briefing_data' in locals() and briefing_data) or
                       arquivos_midia)
        
        if not tem_conteudo:
            st.error("❌ Por favor, forneça pelo menos uma fonte de conteúdo (arquivos, briefing ou mídia)")
        else:
            with st.spinner("Processando todos os insumos e gerando conteúdo..."):
                try:
                    # Construir o contexto combinado de todas as fontes
                    contexto_completo = "## FONTES DE CONTEÚDO COMBINADAS:\n\n"
                    
                    # Adicionar conteúdo dos arquivos uploadados
                    if textos_arquivos:
                        contexto_completo += "### CONTEÚDO DOS ARQUIVOS:\n" + textos_arquivos + "\n\n"
                    
                    # Adicionar briefing do banco ou manual
                    if briefing_manual:
                        contexto_completo += "### BRIEFING MANUAL:\n" + briefing_manual + "\n\n"
                    elif 'briefing_data' in locals() and briefing_data:
                        contexto_completo += "### BRIEFING DO BANCO:\n" + briefing_data['conteudo'] + "\n\n"
                    
                    # Adicionar transcrições
                    if transcricoes_texto:
                        contexto_completo += "### TRANSCRIÇÕES DE MÍDIA:\n" + transcricoes_texto + "\n\n"
                    
                    # Adicionar contexto do agente se selecionado
                    contexto_agente = ""
                    if usar_contexto_agente and st.session_state.agente_selecionado:
                        agente = st.session_state.agente_selecionado
                        contexto_agente = construir_contexto(agente, st.session_state.segmentos_selecionados)
                    
                    # Construir prompt final
                    prompt_final = f"""
                    {contexto_agente}
                    
                    ## INSTRUÇÕES PARA GERAÇÃO DE CONTEÚDO:
                    
                    **TIPO DE CONTEÚDO:** {tipo_conteudo}
                    **TOM DE VOZ:** {tom_voz}
                    **PALAVRAS-CHAVE:** {palavras_chave if palavras_chave else 'Não especificadas'}
                    **NÚMERO DE PALAVRAS:** {numero_palavras} (±10%)
                    **NÍVEL DE DETALHE:** {nivel_detalhe}
                    **INCLUIR CALL-TO-ACTION:** {incluir_cta}
                    
                    **INSTRUÇÕES ESPECÍFICAS:**
                    {instrucoes_especificas if instrucoes_especificas else 'Nenhuma instrução específica fornecida.'}
                    
                    ## FONTES E REFERÊNCIAS:
                    {contexto_completo}
                    
                    ## TAREFA:
                    Com base em TODAS as fontes fornecidas acima, gere um conteúdo do tipo {tipo_conteudo} que:
                    
                    1. **Síntese Eficiente:** Combine e sintetize informações de todas as fontes
                    2. **Coerência:** Mantenha consistência com as informações originais
                    3. **Valor Agregado:** Vá além da simples cópia, agregando insights
                    4. **Engajamento:** Crie conteúdo que engaje o público-alvo
                    5. **Clareza:** Comunique ideias complexas de forma acessível
                    
                    **FORMATO DE SAÍDA:** {formato_saida}
                    
                    Gere um conteúdo completo e profissional.
                    """
                    
                    resposta = modelo_texto.generate_content(prompt_final)
                    
                    # Processar saída baseada no formato selecionado
                    conteudo_gerado = resposta.text
                    
                    if formato_saida == "HTML Básico":
                        # Converter markdown para HTML básico
                        import re
                        conteudo_gerado = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', conteudo_gerado)
                        conteudo_gerado = re.sub(r'\*(.*?)\*', r'<em>\1</em>', conteudo_gerado)
                        conteudo_gerado = re.sub(r'### (.*?)\n', r'<h3>\1</h3>', conteudo_gerado)
                        conteudo_gerado = re.sub(r'## (.*?)\n', r'<h2>\1</h2>', conteudo_gerado)
                        conteudo_gerado = re.sub(r'# (.*?)\n', r'<h1>\1</h1>', conteudo_gerado)
                        conteudo_gerado = conteudo_gerado.replace('\n', '<br>')
                    
                    st.subheader("📄 Conteúdo Gerado")
                    
                    if formato_saida == "HTML Básico":
                        st.components.v1.html(conteudo_gerado, height=400, scrolling=True)
                    else:
                        st.markdown(conteudo_gerado)
                    
                    # Estatísticas
                    palavras_count = len(conteudo_gerado.split())
                    col_stat1, col_stat2, col_stat3 = st.columns(3)
                    with col_stat1:
                        st.metric("Palavras Geradas", palavras_count)
                    with col_stat2:
                        st.metric("Arquivos Processados", len(arquivos_upload) if arquivos_upload else 0)
                    with col_stat3:
                        st.metric("Fontes Utilizadas", 
                                 (1 if arquivos_upload else 0) + 
                                 (1 if briefing_manual or 'briefing_data' in locals() else 0) +
                                 (1 if transcricoes_texto else 0))
                    
                    # Botões de download
                    extensao = ".html" if formato_saida == "HTML Básico" else ".md" if formato_saida == "Markdown" else ".txt"
                    
                    st.download_button(
                        f"💾 Baixar Conteúdo ({formato_saida})",
                        data=conteudo_gerado,
                        file_name=f"conteudo_gerado_{datetime.datetime.now().strftime('%Y%m%d_%H%M')}{extensao}",
                        mime="text/html" if formato_saida == "HTML Básico" else "text/plain"
                    )
                    
                    # Salvar no histórico se MongoDB disponível
                    if mongo_connected_conteudo:
                        try:
                            from bson import ObjectId
                            historico_data = {
                                "tipo_conteudo": tipo_conteudo,
                                "tom_voz": tom_voz,
                                "palavras_chave": palavras_chave,
                                "numero_palavras": numero_palavras,
                                "conteudo_gerado": conteudo_gerado,
                                "fontes_utilizadas": {
                                    "arquivos_upload": [arquivo.name for arquivo in arquivos_upload] if arquivos_upload else [],
                                    "briefing_manual": bool(briefing_manual),
                                    "transcricoes": len(arquivos_midia) if arquivos_midia else 0
                                },
                                "data_criacao": datetime.datetime.now()
                            }
                            db_briefings['historico_geracao'].insert_one(historico_data)
                            st.success("✅ Conteúdo salvo no histórico!")
                        except Exception as e:
                            st.warning(f"Conteúdo gerado, mas não salvo no histórico: {str(e)}")
                    
                except Exception as e:
                    st.error(f"❌ Erro ao gerar conteúdo: {str(e)}")
                    st.info("💡 Dica: Verifique se os arquivos não estão corrompidos e tente novamente.")

    # Seção de histórico rápido
    if mongo_connected_conteudo:
        with st.expander("📚 Histórico de Gerações Recentes"):
            try:
                historico = list(db_briefings['historico_geracao'].find().sort("data_criacao", -1).limit(5))
                if historico:
                    for item in historico:
                        st.write(f"**{item['tipo_conteúdo']}** - {item['data_criacao'].strftime('%d/%m/%Y %H:%M')}")
                        st.caption(f"Palavras-chave: {item.get('palavras_chave', 'Nenhuma')} | Tom: {item['tom_voz']}")
                        with st.expander("Ver conteúdo"):
                            st.write(item['conteudo_gerado'][:500] + "..." if len(item['conteudo_gerado']) > 500 else item['conteudo_gerado'])
                else:
                    st.info("Nenhuma geração no histórico")
            except Exception as e:
                st.warning(f"Erro ao carregar histórico: {str(e)}")

# --- ABA: RESUMO DE TEXTOS ---
with tab_mapping["📝 Resumo de Textos"]:
    st.header("📝 Resumo de Textos")
    
    if not st.session_state.agente_selecionado:
        st.info("Selecione um agente primeiro na aba de Chat")
    else:
        agente = st.session_state.agente_selecionado
        st.subheader(f"Resumo com: {agente['nome']}")
        
        col_original, col_resumo = st.columns(2)
        
        with col_original:
            st.subheader("Texto Original")
            texto_original = st.text_area(
                "Cole o texto que deseja resumir:",
                height=400,
                placeholder="Insira aqui o texto completo...",
                key="texto_original"
            )
            
            with st.expander("⚙️ Configurações do Resumo"):
                nivel_resumo = st.select_slider(
                    "Nível de Resumo:",
                    options=["Extenso", "Moderado", "Conciso"],
                    value="Moderado",
                    key="nivel_resumo"
                )
                
                incluir_pontos = st.checkbox(
                    "Incluir pontos-chave em tópicos",
                    value=True,
                    key="incluir_pontos"
                )
                
                manter_terminologia = st.checkbox(
                    "Manter terminologia técnica",
                    value=True,
                    key="manter_terminologia"
                )
        
        with col_resumo:
            st.subheader("Resumo Gerado")
            
            if st.button("Gerar Resumo", key="gerar_resumo"):
                if not texto_original.strip():
                    st.warning("Por favor, insira um texto para resumir")
                else:
                    with st.spinner("Processando resumo..."):
                        try:
                            config_resumo = {
                                "Extenso": "um resumo detalhado mantendo cerca de 50% do conteúdo original",
                                "Moderado": "um resumo conciso mantendo cerca de 30% do conteúdo original",
                                "Conciso": "um resumo muito breve com apenas os pontos essenciais (cerca de 10-15%)"
                            }[nivel_resumo]
                            
                            prompt = f"""
                            {agente['system_prompt']}
                            
                            Brand Guidelines:
                            {agente.get('base_conhecimento', '')}
                            
                            Planejamento:
                            {agente.get('planejamento', '')}
                            
                            Crie um resumo deste texto com as seguintes características:
                            - {config_resumo}
                            - {"Inclua os principais pontos em tópicos" if incluir_pontos else "Formato de texto contínuo"}
                            - {"Mantenha a terminologia técnica específica" if manter_terminologia else "Simplifique a linguagem"}
                            
                            Texto para resumir:
                            {texto_original}
                            
                            Estrutura do resumo:
                            1. Título do resumo
                            2. {"Principais pontos em tópicos" if incluir_pontos else "Resumo textual"}
                            3. Conclusão/Recomendações
                            """
                            
                            resposta = modelo_texto.generate_content(prompt)
                            st.markdown(resposta.text)
                            
                            st.download_button(
                                "📋 Copiar Resumo",
                                data=resposta.text,
                                file_name="resumo_gerado.txt",
                                mime="text/plain",
                                key="download_resumo"
                            )
                            
                        except Exception as e:
                            st.error(f"Erro ao gerar resumo: {str(e)}")

# --- ABA: BUSCA WEB ---
with tab_mapping["🌐 Busca Web"]:
    st.header("🌐 Busca Web com Perplexity")
    
    if not perp_api_key:
        st.error("❌ Chave da API Perplexity não encontrada. Configure a variável de ambiente PERP_API_KEY.")
    else:
        st.success("✅ API Perplexity configurada com sucesso!")
        
        # Seleção de modo de busca
        modo_busca = st.radio(
            "Selecione o modo de busca:",
            ["🔍 Busca Geral na Web", "📋 Análise de URLs Específicas"],
            horizontal=True,
            key="modo_busca"
        )
        
        # Configurações comuns
        col_config1, col_config2 = st.columns(2)
        
        with col_config1:
            usar_agente = st.checkbox(
                "Usar contexto do agente selecionado",
                value=st.session_state.agente_selecionado is not None,
                help="Utilizar o conhecimento do agente para contextualizar a busca",
                key="usar_agente_busca"
            )
        
        with col_config2:
            if usar_agente and st.session_state.agente_selecionado:
                agente = st.session_state.agente_selecionado
                st.info(f"🎯 Usando: {agente['nome']}")
            else:
                st.info("🔍 Busca sem contexto específico")
        
        if modo_busca == "🔍 Busca Geral na Web":
            st.subheader("Busca Geral na Web")
            
            pergunta = st.text_area(
                "Digite sua pergunta para busca:",
                placeholder="Ex: Quais são as últimas tendências em marketing digital para 2024?",
                height=100,
                key="pergunta_geral"
            )
            
            # Configurações avançadas
            with st.expander("⚙️ Configurações Avançadas"):
                col_adv1, col_adv2 = st.columns(2)
                
                with col_adv1:
                    max_tokens = st.slider(
                        "Comprimento da resposta:",
                        min_value=500,
                        max_value=3000,
                        value=1500,
                        step=100,
                        key="max_tokens_geral"
                    )
                
                with col_adv2:
                    temperatura = st.slider(
                        "Criatividade:",
                        min_value=0.0,
                        max_value=1.0,
                        value=0.1,
                        step=0.1,
                        key="temp_geral"
                    )
            
            if st.button("🔎 Realizar Busca", type="primary", key="buscar_geral"):
                if not pergunta.strip():
                    st.warning("⚠️ Por favor, digite uma pergunta para busca.")
                else:
                    with st.spinner("🔄 Buscando informações na web..."):
                        # Construir contexto do agente se selecionado
                        contexto_agente = None
                        if usar_agente and st.session_state.agente_selecionado:
                            agente = st.session_state.agente_selecionado
                            contexto_agente = construir_contexto(agente, st.session_state.segmentos_selecionados)
                        
                        resultado = buscar_perplexity(
                            pergunta=pergunta,
                            contexto_agente=contexto_agente
                        )
                        
                        st.subheader("📋 Resultado da Busca")
                        st.markdown(resultado)
                        
                        # Opção para download
                        st.download_button(
                            "💾 Baixar Resultado",
                            data=resultado,
                            file_name=f"busca_web_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
                            mime="text/plain",
                            key="download_busca_geral"
                        )
        
        else:  # Análise de URLs Específicas
            st.subheader("Análise de URLs Específicas")
            
            urls_input = st.text_area(
                "Cole as URLs para análise (uma por linha):",
                placeholder="https://exemplo.com/artigo1\nhttps://exemplo.com/artigo2\nhttps://exemplo.com/noticia",
                height=150,
                key="urls_input",
                help="Insira uma URL por linha. Máximo de 5 URLs por análise."
            )
            
            pergunta_urls = st.text_area(
                "Digite a pergunta específica para análise:",
                placeholder="Ex: Com base nestas URLs, quais são os pontos principais discutidos?",
                height=100,
                key="pergunta_urls"
            )
            
            if st.button("🔍 Analisar URLs", type="primary", key="analisar_urls"):
                if not urls_input.strip() or not pergunta_urls.strip():
                    st.warning("⚠️ Por favor, preencha tanto as URLs quanto a pergunta.")
                else:
                    # Processar URLs
                    urls = [url.strip() for url in urls_input.split('\n') if url.strip()]
                    
                    if len(urls) > 5:
                        st.warning("⚠️ Muitas URLs. Analisando apenas as primeiras 5.")
                        urls = urls[:5]
                    
                    # Validar URLs
                    urls_validas = []
                    for url in urls:
                        if url.startswith(('http://', 'https://')):
                            urls_validas.append(url)
                        else:
                            st.warning(f"URL inválida (falta http:// ou https://): {url}")
                    
                    if not urls_validas:
                        st.error("❌ Nenhuma URL válida encontrada.")
                    else:
                        with st.spinner(f"🔄 Analisando {len(urls_validas)} URL(s)..."):
                            # Construir contexto do agente se selecionado
                            contexto_agente = None
                            if usar_agente and st.session_state.agente_selecionado:
                                agente = st.session_state.agente_selecionado
                                contexto_agente = construir_contexto(agente, st.session_state.segmentos_selecionados)
                            
                            resultado = analisar_urls_perplexity(
                                urls=urls_validas,
                                pergunta=pergunta_urls,
                                contexto_agente=contexto_agente
                            )
                            
                            st.subheader("📋 Resultado da Análise")
                            st.markdown(resultado)
                            
                            # Mostrar URLs analisadas
                            st.info("### 🌐 URLs Analisadas:")
                            for i, url in enumerate(urls_validas, 1):
                                st.write(f"{i}. {url}")
                            
                            # Opção para download
                            st.download_button(
                                "💾 Baixar Análise",
                                data=resultado,
                                file_name=f"analise_urls_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
                                mime="text/plain",
                                key="download_analise_urls"
                            )
        
        # Seção de informações
        with st.expander("ℹ️ Informações sobre Busca Web"):
            st.markdown("""
            ### 🌐 Capacidades da Busca Web
            
            **Busca Geral:**
            - Pesquisa em tempo real na web
            - Informações atualizadas
            - Citações de fontes confiáveis
            - Respostas contextuais
            
            **Análise de URLs:**
            - Leitura e análise de páginas específicas
            - Comparação entre múltiplas fontes
            - Extração de pontos principais
            - Síntese de informações
            
            ### ⚡ Tecnologia Utilizada
            
            - **Motor**: Perplexity AI Sonar Medium Online
            - **Atualização**: Dados em tempo real
            - **Fontes**: Diversas fontes confiáveis da web
            - **Citações**: Inclui referências às fontes
            
            ### 💡 Dicas de Uso
            
            - Para buscas gerais, seja específico na pergunta
            - Use o contexto do agente para respostas mais relevantes
            - Para URLs, prefira páginas com conteúdo textual
            - Limite de 5 URLs por análise para melhor performance
            """)

# Função para revisão ortográfica usando a API do Gemini
def revisar_texto_ortografia(texto, agente, segmentos_selecionados, revisao_estilo=True, manter_estrutura=True, explicar_alteracoes=True):
    """
    Realiza revisão ortográfica e gramatical do texto considerando as diretrizes do agente
    usando a API do Gemini
    """
    
    # Construir o contexto do agente
    contexto_agente = "CONTEXTO DO AGENTE PARA REVISÃO:\n\n"
    
    if "system_prompt" in segmentos_selecionados and "system_prompt" in agente:
        contexto_agente += f"DIRETRIZES PRINCIPAIS:\n{agente['system_prompt']}\n\n"
    
    if "base_conhecimento" in segmentos_selecionados and "base_conhecimento" in agente:
        contexto_agente += f"BASE DE CONHECIMENTO:\n{agente['base_conhecimento']}\n\n"
    
    if "comments" in segmentos_selecionados and "comments" in agente:
        contexto_agente += f"COMENTÁRIOS E OBSERVAÇÕES:\n{agente['comments']}\n\n"
    
    if "planejamento" in segmentos_selecionados and "planejamento" in agente:
        contexto_agente += f"PLANEJAMENTO E ESTRATÉGIA:\n{agente['planejamento']}\n\n"
    
    # Construir instruções baseadas nas configurações
    instrucoes_revisao = ""
    
    if revisao_estilo:
        instrucoes_revisao += """
        - Analise e melhore a clareza, coesão e coerência textual
        - Verifique adequação ao tom da marca
        - Elimine vícios de linguagem e redundâncias
        - Simplifique frases muito longas ou complexas
        """
    
    if manter_estrutura:
        instrucoes_revisao += """
        - Mantenha a estrutura geral do texto original
        - Preserve parágrafos e seções quando possível
        - Conserve o fluxo lógico do conteúdo
        """
    
    if explicar_alteracoes:
        instrucoes_revisao += """
        - Inclua justificativa para as principais alterações
        - Explique correções gramaticais importantes
        - Destaque melhorias de estilo significativas
        """
    
    # Construir o prompt para revisão
    prompt_revisao = f"""
    {contexto_agente}
    
    TEXTO PARA REVISÃO:
    {texto}
    
    INSTRUÇÕES PARA REVISÃO:
    
    1. **REVISÃO ORTOGRÁFICA E GRAMATICAL:**
       - Corrija erros de ortografia, acentuação e grafia
       - Verifique concordância nominal e verbal
       - Ajuste pontuação (vírgulas, pontos, travessões)
       - Corrija regência verbal e nominal
       - Ajuste colocação pronominal
    
    2. **REVISÃO DE ESTILO E CLAREZA:**
       {instrucoes_revisao}
    
    3. **CONFORMIDADE COM AS DIRETRIZES:**
       - Alinhe o texto ao tom e estilo definidos
       - Mantenha consistência terminológica
       - Preserve a estrutura original quando possível
       - Adapte ao público-alvo definido
    
    FORMATO DA RESPOSTA:
    
    ## 📋 TEXTO REVISADO
    [Aqui vai o texto completo revisado, mantendo a estrutura geral quando possível]
    
    ## 🔍 PRINCIPAIS ALTERAÇÕES REALIZADAS
    [Lista das principais correções realizadas com justificativa]
    
    
    **IMPORTANTE:**
    - Seja detalhado e preciso nas explicações
    - Mantenha o formato markdown para fácil leitura
    - Inclua exemplos específicos quando relevante
    - Foque nas correções ortográficas e gramaticais
    """
    
    try:
        # Chamar a API do Gemini
        response = modelo_texto.generate_content(prompt_revisao)
        
        if response and response.text:
            return response.text
        else:
            return "❌ Erro: Não foi possível gerar a revisão. Tente novamente."
        
    except Exception as e:
        return f"❌ Erro durante a revisão: {str(e)}"

# --- ABA: REVISÃO ORTOGRÁFICA ---
with tab_mapping["📝 Revisão Ortográfica"]:
    st.header("📝 Revisão Ortográfica e Gramatical")
    
    if not st.session_state.agente_selecionado:
        st.info("Selecione um agente primeiro na aba de Chat")
    else:
        agente = st.session_state.agente_selecionado
        st.subheader(f"Revisão com: {agente['nome']}")
        
        # Configurações de segmentos para revisão
        st.sidebar.subheader("🔧 Configurações de Revisão")
        st.sidebar.write("Selecione bases para orientar a revisão:")
        
        segmentos_revisao = st.sidebar.multiselect(
            "Bases para revisão:",
            options=["system_prompt", "base_conhecimento", "comments", "planejamento"],
            default=st.session_state.segmentos_selecionados,
            key="revisao_segmentos"
        )
        
        # Layout em abas para diferentes métodos de entrada
        tab_texto, tab_arquivo = st.tabs(["📝 Texto Direto", "📎 Upload de Arquivos"])
        
        with tab_texto:
            # Layout em colunas para texto direto
            col_original, col_resultado = st.columns(2)
            
            with col_original:
                st.subheader("📄 Texto Original")
                
                texto_para_revisao = st.text_area(
                    "Cole o texto que deseja revisar:",
                    height=400,
                    placeholder="Cole aqui o texto que precisa de revisão ortográfica e gramatical...",
                    help="O texto será analisado considerando as diretrizes do agente selecionado",
                    key="texto_revisao"
                )
                
                # Estatísticas do texto
                if texto_para_revisao:
                    palavras = len(texto_para_revisao.split())
                    caracteres = len(texto_para_revisao)
                    paragrafos = texto_para_revisao.count('\n\n') + 1
                    
                    col_stats1, col_stats2, col_stats3 = st.columns(3)
                    with col_stats1:
                        st.metric("📊 Palavras", palavras)
                    with col_stats2:
                        st.metric("🔤 Caracteres", caracteres)
                    with col_stats3:
                        st.metric("📄 Parágrafos", paragrafos)
                
                # Configurações de revisão
                with st.expander("⚙️ Configurações da Revisão"):
                    revisao_estilo = st.checkbox(
                        "Incluir revisão de estilo",
                        value=True,
                        help="Analisar clareza, coesão e adequação ao tom da marca",
                        key="revisao_estilo"
                    )
                    
                    manter_estrutura = st.checkbox(
                        "Manter estrutura original",
                        value=True,
                        help="Preservar a estrutura geral do texto quando possível",
                        key="manter_estrutura"
                    )
                    
                    explicar_alteracoes = st.checkbox(
                        "Explicar alterações principais",
                        value=True,
                        help="Incluir justificativa para as mudanças mais importantes",
                        key="explicar_alteracoes"
                    )
            
            with col_resultado:
                st.subheader("📋 Resultado da Revisão")
                
                if st.button("🔍 Realizar Revisão Completa", type="primary", key="revisar_texto"):
                    if not texto_para_revisao.strip():
                        st.warning("⚠️ Por favor, cole o texto que deseja revisar.")
                    else:
                        with st.spinner("🔄 Analisando texto e realizando revisão..."):
                            try:
                                resultado = revisar_texto_ortografia(
                                    texto=texto_para_revisao,
                                    agente=agente,
                                    segmentos_selecionados=segmentos_revisao,
                                    revisao_estilo=revisao_estilo,
                                    manter_estrutura=manter_estrutura,
                                    explicar_alteracoes=explicar_alteracoes
                                )
                                
                                st.markdown(resultado)
                                
                                # Opções de download
                                col_dl1, col_dl2, col_dl3 = st.columns(3)
                                
                                with col_dl1:
                                    st.download_button(
                                        "💾 Baixar Relatório Completo",
                                        data=resultado,
                                        file_name=f"relatorio_revisao_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
                                        mime="text/plain",
                                        key="download_revisao_completo"
                                    )
                                
                                with col_dl2:
                                    # Extrair apenas o texto revisado se disponível
                                    if "## 📋 TEXTO REVISADO" in resultado:
                                        texto_revisado_start = resultado.find("## 📋 TEXTO REVISADO")
                                        texto_revisado_end = resultado.find("##", texto_revisado_start + 1)
                                        texto_revisado = resultado[texto_revisado_start:texto_revisado_end] if texto_revisado_end != -1 else resultado[texto_revisado_start:]
                                        
                                        st.download_button(
                                            "📄 Baixar Texto Revisado",
                                            data=texto_revisado,
                                            file_name=f"texto_revisado_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
                                            mime="text/plain",
                                            key="download_texto_revisado"
                                        )
                                
                                with col_dl3:
                                    # Extrair apenas as explicações se disponível
                                    if "## 🔍 PRINCIPAIS ALTERAÇÕES REALIZADAS" in resultado:
                                        explicacoes_start = resultado.find("## 🔍 PRINCIPAIS ALTERAÇÕES REALIZADAS")
                                        explicacoes_end = resultado.find("##", explicacoes_start + 1)
                                        explicacoes = resultado[explicacoes_start:explicacoes_end] if explicacoes_end != -1 else resultado[explicacoes_start:]
                                        
                                        st.download_button(
                                            "📝 Baixar Explicações",
                                            data=explicacoes,
                                            file_name=f"explicacoes_revisao_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
                                            mime="text/plain",
                                            key="download_explicacoes"
                                        )
                                
                            except Exception as e:
                                st.error(f"❌ Erro ao realizar revisão: {str(e)}")
        
        with tab_arquivo:
            st.subheader("📎 Upload de Arquivos para Revisão")
            
            # Upload de múltiplos arquivos
            arquivos_upload = st.file_uploader(
                "Selecione arquivos PDF ou PPTX para revisão:",
                type=['pdf', 'pptx'],
                accept_multiple_files=True,
                help="Arquivos serão convertidos para texto e revisados ortograficamente",
                key="arquivos_revisao"
            )
            
            # Configurações para arquivos
            with st.expander("⚙️ Configurações da Revisão para Arquivos"):
                revisao_estilo_arquivos = st.checkbox(
                    "Incluir revisão de estilo",
                    value=True,
                    help="Analisar clareza, coesão e adequação ao tom da marca",
                    key="revisao_estilo_arquivos"
                )
                
                manter_estrutura_arquivos = st.checkbox(
                    "Manter estrutura original",
                    value=True,
                    help="Preservar a estrutura geral do texto quando possível",
                    key="manter_estrutura_arquivos"
                )
                
                explicar_alteracoes_arquivos = st.checkbox(
                    "Explicar alterações principais",
                    value=True,
                    help="Incluir justificativa para as mudanças mais importantes",
                    key="explicar_alteracoes_arquivos"
                )
            
            if arquivos_upload:
                st.success(f"✅ {len(arquivos_upload)} arquivo(s) carregado(s)")
                
                # Mostrar preview dos arquivos
                with st.expander("📋 Visualizar Arquivos Carregados", expanded=False):
                    for i, arquivo in enumerate(arquivos_upload):
                        st.write(f"**{arquivo.name}** ({arquivo.size} bytes)")
                
                if st.button("🔍 Revisar Todos os Arquivos", type="primary", key="revisar_arquivos"):
                    resultados_completos = []
                    
                    for arquivo in arquivos_upload:
                        with st.spinner(f"Processando {arquivo.name}..."):
                            try:
                                # Extrair texto do arquivo
                                texto_extraido = ""
                                
                                if arquivo.type == "application/pdf":
                                    texto_extraido = extract_text_from_pdf(arquivo)
                                elif arquivo.type == "application/vnd.openxmlformats-officedocument.presentationml.presentation":
                                    texto_extraido = extract_text_from_pptx(arquivo)
                                else:
                                    st.warning(f"Tipo de arquivo não suportado: {arquivo.name}")
                                    continue
                                
                                if texto_extraido and len(texto_extraido.strip()) > 0:
                                    # Realizar revisão
                                    resultado = revisar_texto_ortografia(
                                        texto=texto_extraido,
                                        agente=agente,
                                        segmentos_selecionados=segmentos_revisao,
                                        revisao_estilo=revisao_estilo_arquivos,
                                        manter_estrutura=manter_estrutura_arquivos,
                                        explicar_alteracoes=explicar_alteracoes_arquivos
                                    )
                                    
                                    resultados_completos.append({
                                        'nome': arquivo.name,
                                        'texto_original': texto_extraido,
                                        'resultado': resultado
                                    })
                                    
                                    # Exibir resultado individual
                                    with st.expander(f"📄 Resultado - {arquivo.name}", expanded=False):
                                        st.markdown(resultado)
                                        
                                        # Estatísticas do arquivo processado
                                        palavras_orig = len(texto_extraido.split())
                                        st.info(f"📊 Arquivo original: {palavras_orig} palavras")
                                        
                                else:
                                    st.warning(f"❌ Não foi possível extrair texto do arquivo: {arquivo.name}")
                                
                            except Exception as e:
                                st.error(f"❌ Erro ao processar {arquivo.name}: {str(e)}")
                    
                    # Botão para download de todos os resultados
                    if resultados_completos:
                        st.markdown("---")
                        st.subheader("📦 Download de Todos os Resultados")
                        
                        # Criar relatório consolidado
                        relatorio_consolidado = f"# RELATÓRIO DE REVISÃO ORTOGRÁFICA\n\n"
                        relatorio_consolidado += f"**Data:** {datetime.datetime.now().strftime('%d/%m/%Y %H:%M')}\n"
                        relatorio_consolidado += f"**Agente:** {agente['nome']}\n"
                        relatorio_consolidado += f"**Total de Arquivos:** {len(resultados_completos)}\n\n"
                        
                        for resultado in resultados_completos:
                            relatorio_consolidado += f"## 📄 {resultado['nome']}\n\n"
                            relatorio_consolidado += f"{resultado['resultado']}\n\n"
                            relatorio_consolidado += "---\n\n"
                        
                        st.download_button(
                            "💾 Baixar Relatório Consolidado",
                            data=relatorio_consolidado,
                            file_name=f"relatorio_revisao_arquivos_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
                            mime="text/plain",
                            key="download_consolidado"
                        )
            
            else:
                st.info("""
                **📎 Como usar o upload de arquivos:**
                
                1. Selecione um ou mais arquivos PDF ou PPTX
                2. Configure as opções de revisão
                3. Clique em **"Revisar Todos os Arquivos"**
                
                **📋 Formatos suportados:**
                - PDF (documentos, apresentações)
                - PPTX (apresentações PowerPoint)
                
                **⚡ Processamento:**
                - Arquivos são convertidos para texto automaticamente
                - Texto é revisado ortograficamente
                - Resultados podem ser baixados individualmente ou em lote
                """)
        
        # Seção informativa
        with st.expander("ℹ️ Sobre a Revisão Ortográfica"):
            st.markdown("""
            ### 🎯 O que é Analisado
            
            **🔤 Ortografia:**
            - Erros de grafia e acentuação
            - Uso correto de maiúsculas e minúsculas
            - Escrita de números e datas
            - Concordância nominal e verbal
            
            **📖 Gramática:**
            - Estrutura sintática das frases
            - Uso adequado de preposições
            - Colocação pronominal
            - Regência verbal e nominal
            
            **🔠 Pontuação:**
            - Uso de vírgulas, pontos, dois-pontos
            - Aplicação de travessões e parênteses
            - Pontuação de citações e diálogos
            
            **📝 Estilo e Clareza:**
            - Coesão e coerência textual
            - Adequação ao tom da marca
            - Clareza na comunicação
            - Eliminação de vícios de linguagem
            
            ### 💡 Dicas para Melhor Revisão
            
            1. **Texto Completo**: Cole o texto integral para análise detalhada
            2. **Segmentos Relevantes**: Selecione as bases de conhecimento apropriadas
            3. **Contexto Específico**: Use agentes especializados para cada tipo de conteúdo
            4. **Implementação**: Aplique as sugestões sistematicamente
            
            ### 🎨 Benefícios da Revisão Contextual
            
            - **Consistência da Marca**: Mantém o tom e estilo adequados
            - **Qualidade Profissional**: Elimina erros que prejudicam a credibilidade
            - **Otimização de Conteúdo**: Melhora a clareza e impacto da comunicação
            - **Eficiência**: Reduz tempo de revisão manual
            """)
            

# --- ABA: MONITORAMENTO DE REDES ---
with tab_mapping["Monitoramento de Redes"]:
    st.header("🤖 Agente de Monitoramento")
    st.markdown("**Especialista que fala como gente** - Conectando conhecimento técnico e engajamento social")
    
    # --- CONFIGURAÇÃO DO ASTRA DB DENTRO DA ABA ---
    class AstraDBClient:
        def __init__(self):
            self.base_url = f"{os.getenv('ASTRA_DB_API_ENDPOINT')}/api/json/v1/{os.getenv('ASTRA_DB_NAMESPACE')}"
            self.headers = {
                "Content-Type": "application/json",
                "x-cassandra-token": os.getenv('ASTRA_DB_APPLICATION_TOKEN'),
                "Accept": "application/json"
            }
        
        def vector_search(self, collection: str, vector: List[float], limit: int = 5) -> List[Dict]:
            """Realiza busca por similaridade vetorial"""
            url = f"{self.base_url}/{collection}"
            payload = {
                "find": {
                    "sort": {"$vector": vector},
                    "options": {"limit": limit}
                }
            }
            try:
                response = requests.post(url, json=payload, headers=self.headers, timeout=30)
                response.raise_for_status()
                data = response.json()
                return data.get("data", {}).get("documents", [])
            except Exception as e:
                st.error(f"Erro na busca vetorial: {str(e)}")
                return []

    # Inicializa o cliente AstraDB
    try:
        astra_client = AstraDBClient()
        st.success("✅ Conectado ao Astra DB")
    except Exception as e:
        st.error(f"❌ Erro ao conectar com Astra DB: {str(e)}")
        astra_client = None

    def get_embedding(text: str) -> List[float]:
        """Obtém embedding do texto usando OpenAI"""
        try:
            client = openai.OpenAI(api_key=os.getenv('OPENAI_API_KEY'))
            response = client.embeddings.create(
                input=text,
                model="text-embedding-3-small"
            )
            return response.data[0].embedding
        except Exception as e:
            st.warning(f"Embedding OpenAI não disponível: {str(e)}")
            # Fallback para embedding simples
            import numpy as np
            text_hash = hashlib.md5(text.encode()).hexdigest()
            vector = [float(int(text_hash[i:i+2], 16) / 255.0) for i in range(0, 32, 2)]
            # Preenche para ter 1536 dimensões
            while len(vector) < 1536:
                vector.append(0.0)
            return vector[:1536]

    def buscar_conhecimento_tecnico(pergunta: str) -> str:
        """Busca conhecimento técnico na Astra DB usando RAG"""
        try:
            # Gera embedding para a pergunta
            embedding = get_embedding(pergunta)
            
            # Busca documentos relevantes
            relevant_docs = astra_client.vector_search(os.getenv('ASTRA_DB_COLLECTION'), embedding, limit=5)
            
            # Constrói contexto dos documentos
            contexto_tecnico = ""
            if relevant_docs:
                contexto_tecnico = "INFORMAÇÕES TÉCNICAS DA BASE:\n\n"
                for i, doc in enumerate(relevant_docs, 1):
                    doc_content = str(doc)
                    # Limpa e formata o documento
                    doc_clean = doc_content.replace('{', '').replace('}', '').replace("'", "").replace('"', '')
                    contexto_tecnico += f"--- Fonte {i} ---\n{doc_clean[:600]}...\n\n"
            else:
                contexto_tecnico = "Consulta não retornou informações técnicas específicas da base."
            
            return contexto_tecnico
            
        except Exception as e:
            st.error(f"Erro na busca de conhecimento técnico: {str(e)}")
            return ""

    def gerar_resposta_agente(pergunta_usuario: str, historico: List[Dict] = None) -> str:
        """Gera resposta do agente usando RAG"""
        
        # Busca conhecimento técnico relevante
        contexto_tecnico = buscar_conhecimento_tecnico(pergunta_usuario)
        
        # Configuração do agente
        system_prompt = """
        PERSONALIDADE: Especialista técnico do agronegócio com habilidade social - "Especialista que fala como gente"

        TOM DE VOZ:
        - Técnico, confiável e seguro, mas acessível
        - Evita exageros e promessas vazias
        - Sempre embasado em fatos e ciência
        - Frases curtas e diretas, mais simpáticas
        - Toque de leveza e ironia pontual quando o contexto permite
        - Comunica como quem entende o campo e a internet

        DIRETRIZES DE ESTILO:
        - Evitar jargões excessivos (usar apenas quando necessário)
        - Ensinar sem parecer que está dando aula
        - Preferir frases curtas
        - Usar emojis com parcimônia, apenas quando encaixam no contexto
        - Sempre positivo e construtivo
        - Assumir autoridade técnica sem arrogância

        TIPOS DE INTERAÇÃO:

        1. TÉCNICA/EDUCATIVA:
        - Foco: performance de produtos, boas práticas agrícolas, conceitos técnicos
        - Linguagem: direta, com analogias simples e didáticas
        - Exemplo: "Os nematoides são como ladrões invisíveis do solo — e o Victrato age como uma cerca viva subterrânea contra eles."

        2. SOCIAL/ENGAJAMENTO:
        - Foco: responder comentários, interagir em posts, participar de trends
        - Linguagem: leve, simpática e natural
        - Exemplo: "A gente também ama ver um talhão desse jeito 😍 Solo vivo é solo produtivo!"

        3. INSTITUCIONAL:
        - Foco: valores, propósito, sustentabilidade, ciência
        - Linguagem: inspiradora, mas sem ser piegas
        - Exemplo: "Quando o produtor prospera, o campo inteiro floresce. É pra isso que a gente trabalha todo dia."

        PALAVRAS-CHAVE DA PERSONALIDADE:
        Confiável | Técnico | Gentil | Moderno | Natural | Direto | Otimista | Didático | Orgulhosamente agro

        REGRAS IMPORTANTES:
        - NÃO inventar informações técnicas que não estejam na base de conhecimento
        - Sempre basear respostas técnicas nas informações fornecidas
        - Manter tom profissional mas acessível
        - Adaptar a resposta ao tipo de pergunta (técnica, social ou institucional)
        """
        
        # Constrói o prompt final
        prompt_final = f"""
        {system_prompt}
        
        CONTEXTO TÉCNICO DA BASE:
        {contexto_tecnico}
        
        PERGUNTA DO USUÁRIO:
        {pergunta_usuario}
        
        HISTÓRICO DA CONVERSA (se aplicável):
        {historico if historico else "Nenhum histórico anterior"}
        
        INSTRUÇÕES FINAIS:
        Baseie sua resposta principalmente nas informações técnicas da base.
        Se a pergunta for técnica e não houver informações suficientes na base, seja honesto e diga que não tem a informação específica.
        Adapte seu tom ao tipo de pergunta:
        - Perguntas técnicas: seja preciso e didático
        - Perguntas sociais: seja leve e engajador  
        - Críticas ou problemas: seja construtivo e proativo
        
        Sua resposta deve refletir a personalidade do "especialista que fala como gente".
        """
        
        try:
            resposta = modelo_texto.generate_content(prompt_final)
            return resposta.text
        except Exception as e:
            return f"Erro ao gerar resposta: {str(e)}"

    # Sidebar com informações
    with st.sidebar:
        st.header("ℹ️ Sobre o Agente")
        st.markdown("""
        **Personalidade:**
        - 🎯 Técnico mas acessível
        - 💬 Direto mas simpático
        - 🌱 Conhece o campo e a internet
        - 🔬 Baseado em ciência
        
        **Capacidades:**
        - Respostas técnicas baseadas em RAG
        - Engajamento em redes sociais
        - Suporte a produtores
        - Esclarecimento de dúvidas
        """)
        
        st.header("🔧 Configurações")
        modo_resposta = st.selectbox(
            "Modo de Resposta:",
            ["Automático", "Técnico", "Social", "Institucional"],
            key="modo_resposta_monitoramento"
        )
        
        if st.button("🔄 Reiniciar Conversa", key="reiniciar_monitoramento"):
            if "messages_monitoramento" in st.session_state:
                st.session_state.messages_monitoramento = []
            st.rerun()

        # Status da conexão
        st.header("📊 Status do Sistema")
        if astra_client:
            st.success("✅ Astra DB: Conectado")
        else:
            st.error("❌ Astra DB: Desconectado")
        
        if os.getenv('OPENAI_API_KEY'):
            st.success("✅ OpenAI: Configurado")
        else:
            st.warning("⚠️ OpenAI: Não configurado")

    # Inicializar histórico de mensagens específico para monitoramento
    if "messages_monitoramento" not in st.session_state:
        st.session_state.messages_monitoramento = []

    # Área de chat principal
    st.header("💬 Simulador de Respostas do Agente")

    # Exemplos de perguntas rápidas
    st.subheader("🎯 Exemplos para testar:")
    col1, col2, col3 = st.columns(3)

    with col1:
        if st.button("❓ Dúvida Técnica", use_container_width=True, key="exemplo_tecnico"):
            st.session_state.messages_monitoramento.append({"role": "user", "content": "Esse produto serve pra todas as culturas?"})

    with col2:
        if st.button("😊 Comentário Social", use_container_width=True, key="exemplo_social"):
            st.session_state.messages_monitoramento.append({"role": "user", "content": "O campo tá lindo demais!"})

    with col3:
        if st.button("⚠️ Crítica/Problema", use_container_width=True, key="exemplo_critica"):
            st.session_state.messages_monitoramento.append({"role": "user", "content": "Usei e não funcionou."})

    # Exibir histórico de mensagens
    for message in st.session_state.messages_monitoramento:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    # Input do usuário
    if prompt := st.chat_input("Digite sua mensagem ou pergunta...", key="chat_monitoramento"):
        # Adicionar mensagem do usuário
        st.session_state.messages_monitoramento.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)
        
        # Gerar resposta do agente
        with st.chat_message("assistant"):
            with st.spinner("🌱 Consultando base técnica..."):
                resposta = gerar_resposta_agente(prompt, st.session_state.messages_monitoramento)
                st.markdown(resposta)
                
                # Adicionar ao histórico
                st.session_state.messages_monitoramento.append({"role": "assistant", "content": resposta})

    # Seção de análise de performance
    st.markdown("---")
    st.header("📊 Análise da Resposta")

    if st.session_state.messages_monitoramento:
        ultima_resposta = st.session_state.messages_monitoramento[-1]["content"] if st.session_state.messages_monitoramento[-1]["role"] == "assistant" else ""
        
        if ultima_resposta:
            col_analise1, col_analise2, col_analise3 = st.columns(3)
            
            with col_analise1:
                # Análise de tom
                if "😊" in ultima_resposta or "😍" in ultima_resposta:
                    st.metric("Tom Identificado", "Social/Engajador", delta="Leve")
                elif "🔬" in ultima_resposta or "📊" in ultima_resposta:
                    st.metric("Tom Identificado", "Técnico", delta="Preciso")
                else:
                    st.metric("Tom Identificado", "Balanceado", delta="Adaptado")
            
            with col_analise2:
                # Comprimento da resposta
                palavras = len(ultima_resposta.split())
                st.metric("Tamanho", f"{palavras} palavras")
            
            with col_analise3:
                # Uso de emojis
                emojis = sum(1 for char in ultima_resposta if char in "😀😃😄😁😆😅😂🤣☺️😊😇🙂🙃😉😌😍🥰😘😗😙😚😋😛😝😜🤪🤨🧐🤓😎🤩🥳😏😒😞😔😟😕🙁☹️😣😖😫😩🥺😢😭😤😠😡🤬🤯😳🥵🥶😱😨😰😥😓🤗🤔🤭🤫🤥😶😐😑😬🙄😯😦😧😮😲🥱😴🤤😪😵🤐🥴🤢🤮🤧😷🤒🤕🤑🤠😈👿👹👺🤡💩👻💀☠️👽👾🤖🎃😺😸😹😻😼😽🙀😿😾")
                st.metric("Emojis", emojis, delta="Moderado" if emojis <= 2 else "Alto")

    # Seção de exemplos de uso
    with st.expander("📋 Exemplos de Respostas do Agente"):
        st.markdown("""
        **🎯 PERGUNTA TÉCNICA:**
        *Usuário:* "Qual a diferença entre os nematoides de galha e de cisto na soja?"
        
        **🤖 AGENTE:** "Boa pergunta! Os nematoides de galha (Meloidogyne) formam aquelas 'inchações' nas raízes, enquanto os de cisto (Heterodera) ficam mais externos. Ambos roubam nutrientes, mas o manejo pode ser diferente. Temos soluções específicas para cada caso! 🌱"
        
        **🎯 COMENTÁRIO SOCIAL:**
        *Usuário:* "Adorei ver as fotos da lavoura no stories!"
        
        **🤖 AGENTE:** "A gente também ama compartilhar esses momentos! Quando a tecnologia encontra o cuidado certo, o campo fica ainda mais bonito 😍 Compartilhe suas fotos também!"
        
        **🎯 CRÍTICA/PROBLEMA:**
        *Usuário:* "A aplicação não deu o resultado esperado"
        
        **🤖 AGENTE:** "Poxa, que pena saber disso! Vamos entender melhor o que aconteceu. Pode me contar sobre as condições de aplicação? Assim conseguimos te orientar melhor da próxima vez. A equipe técnica também está à disposição! 📞"
        """)

    # Seção de configurações avançadas
    with st.expander("⚙️ Configurações Avançadas do RAG"):
        st.subheader("Configurações da Busca Vetorial")
        
        col_rag1, col_rag2 = st.columns(2)
        
        with col_rag1:
            limite_documentos = st.slider(
                "Número de documentos para busca:",
                min_value=1,
                max_value=10,
                value=5,
                help="Quantos documentos similares buscar na base de conhecimento"
            )
        
        with col_rag2:
            similaridade_minima = st.slider(
                "Similaridade mínima:",
                min_value=0.0,
                max_value=1.0,
                value=0.7,
                help="Limite de similaridade para considerar documentos relevantes"
            )
        
        if st.button("🔄 Testar Conexão RAG", key="testar_rag"):
            with st.spinner("Testando conexão com Astra DB..."):
                try:
                    # Teste simples de busca
                    embedding_teste = get_embedding("teste de conexão")
                    documentos = astra_client.vector_search(os.getenv('ASTRA_DB_COLLECTION'), embedding_teste, limit=1)
                    if documentos:
                        st.success(f"✅ Conexão funcionando! {len(documentos)} documento(s) encontrado(s)")
                    else:
                        st.warning("⚠️ Conexão funcionando, mas nenhum documento encontrado")
                except Exception as e:
                    st.error(f"❌ Erro na conexão: {str(e)}")

    # Footer
    st.markdown("---")
    st.markdown(
        """
        <div style='text-align: center; color: #666;'>
        <i>Agente Social • Especialista que fala como gente • Conectando conhecimento técnico e pessoas</i>
        </div>
        """,
        unsafe_allow_html=True
    )

# --- Estilização ---
st.markdown("""
<style>
    .stChatMessage {
        padding: 1rem;
        border-radius: 0.5rem;
        margin-bottom: 1rem;
    }
    [data-testid="stChatMessageContent"] {
        font-size: 1rem;
    }
    .stChatInput {
        bottom: 20px;
        position: fixed;
        width: calc(100% - 5rem);
    }
    div[data-testid="stTabs"] {
        margin-top: -30px;
    }
    div[data-testid="stVerticalBlock"] > div:has(>.stTextArea) {
        border-left: 3px solid #4CAF50;
        padding-left: 1rem;
    }
    .segment-indicator {
        background-color: #f0f2f6;
        padding: 0.5rem;
        border-radius: 0.5rem;
        margin: 0.5rem 0;
        border-left: 4px solid #4CAF50;
    }
    .video-analysis-card {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
        padding: 1.5rem;
        border-radius: 10px;
        margin: 1rem 0;
    }
    .inheritance-badge {
        background-color: #e3f2fd;
        color: #1976d2;
        padding: 0.2rem 0.5rem;
        border-radius: 12px;
        font-size: 0.8rem;
        margin-left: 0.5rem;
    }
    .web-search-card {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
        padding: 1.5rem;
        border-radius: 10px;
        margin: 1rem 0;
    }
    .seo-analysis-card {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
        padding: 1.5rem;
        border-radius: 10px;
        margin: 1rem 0;
    }
    .spelling-review-card {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
        padding: 1.5rem;
        border-radius: 10px;
        margin: 1rem 0;
    }
    .validation-unified-card {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
        padding: 1.5rem;
        border-radius: 10px;
        margin: 1rem 0;
    }
</style>
""", unsafe_allow_html=True)
